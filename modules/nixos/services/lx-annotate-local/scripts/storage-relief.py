from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class ReliefResourceKind(str, Enum):
    VIDEO = "video"
    REPORT = "report"


def parse_resource_kind(value: object) -> ReliefResourceKind | None:
    try:
        return ReliefResourceKind(str(value).lower())
    except ValueError:
        return None


def emit(event: str, **payload: object) -> None:
    record = {"event": event, **payload}
    print(json.dumps(record, sort_keys=True), flush=True)


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("storage relief config must be a JSON object")
    return data


def setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lx_annotate.settings.settings_prod")
    import django

    django.setup()


def state_is_processed_anonymized(state: object | None) -> bool:
    if state is None:
        return False
    return bool(
        getattr(state, "anonymization_validated", False)
        or getattr(state, "sensitive_meta_processed", False)
        or getattr(state, "anonymized", False)
    )


def state_is_validated(state: object | None) -> bool:
    return bool(state is not None and getattr(state, "anonymization_validated", False))


def field_name_keys(field_name: str) -> set[str]:
    normalized = field_name.strip("/")
    keys = {normalized, Path(normalized).name}
    parts = normalized.split("/", 1)
    if len(parts) == 2:
        keys.add(parts[1])
    return {key for key in keys if key}


def archive_destination(root: Path, category: str, label: str, rel_path: Path, content_hash: str) -> Path:
    destination = root / category / label / rel_path
    if not destination.exists():
        return destination
    return destination.with_name(f"{destination.name}.{content_hash[:16]}")


def staging_destination(staging_root: Path, archive_root: Path, destination: Path, content_hash: str) -> Path:
    final_rel_path = destination.resolve().relative_to(archive_root.resolve())
    staged = staging_root / final_rel_path
    return staged.with_name(f"{staged.name}.{os.getpid()}.{content_hash[:16]}.staging")


def ensure_archive_path(path: Path, archive_root: Path) -> None:
    resolved_path = path.resolve()
    resolved_archive = archive_root.resolve()
    if resolved_path == resolved_archive or resolved_archive in resolved_path.parents:
        return
    raise ValueError(f"refusing to write outside archive root: {path}")


def resource_identifier(kind: ReliefResourceKind, obj: object) -> str:
    return f'{kind.value}:{getattr(obj, "pk", "")}'


def build_eligible_resources() -> dict[str, dict[str, dict[str, Any]]]:
    from endoreg_db.models import RawPdfFile, VideoFile

    resources: dict[str, dict[str, dict[str, Any]]] = {
        kind.value: {} for kind in ReliefResourceKind
    }

    videos = (
        VideoFile.objects.select_related("state")
        .exclude(processed_file="")
        .exclude(processed_file__isnull=True)
        .order_by("pk")
    )
    for video in videos.iterator():
        field = getattr(video, "processed_file", None)
        field_name = str(getattr(field, "name", "") or "")
        if not field_name or not state_is_processed_anonymized(getattr(video, "state", None)):
            continue
        record = {
            "kind": ReliefResourceKind.VIDEO.value,
            "object": video,
            "field_file": field,
            "content_hash": getattr(video, "processed_video_hash", None) or None,
            "validated": state_is_validated(getattr(video, "state", None)),
            "identifier": resource_identifier(ReliefResourceKind.VIDEO, video),
        }
        for key in field_name_keys(field_name):
            resources[ReliefResourceKind.VIDEO.value][key] = record

    reports = (
        RawPdfFile.objects.select_related("state")
        .exclude(processed_file="")
        .exclude(processed_file__isnull=True)
        .order_by("pk")
    )
    for report in reports.iterator():
        field = getattr(report, "processed_file", None)
        field_name = str(getattr(field, "name", "") or "")
        if not field_name or not state_is_processed_anonymized(getattr(report, "state", None)):
            continue
        record = {
            "kind": ReliefResourceKind.REPORT.value,
            "object": report,
            "field_file": field,
            "content_hash": None,
            "validated": state_is_validated(getattr(report, "state", None)),
            "identifier": resource_identifier(ReliefResourceKind.REPORT, report),
        }
        for key in field_name_keys(field_name):
            resources[ReliefResourceKind.REPORT.value][key] = record

    return resources


