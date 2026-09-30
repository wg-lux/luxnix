"""Public, immutable ZIP distribution; clinical validation belongs to the importer."""

import hashlib
import hmac
import io
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import zipfile

from flask import Flask, abort, jsonify, request, send_file
import yaml

MAX_BYTES = 64 * 1024 * 1024
MAX_UNPACKED = 256 * 1024 * 1024


def inspect_bundle(content: bytes) -> tuple[str, str]:
    """Accept editor ZIPs and root-config ZIPs without extracting uploaded paths."""
    files = {}
    directories = set()
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        if len(archive.infolist()) > 4096:
            raise ValueError("Too many ZIP entries")
        remaining = MAX_UNPACKED
        for entry in archive.infolist():
            raw = entry.orig_filename
            path = PurePosixPath(raw)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in raw
                or "\0" in raw
                or not path.parts
                or stat.S_ISLNK(entry.external_attr >> 16)
            ):
                raise ValueError("Unsafe ZIP path")
            if entry.is_dir():
                continue
            name = path.as_posix()
            parents = {p.as_posix() for p in path.parents if p.parts}
            if name in files or name in directories or parents.intersection(files):
                raise ValueError("Conflicting ZIP paths")
            directories.update(parents)
            if entry.file_size > remaining:
                raise ValueError("Unpacked ZIP too large")
            data = archive.read(entry)
            remaining -= len(data)
            if remaining < 0:
                raise ValueError("Unpacked ZIP too large")
            files[name] = data
    if "config.yaml" not in files and files:
        roots = {name.split("/", 1)[0] for name in files}
        if len(roots) == 1 and all("/" in name for name in files):
            files = {name.split("/", 1)[1]: data for name, data in files.items()}
    config_bytes = files.get("config.yaml", b"")
    if len(config_bytes) > 65536:
        raise ValueError("Root config too large")
    config = yaml.safe_load(config_bytes.decode("utf-8"))
    if not isinstance(config, dict):
        raise ValueError("ZIP requires root config.yaml")
    identity = config.get("name"), config.get("version")
    if any(
        not isinstance(v, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}", v)
        for v in identity
    ):
        raise ValueError("config.yaml requires string name and version")
    return identity


def create_app(database=None, token_file=None, public_url=None):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_BYTES
    database = database or os.environ["LX_TERMINOLOGY_DATABASE"]
    token_file = token_file or os.environ["LX_TERMINOLOGY_TOKEN_FILE"]
    public_url = (public_url or os.environ["LX_TERMINOLOGY_PUBLIC_URL"]).rstrip("/")
    token = Path(token_file).read_text().strip()
    if len(token) < 32 or not token.isascii():
        raise ValueError("Upload token must contain at least 32 ASCII characters")
    with sqlite3.connect(database) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS packages (
            name TEXT NOT NULL, version TEXT NOT NULL, sha256 TEXT NOT NULL,
            content BLOB NOT NULL, PRIMARY KEY (name, version))""")

    def metadata(row):
        name, version, digest, size = row
        return dict(
            name=name,
            version=version,
            sha256=digest,
            size=size,
            url=f"{public_url}/packages/{digest}.zip",
        )

    @app.after_request
    def public_headers(response):
        # No cookie authentication: reads are public, uploads require an explicit token.
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, HEAD, POST, OPTIONS"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/api/packages")
    def catalog():
        with sqlite3.connect(database) as db:
            rows = db.execute(
                "SELECT name, version, sha256, length(content) FROM packages "
                "ORDER BY name, version"
            )
            return jsonify(packages=[metadata(row) for row in rows])

    @app.post("/api/packages")
    def upload():
        supplied = request.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied.encode(), f"Bearer {token}".encode()):
            abort(401)
        content = request.get_data()
        try:
            name, version = inspect_bundle(content)
        except (
            ValueError,
            UnicodeError,
            yaml.YAMLError,
            zipfile.BadZipFile,
            RuntimeError,
            NotImplementedError,
            OSError,
            RecursionError,
        ):
            abort(400, "Invalid terminology ZIP")
        digest = hashlib.sha256(content).hexdigest()
        with sqlite3.connect(database, timeout=30) as db:
            try:
                db.execute(
                    "INSERT INTO packages VALUES (?, ?, ?, ?)",
                    (name, version, digest, content),
                )
            except sqlite3.IntegrityError:
                previous = db.execute(
                    "SELECT sha256 FROM packages WHERE name=? AND version=?",
                    (name, version),
                ).fetchone()
                if previous[0] != digest:
                    abort(409, "Identity already published; increment the version")
                return jsonify(metadata((name, version, digest, len(content)))), 200
        return jsonify(metadata((name, version, digest, len(content)))), 201

    @app.get("/packages/<digest>.zip")
    def download(digest):
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            abort(404)
        with sqlite3.connect(database) as db:
            row = db.execute(
                "SELECT name, version, content FROM packages WHERE sha256=?", (digest,)
            ).fetchone()
        if row is None:
            abort(404)
        return send_file(
            io.BytesIO(row[2]),
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"{row[0]}-{row[1]}.zip",
            etag=digest,
            max_age=31536000,
            conditional=True,
        )

    @app.get("/")
    def index():
        return Path(__file__).with_name("index.html").read_text()

    return app
