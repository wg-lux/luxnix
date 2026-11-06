import importlib.util
import json
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest


spec = importlib.util.spec_from_file_location(
    "llm_status", Path(__file__).parents[1] / "scripts/llm-status.py"
)
status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status)


@pytest.fixture
def endpoint_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            code, body = {
                "/ok": (200, b'{"status":"ok"}'),
                "/version": (200, b'{"version":"1.0"}'),
                "/loading": (503, b'{"error":"Loading model"}'),
                "/auth": (403, b"Forbidden"),
                "/login": (302, b""),
                "/html": (200, b"<html>Login</html>"),
                "/array": (200, b"[]"),
                "/truncated": (200, b'{"status":'),
            }[self.path]
            self.send_response(code)
            self.send_header("Location", "/ok")
            if self.path == "/truncated":
                self.send_header("Content-Length", "100")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join()
    server.server_close()


@pytest.mark.parametrize(
    "path,check,expected",
    [
        ("/ok", "glm", "ready"),
        ("/version", "ollama", "ready"),
        ("/loading", "glm", "unavailable"),
        ("/auth", "glm", "authentication_required"),
        ("/login", "glm", "redirect"),
        ("/html", "glm", "invalid_response"),
        ("/array", "ollama", "invalid_response"),
        ("/version", "glm", "invalid_response"),
        ("/truncated", "glm", "invalid_response"),
    ],
)
def test_readiness_requires_valid_response(endpoint_server, path, check, expected):
    assert (
        status.probe({"url": endpoint_server + path, "check": check}, 1)["state"]
        == expected
    )


def monitor_at(tmp_path):
    config = status.read_config(Path(__file__).parents[1] / "scripts/llm-status.yml")
    config["endpoints"] = config["endpoints"][:1]
    return status.Monitor(config, tmp_path / "samples.sqlite3")


def test_persistence_staleness_and_missing_history(tmp_path):
    monitor = monitor_at(tmp_path)
    endpoint = monitor.config["endpoints"][0]
    with monitor.connect() as db:
        db.executemany(
            "INSERT INTO samples VALUES (?, ?, ?, ?, ?, ?)",
            [
                (endpoint["id"], endpoint["url"], 1000, "ready", 200, 10),
                (endpoint["id"], endpoint["url"], 1060, "unavailable", 503, 10),
            ],
        )
    report = monitor_at(tmp_path).report(now=1070)
    result = report["endpoints"][0]
    window = result["windows_hours"]["1"]
    assert result["state"] == "unavailable"
    assert window["sampled_availability_percent"] == 50
    assert window["samples"] == 2
    assert window["expected_samples"] == 60
    assert monitor.report(now=1300)["endpoints"][0]["state"] == "unknown"
    assert not monitor.report(now=1300)["collector_fresh"]
    endpoint["url"] = "http://127.0.0.1:1234/changed"
    assert (
        monitor.report(now=1070)["endpoints"][0]["windows_hours"]["1"]["samples"] == 0
    )


def test_api_remains_json_when_targets_fail(tmp_path):
    monitor = monitor_at(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), status.handler_for(monitor))
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        for path, expected in [
            ("/status", 200),
            ("/uptime", 200),
            ("/ready", 503),
            ("/health", 503),
            ("/status?url=http://example.com", 404),
        ]:
            try:
                response = urlopen(
                    f"http://127.0.0.1:{server.server_port}{path}", timeout=2
                )
            except HTTPError as error:
                response = error
            with response:
                assert response.status == expected
                assert response.headers["Cache-Control"] == "no-store"
                assert isinstance(json.load(response), dict)
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