def get_record_hash(record: dict[str, Any]) -> str:
    cached = record.get("content_hash")
    if cached:
        return str(cached)
    from endoreg_db.utils.file_operations import sha256_file

    digest = sha256_file(record["field_file"])
    record["content_hash"] = digest
    return digest


def copy_verify_delete(
    *,
    source: Path,
    destination: Path,
    archive_root: Path,
    staging_root: Path,
    dry_run: bool,
    delete_after_verify: bool,
    expected_hash: str | None,
) -> dict[str, Any]:
    from endoreg_db.utils.file_operations import (
        atomic_copy_file,
        atomic_move_file,
        safe_unlink_file,
        sha256_file,
    )

    ensure_archive_path(destination, archive_root)
    ensure_archive_path(staging_root, archive_root)
    size_bytes = source.stat().st_size
    source_hash = sha256_file(source)
    if expected_hash is not None and source_hash != expected_hash:
        return {
            "status": "skipped",
            "reason": "source hash does not match eligible database payload",
            "source": str(source),
            "source_hash": source_hash,
            "expected_hash": expected_hash,
        }

    if dry_run:
        return {
            "status": "planned",
            "source": str(source),
            "destination": str(destination),
            "source_hash": source_hash,
            "bytes": size_bytes,
        }

    staged = staging_destination(staging_root, archive_root, destination, source_hash)
    ensure_archive_path(staged, archive_root)
    try:
        atomic_copy_file(
            source=source,
            destination=staged,
            preserve_metadata=True,
            file_mode=0o640,
            dir_mode=0o750,
        )
        staged_hash = sha256_file(staged)
        if staged_hash != source_hash:
            raise RuntimeError(
                f"staging hash verification failed for {source}: {staged_hash} != {source_hash}"
            )
        atomic_move_file(
            source=staged,
            destination=destination,
            file_mode=0o640,
            dir_mode=0o750,
        )
    except Exception:
        if staged.exists():
            safe_unlink_file(staged, missing_ok=True)
        raise

    destination_hash = sha256_file(destination)
    if destination_hash != source_hash:
        raise RuntimeError(
            f"archive hash verification failed for {source}: {destination_hash} != {source_hash}"
        )

    deleted = False
    if delete_after_verify:
        safe_unlink_file(source, missing_ok=False)
        deleted = True

    return {
        "status": "archived",
        "source": str(source),
        "destination": str(destination),
        "staging": str(staged),
        "source_hash": source_hash,
        "bytes": size_bytes,
        "deleted": deleted,
    }


