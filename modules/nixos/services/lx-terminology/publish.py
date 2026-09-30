"""Publish an editor ZIP or a self-contained bundle from lx_dtypes/data at runtime."""

import argparse
import io
from pathlib import Path
import urllib.request
import zipfile

import yaml

from server import MAX_BYTES, inspect_bundle


def bundle_directory(root: Path, data_root: Path) -> bytes:
    root = root.resolve()
    data_root = data_root.resolve()
    root.relative_to(data_root)
    files: dict[str, bytes] = {}
    included: set[Path] = set()
    identities: dict[str, Path] = {}
    candidates: dict[str, list[Path]] = {}
    for config_path in sorted(data_root.rglob("config.yaml")):
        if config_path.relative_to(data_root).parts[0] == "versions":
            continue
        config = yaml.safe_load(config_path.read_text())
        candidates.setdefault(config["name"], []).append(config_path.parent)

    def add(directory: Path, prefix: str) -> None:
        directory = directory.resolve()
        directory.relative_to(data_root)
        if directory in included:
            return
        included.add(directory)
        # Preserve the source bundle and include referenced external modules below it.
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"Symlinks are not publishable: {path}")
            if path.is_file():
                name = prefix + path.relative_to(directory).as_posix()
                if name in files:
                    raise ValueError(f"Conflicting bundle path: {name}")
                files[name] = path.read_bytes()
        configs = sorted(directory.rglob("config.yaml"))
        for config_path in configs:
            config = yaml.safe_load(config_path.read_text())
            name = config["name"]
            if name in identities and identities[name] != config_path:
                raise ValueError(f"Multiple versions of dependency {name}")
            identities[name] = config_path
        for config_path in configs:
            config = yaml.safe_load(config_path.read_text())
            for dependency in [
                *config.get("modules", []),
                *config.get("depends_on", []),
            ]:
                if dependency in identities:
                    continue
                if (
                    not isinstance(dependency, str)
                    or Path(dependency).name != dependency
                ):
                    raise ValueError("Invalid dependency name")
                matches = candidates.get(dependency, [])
                if not matches:
                    raise ValueError(f"Missing dependency: {dependency}")
                if len(matches) != 1:
                    raise ValueError(f"Ambiguous dependency: {dependency}")
                add(matches[0], f"_dependencies/{dependency}/")

    add(root, "")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            # Stable ZIP metadata makes publishing an unchanged source idempotent.
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    content = output.getvalue()
    if len(content) > MAX_BYTES:
        raise ValueError("Bundle exceeds upload limit")
    inspect_bundle(content)
    return content


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source", type=Path, help="Editor ZIP or knowledge-base directory"
    )
    parser.add_argument(
        "--data-root", type=Path, help="lx-data-models/lx_dtypes/data (for directories)"
    )
    parser.add_argument("--server", required=True, help="Public HTTPS server URL")
    parser.add_argument("--token-file", required=True, type=Path)
    args = parser.parse_args()
    if not args.server.startswith("https://"):
        parser.error("--server must use HTTPS")
    if args.source.is_dir():
        if args.data_root is None:
            parser.error("--data-root is required for directory publication")
        content = bundle_directory(args.source, args.data_root)
    else:
        with args.source.open("rb") as source:
            content = source.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            parser.error("ZIP exceeds upload limit")
        inspect_bundle(content)
    request = urllib.request.Request(
        args.server.rstrip("/") + "/api/packages",
        data=content,
        headers={
            "Authorization": "Bearer " + args.token_file.read_text().strip(),
            "Content-Type": "application/zip",
        },
    )

    # Do not forward the publisher credential through redirects.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    with urllib.request.build_opener(NoRedirect).open(request, timeout=120) as response:
        print(response.read().decode())


if __name__ == "__main__":
    main()
