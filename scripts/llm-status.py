#!/usr/bin/env python3
"""Read-only endpoint sampling; loopback JSON API with durable availability evidence."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.client import HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import sqlite3
import ssl
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

import yaml


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_config(path):
    config = yaml.safe_load(Path(path).read_text())
    if config.get("schema_version") != 1:
        raise ValueError("Unsupported configuration schema")
    for key, low, high in (
        ("interval_seconds", 10, 3600),
        ("timeout_seconds", 1, 10),
        ("retention_days", 1, 30),
    ):
        if type(config.get(key)) is not int or not low <= config[key] <= high:
            raise ValueError(f"Invalid {key}")
    endpoints = config["endpoints"]
    if not 1 <= len(endpoints) <= 20:
        raise ValueError("Configure between 1 and 20 endpoints")
    identities = set()
    for endpoint in endpoints:
        url = urlsplit(endpoint["url"])
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError(
                "Endpoints must be HTTP(S) URLs without credentials or queries"
            )
        if endpoint["check"] not in {"glm", "ollama"}:
            raise ValueError("Unknown readiness check")
        if not endpoint.get("host") or endpoint["id"] in identities:
            raise ValueError("Missing host or duplicate endpoint ID")
        identities.add(endpoint["id"])
    return config


def probe(endpoint, timeout):
    started = time.monotonic()
    code = None
    state = "unavailable"
    # Explicit targets bypass ambient proxies; never follow a login redirect.
    opener = build_opener(NoRedirect(), ProxyHandler({}))
    try:
        with opener.open(endpoint["url"], timeout=timeout) as response:
            code = response.status
            body = response.read(65537)
            if len(body) > 65536:
                state = "invalid_response"
            else:
                payload = json.loads(body)
                valid = isinstance(payload, dict) and (
                    payload.get("status") == "ok"
                    if endpoint["check"] == "glm"
                    else isinstance(payload.get("version"), str)
                    and bool(payload["version"])
                )
                state = "ready" if code == 200 and valid else "invalid_response"
    except HTTPError as error:
        code = error.code
        state = (
            "authentication_required"
            if code in {401, 403}
            else "redirect"
            if 300 <= code < 400
            else "unavailable"
        )
    except (TimeoutError, socket.timeout):
        state = "timeout"
    except URLError as error:
        state = (
            "tls_error"
            if isinstance(error.reason, ssl.SSLError)
            else "timeout"
            if isinstance(error.reason, TimeoutError)
            else "unavailable"
        )
    except (ValueError, UnicodeError, HTTPException):
        state = "invalid_response"
    except OSError:
        state = "unavailable"
    return {
        "state": state,
        "http_status": code,
        "latency_ms": round((time.monotonic() - started) * 1000, 1),
    }


class Monitor:
    def __init__(self, config, database):
        self.config = config
        self.database = str(database)
        self.interval = config["interval_seconds"]
        Path(database).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS samples (
                endpoint TEXT, url TEXT, checked_at REAL, state TEXT,
                http_status INTEGER, latency_ms REAL)""")
            db.execute("CREATE INDEX IF NOT EXISTS sample_time ON samples(checked_at)")
        os.chmod(database, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def sample(self):
        endpoints = self.config["endpoints"]
        with ThreadPoolExecutor(max_workers=len(endpoints)) as pool:
            results = list(
                pool.map(
                    lambda endpoint: probe(endpoint, self.config["timeout_seconds"]),
                    endpoints,
                )
            )
        now = time.time()
        with self.connect() as db:
            for endpoint, result in zip(endpoints, results):
                db.execute(
                    "INSERT INTO samples VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        endpoint["id"],
                        endpoint["url"],
                        now,
                        result["state"],
                        result["http_status"],
                        result["latency_ms"],
                    ),
                )
            db.execute(
                "DELETE FROM samples WHERE checked_at < ?",
                (now - self.config["retention_days"] * 86400,),
            )

    def report(self, now=None):
        now = time.time() if now is None else now
        endpoints = []
        freshness = 2 * self.interval + self.config["timeout_seconds"]
        with self.connect() as db:
            for endpoint in self.config["endpoints"]:
                rows = db.execute(
                    "SELECT checked_at, state, http_status, latency_ms FROM samples "
                    "WHERE endpoint = ? AND url = ? AND checked_at >= ? "
                    "ORDER BY checked_at",
                    (
                        endpoint["id"],
                        endpoint["url"],
                        now - self.config["retention_days"] * 86400,
                    ),
                ).fetchall()
                latest = rows[-1] if rows else None
                stale = not latest or now - latest[0] > freshness
                windows = {}
                for hours in (1, 24, 168):
                    if hours > self.config["retention_days"] * 24:
                        continue
                    selected = [row for row in rows if row[0] >= now - hours * 3600]
                    count = len(selected)
                    ready = sum(row[1] == "ready" for row in selected)
                    windows[str(hours)] = {
                        "samples": count,
                        "ready_samples": ready,
                        "sampled_availability_percent": round(100 * ready / count, 2)
                        if count
                        else None,
                        "expected_samples": hours * 3600 // self.interval,
                        "first_sample_at": selected[0][0] if count else None,
                        "last_sample_at": selected[-1][0] if count else None,
                    }
                endpoints.append(
                    {
                        **endpoint,
                        "state": "unknown" if stale else latest[1],
                        "stale": bool(stale),
                        "checked_at": latest[0] if latest else None,
                        "http_status": latest[2] if latest else None,
                        "latency_ms": latest[3] if latest else None,
                        "windows_hours": windows,
                    }
                )
        return {
            "schema_version": 1,
            "generated_at": now,
            "all_ready": all(item["state"] == "ready" for item in endpoints),
            "collector_fresh": all(not item["stale"] for item in endpoints),
            "interval_seconds": self.interval,
            "endpoints": endpoints,
        }


def handler_for(monitor):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in {"/health", "/ready", "/status", "/uptime"}:
                payload, status = {"error": "not_found"}, 404
            else:
                payload = monitor.report()
                status = 200
                if self.path == "/health":
                    status = 200 if payload["collector_fresh"] else 503
                    payload = {
                        "schema_version": 1,
                        "collector_fresh": payload["collector_fresh"],
                    }
                elif self.path == "/ready":
                    status = 200 if payload["all_ready"] else 503
            body = json.dumps(payload, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(Path(__file__).with_suffix(".yml")))
    parser.add_argument("--database", default="logs/llm-status.sqlite3")
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    monitor = Monitor(read_config(args.config), args.database)
    monitor.sample()
    if args.once:
        report = monitor.report()
        print(json.dumps(report, indent=2))
        return 0 if report["all_ready"] else 1
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(monitor))

    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"LLM status API listening on http://127.0.0.1:{args.port}", flush=True)
    deadline = time.monotonic() + monitor.interval
    try:
        while True:
            time.sleep(max(0, deadline - time.monotonic()))
            # A collector failure exits the process so supervision can restart it.
            monitor.sample()
            deadline = max(deadline + monitor.interval, time.monotonic())
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