def archive_legacy_duplicates(
    *,
    config: dict[str, Any],
    resources: dict[str, dict[str, dict[str, Any]]],
    archive_root: Path,
    staging_root: Path,
    dry_run: bool,
    delete_after_verify: bool,
    ) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for source_config in config.get("legacy_duplicate_sources", []):
        kind = parse_resource_kind(source_config["kind"])
        if kind is None:
            emit(
                "lx_annotate_storage_relief_skip",
                reason="unknown legacy duplicate source kind",
                kind=str(source_config["kind"]),
            )
            continue
        source_root = Path(str(source_config["source_root"]))
        label = str(source_config["label"]).strip("/")
        if not source_root.is_dir():
            emit(
                "lx_annotate_storage_relief_skip",
                reason="legacy source missing",
                source_root=str(source_root),
                kind=kind.value,
            )
            continue

        for source in sorted(path for path in source_root.rglob("*") if path.is_file()):
            rel_path = source.relative_to(source_root)
            keys = {rel_path.as_posix(), source.name}
            record = next(
                (
                    resources.get(kind.value, {}).get(key)
                    for key in keys
                    if resources.get(kind.value, {}).get(key)
                ),
                None,
            )
            if record is None:
                items.append(
                    {
                        "status": "skipped",
                        "reason": "no eligible database payload",
                        "kind": kind.value,
                        "source": str(source),
                    }
                )
                continue

            expected_hash = get_record_hash(record)
            source_hash = None
            destination = archive_destination(
                archive_root,
                "duplicates",
                label,
                rel_path,
                expected_hash,
            )
            result = copy_verify_delete(
                source=source,
                destination=destination,
                archive_root=archive_root,
                staging_root=staging_root,
                dry_run=dry_run,
                delete_after_verify=delete_after_verify,
                expected_hash=expected_hash,
            )
            result.update(
                {
                    "kind": kind.value,
                    "category": "legacy_processed_duplicate",
                    "resource": record["identifier"],
                    "label": label,
                }
            )
            if result.get("source_hash"):
                source_hash = result["source_hash"]
            emit("lx_annotate_storage_relief_item", **result)
            items.append(result)
            if source_hash and result["status"] == "skipped":
                continue
    return items


