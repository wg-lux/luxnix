import concurrent.futures
import hashlib
import io
from pathlib import Path
import sys
import zipfile

import pytest

SERVICE = Path(__file__).resolve().parents[2] / "modules/nixos/services/lx-terminology"
sys.path.insert(0, str(SERVICE))
from server import create_app, inspect_bundle  # noqa: E402
from publish import bundle_directory  # noqa: E402


def bundle(extra=None, prefix=""):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            prefix + "config.yaml",
            "name: example\nversion: '1.0'\n"
            "medical_field: gastroenterology\nmodules: []\n",
        )
        for name, content in (extra or {}).items():
            archive.writestr(prefix + name, content)
    return output.getvalue()


@pytest.fixture
def app(tmp_path):
    token = tmp_path / "token"
    token.write_text("a" * 48)
    return create_app(
        tmp_path / "packages.db", token, "https://terminology.example.org"
    )


AUTH = {"Authorization": "Bearer " + "a" * 48, "Content-Type": "application/zip"}


def test_publish_catalog_download_and_immutability(app):
    client = app.test_client()
    content = bundle(prefix="editor/")
    assert client.post("/api/packages", data=content).status_code == 401
    published = client.post("/api/packages", data=content, headers=AUTH)
    assert published.status_code == 201
    info = published.json
    assert info["sha256"] == hashlib.sha256(content).hexdigest()
    assert client.get("/api/packages").json == {"packages": [info]}
    response = client.get(f"/packages/{info['sha256']}.zip")
    assert response.data == content
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert (
        client.get(
            f"/packages/{info['sha256']}.zip",
            headers={"If-None-Match": response.headers["ETag"]},
        ).status_code
        == 304
    )
    assert client.post("/api/packages", data=content, headers=AUTH).status_code == 200
    assert (
        client.post(
            "/api/packages", data=bundle({"changed.yaml": "[]"}), headers=AUTH
        ).status_code
        == 409
    )
    assert client.get(f"/packages/{info['sha256']}.zip").data == content


@pytest.mark.parametrize(
    "path", ["../escape", "/absolute", "a/../../escape", "a\\escape"]
)
def test_reject_unsafe_archives(app, path):
    assert (
        app.test_client()
        .post("/api/packages", data=bundle({path: "bad"}), headers=AUTH)
        .status_code
        == 400
    )


def test_reject_symlinks_and_corrupt_zip(app):
    output = io.BytesIO(bundle())
    with zipfile.ZipFile(output, "a") as archive:
        info = zipfile.ZipInfo("link")
        info.external_attr = 0o120777 << 16
        archive.writestr(info, "config.yaml")
    for content in [
        output.getvalue(),
        b"not a zip",
        bundle({"config.yaml/child": "bad"}),
    ]:
        assert (
            app.test_client()
            .post("/api/packages", data=content, headers=AUTH)
            .status_code
            == 400
        )


def test_size_limit_and_preflight(app):
    app.config["MAX_CONTENT_LENGTH"] = 10
    assert (
        app.test_client().post("/api/packages", data=bundle(), headers=AUTH).status_code
        == 413
    )
    response = app.test_client().options(
        "/api/packages", headers={"Origin": "https://editor.example.org"}
    )
    assert response.status_code == 200
    assert "Authorization" in response.headers["Access-Control-Allow-Headers"]


def test_concurrent_publishing_is_atomic(app):
    def upload(index):
        return (
            app.test_client()
            .post("/api/packages", data=bundle({"data.yaml": str(index)}), headers=AUTH)
            .status_code
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        codes = list(pool.map(upload, range(4)))
    assert sorted(codes) == [201, 409, 409, 409]
    assert len(app.test_client().get("/api/packages").json["packages"]) == 1


def test_directory_export_includes_dependency_and_is_deterministic(tmp_path):
    root = tmp_path / "example"
    dependency = tmp_path / "dependency"
    root.mkdir()
    dependency.mkdir()
    (root / "config.yaml").write_text(
        "name: example\nversion: '1.0'\ndepends_on: [dependency]\n"
    )
    (dependency / "config.yaml").write_text("name: dependency\nversion: '2.0'\n")
    content = bundle_directory(root, tmp_path)
    assert content == bundle_directory(root, tmp_path)
    assert inspect_bundle(content) == ("example", "1.0")
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert "_dependencies/dependency/config.yaml" in archive.namelist()
    (dependency / "config.yaml").unlink()
    with pytest.raises(ValueError, match="Missing dependency"):
        bundle_directory(root, tmp_path)


def test_restart_keeps_packages(tmp_path):
    token = tmp_path / "token"
    token.write_text("a" * 48)
    database = tmp_path / "packages.db"
    first = create_app(database, token, "https://terminology.example.org")
    first.test_client().post("/api/packages", data=bundle(), headers=AUTH)
    second = create_app(database, token, "https://terminology.example.org")
    assert len(second.test_client().get("/api/packages").json["packages"]) == 1


def test_empty_token_fails_startup(tmp_path):
    token = tmp_path / "token"
    token.write_text("")
    with pytest.raises(ValueError, match="Upload token"):
        create_app(tmp_path / "packages.db", token, "https://terminology.example.org")