def marker_payload(marker: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except Exception as exc:
        emit(
            "lx_annotate_storage_relief_skip",
            reason="invalid export marker json",
            marker=str(marker),
            detail=str(exc),
        )
        return None
    if not isinstance(payload, dict) or payload.get("validated") is not True:
        return None
    return payload


def marker_resources(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_resources = payload.get("resources")
    if raw_resources is None:
        raw_resources = [
            {
                "kind": payload.get("resource_kind"),
                "id": payload.get("resource_id"),
            }
        ]
    if not isinstance(raw_resources, list):
        return []
    return [item for item in raw_resources if isinstance(item, dict)]


def resource_is_validated(resource: dict[str, Any]) -> bool:
    from endoreg_db.models import RawPdfFile, VideoFile

    kind = parse_resource_kind(resource.get("kind") or resource.get("resource_kind"))
    pk = resource.get("id", resource.get("pk", resource.get("resource_id")))
    if kind is None or pk in {None, ""}:
        return False
    if kind is ReliefResourceKind.VIDEO:
        model = VideoFile
    elif kind is ReliefResourceKind.REPORT:
        model = RawPdfFile
    else:
        raise ValueError(f"unhandled relief resource kind: {kind.value}")
    obj = model.objects.select_related("state").filter(pk=pk).first()
    return bool(obj is not None and state_is_validated(getattr(obj, "state", None)))


def find_validated_bundle_roots(export_dir: Path, marker_names: list[str]) -> list[tuple[Path, Path]]:
    bundles: list[tuple[Path, Path]] = []
    if not export_dir.is_dir():
        return bundles
    for root, dirs, files in os.walk(export_dir):
        root_path = Path(root)
        marker_name = next((name for name in marker_names if name in files), None)
        if marker_name is None:
            continue
        bundles.append((root_path, root_path / marker_name))
        dirs[:] = []
    return bundles


def archive_validated_export_bundles(
    *,
    config: dict[str, Any],
    archive_root: Path,
    staging_root: Path,
    dry_run: bool,
    delete_after_verify: bool,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    marker_names = [str(name) for name in config.get("validated_export_marker_names", [])]
    for export_dir_value in config.get("validated_export_dirs", []):
        export_dir = Path(str(export_dir_value))
        for bundle_root, marker in find_validated_bundle_roots(export_dir, marker_names):
            payload = marker_payload(marker)
            if payload is None:
                continue
            resources = marker_resources(payload)
            if not resources or not all(resource_is_validated(resource) for resource in resources):
                emit(
                    "lx_annotate_storage_relief_skip",
                    reason="export bundle resources are not validated",
                    bundle_root=str(bundle_root),
                    marker=str(marker),
                )
                continue

            bundle_label = bundle_root.relative_to(export_dir).as_posix()
            if bundle_label == ".":
                bundle_label = export_dir.name
            for source in sorted(path for path in bundle_root.rglob("*") if path.is_file()):
                rel_path = source.relative_to(bundle_root)
                destination = archive_destination(
                    archive_root,
                    "validated-export-bundles",
                    bundle_label,
                    rel_path,
                    datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
                )
                result = copy_verify_delete(
                    source=source,
                    destination=destination,
                    archive_root=archive_root,
                    staging_root=staging_root,
                    dry_run=dry_run,
                    delete_after_verify=delete_after_verify,
                    expected_hash=None,
                )
                result.update(
                    {
                        "category": "validated_export_bundle",
                        "bundle_root": str(bundle_root),
                        "marker": str(marker),
                    }
                )
                emit("lx_annotate_storage_relief_item", **result)
                items.append(result)
    return items


def write_manifest(
    manifest_dir: Path,
    archive_root: Path,
    staging_root: Path,
    dry_run: bool,
    items: list[dict[str, Any]],
) -> Path:
    from endoreg_db.utils.file_operations import atomic_write_file, ensure_directory

    ensure_directory(manifest_dir, dir_mode=0o750)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest = {
        "schema": "lx_annotate_emergency_storage_relief.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "archive_root": str(archive_root),
        "staging_root": str(staging_root),
        "dry_run": dry_run,
        "items": items,
        "archived_count": sum(1 for item in items if item.get("status") == "archived"),
        "planned_count": sum(1 for item in items if item.get("status") == "planned"),
        "skipped_count": sum(1 for item in items if item.get("status") == "skipped"),
        "freed_bytes": sum(int(item.get("bytes", 0)) for item in items if item.get("deleted") is True),
    }
    payload = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    destination = manifest_dir / f"{timestamp}.json"
    atomic_write_file(
        destination=destination,
        content=[payload],
        required_bytes=len(payload),
        file_mode=0o640,
        dir_mode=0o750,
    )
    return destination


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config = load_config(Path(args.config))
    archive_root = Path(str(config["archive_root"]))
    manifest_dir = Path(str(config["manifest_dir"]))
    staging_root = Path(str(config["staging_dir"]))
    dry_run = bool(config.get("dry_run", False))
    delete_after_verify = bool(config.get("delete_after_verify", True))

    setup_django()
    items: list[dict[str, Any]] = []
    resources = build_eligible_resources()

    emit(
        "lx_annotate_storage_relief_start",
        archive_root=str(archive_root),
        staging_root=str(staging_root),
        dry_run=dry_run,
        eligible_videos=len(resources["video"]),
        eligible_reports=len(resources["report"]),
    )

    if config.get("include_legacy_processed_duplicates", True):
        items.extend(
            archive_legacy_duplicates(
                config=config,
                resources=resources,
                archive_root=archive_root,
                staging_root=staging_root,
                dry_run=dry_run,
                delete_after_verify=delete_after_verify,
            )
        )

    if config.get("include_validated_export_bundles", True):
        items.extend(
            archive_validated_export_bundles(
                config=config,
                archive_root=archive_root,
                staging_root=staging_root,
                dry_run=dry_run,
                delete_after_verify=delete_after_verify,
            )
        )

    manifest_path = write_manifest(manifest_dir, archive_root, staging_root, dry_run, items)
    emit(
        "lx_annotate_storage_relief_complete",
        manifest=str(manifest_path),
        archived_count=sum(1 for item in items if item.get("status") == "archived"),
        planned_count=sum(1 for item in items if item.get("status") == "planned"),
        skipped_count=sum(1 for item in items if item.get("status") == "skipped"),
        freed_bytes=sum(int(item.get("bytes", 0)) for item in items if item.get("deleted") is True),
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        emit("lx_annotate_storage_relief_error", detail=str(exc))
        raise
