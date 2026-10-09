#!/usr/bin/env bash
set -euo pipefail

# Read-only forensic audit for HLS materialization failures.  The helper is
# streamed to the service account so it can read the DB password without
# making this checkout accessible from /home/admin.

SERVICE_USER="${SERVICE_USER:-endoreg-service-user}"
SERVICE_PYTHON="${SERVICE_PYTHON:-/var/endoreg-service-user/lx-annotate-wheel/.venv/bin/python}"

usage() {
  cat <<'EOF'
Usage:
  scripts/audit-lx-annotate-hls-payloads.sh [options] > hls-failed-payloads.tsv

Audits failed LX Annotate HLS artifact rows using a read-only database
transaction. For each row it maps the selected raw/processed payload and
reads at most 32 bytes to classify it as current_lxenc01, mp4_plain_media,
or unknown_legacy_envelope. It does not decrypt, alter, or hash video files.

Options:
  --include-non-ready    Audit queued/materializing rows too, not only failed rows.
  --all-statuses         Audit ready rows too; useful when a ready playlist is missing.
  --video-id ID          Restrict the audit to one video ID.
  --format FORMAT        Output format: tsv (default) or jsonl.
  --show-header-hex      Include the 32-byte prefix as hex for unknown-envelope triage.
  --storage-root PATH    Encrypted storage root.
  --db-host HOST         PostgreSQL host.
  --db-port PORT         PostgreSQL port.
  --db-name NAME         PostgreSQL database name.
  --db-user USER         PostgreSQL user.
  --db-password-file P  Password file readable only by the service account.
  --help, -h             Show this help.

Examples:
  scripts/audit-lx-annotate-hls-payloads.sh > /var/tmp/hls-failed-payloads.tsv
  scripts/audit-lx-annotate-hls-payloads.sh --show-header-hex --format jsonl \
    > /var/tmp/hls-failed-payloads.jsonl
  scripts/audit-lx-annotate-hls-payloads.sh --video-id 51 --all-statuses
EOF
}

if [[ $# -gt 0 && ( "$1" == "--help" || "$1" == "-h" ) ]]; then
  usage
  exit 0
fi

if [[ ! -x "${SERVICE_PYTHON}" ]]; then
  printf 'Service Python is not executable: %s\n' "${SERVICE_PYTHON}" >&2
  exit 1
fi

if [[ "$(id -un)" == "${SERVICE_USER}" ]]; then
  runner=("${SERVICE_PYTHON}" - "$@")
else
  runner=(sudo -u "${SERVICE_USER}" -- "${SERVICE_PYTHON}" - "$@")
fi

"${runner[@]}" <<'PY'
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


DEFAULTS = {
    "db_host": "localhost",
    "db_port": 5432,
    "db_name": "endoregDbLocal",
    "db_user": "endoregDbLocal",
    "db_password_file": "/var/endoreg-service-user/lx-annotate-wheel/conf/db_pwd",
    "storage_root": "/var/lib/lx-annotate/data/storage",
}
HEADER_READ_SIZE = 32
LXENC_MAGIC = b"LXENC01\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only audit of failed LX Annotate HLS rows and their managed "
            "payload headers."
        )
    )
    parser.add_argument(
        "--include-non-ready",
        action="store_true",
        help="include queued and materializing rows in addition to failed rows",
    )
    parser.add_argument(
        "--all-statuses",
        action="store_true",
        help="include ready rows too; takes precedence over --include-non-ready",
    )
    parser.add_argument("--video-id", type=int, help="restrict the audit to one video")
    parser.add_argument("--format", choices=("tsv", "jsonl"), default="tsv")
    parser.add_argument(
        "--show-header-hex",
        action="store_true",
        help="include the first 32 bytes as hex; omit this for the minimum report",
    )
    parser.add_argument("--storage-root", default=DEFAULTS["storage_root"])
    parser.add_argument("--db-host", default=DEFAULTS["db_host"])
    parser.add_argument("--db-port", type=int, default=DEFAULTS["db_port"])
    parser.add_argument("--db-name", default=DEFAULTS["db_name"])
    parser.add_argument("--db-user", default=DEFAULTS["db_user"])
    parser.add_argument("--db-password-file", default=DEFAULTS["db_password_file"])
    return parser.parse_args()


def resolve_managed_path(storage_root: Path, stored_name: str) -> tuple[Path | None, str]:
    if not stored_name:
        return None, "missing_file_field"

    candidate = Path(stored_name)
    resolved = candidate.resolve() if candidate.is_absolute() else (storage_root / candidate).resolve()
    try:
        resolved.relative_to(storage_root)
    except ValueError:
        return None, "path_outside_storage_root"
    return resolved, ""


def classify_path(path: Path | None, path_note: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "source_path": str(path) if path is not None else "",
        "source_size_bytes": "",
        "header_class": "",
        "read_note": path_note,
        "header_prefix_hex": "",
    }
    if path is None:
        result["header_class"] = "unavailable"
        return result

    try:
        stat_result = path.stat()
        if not path.is_file():
            result["header_class"] = "unavailable"
            result["read_note"] = "not_a_regular_file"
            return result
        with path.open("rb") as payload:
            prefix = payload.read(HEADER_READ_SIZE)
    except FileNotFoundError:
        result["header_class"] = "unavailable"
        result["read_note"] = "file_missing"
        return result
    except PermissionError:
        result["header_class"] = "unavailable"
        result["read_note"] = "permission_denied"
        return result
    except OSError as exc:
        result["header_class"] = "unavailable"
        result["read_note"] = f"read_error:{exc.errno or 'unknown'}"
        return result

    result["source_size_bytes"] = stat_result.st_size
    result["read_note"] = ""
    result["header_prefix_hex"] = prefix.hex()
    if prefix.startswith(LXENC_MAGIC):
        result["header_class"] = "current_lxenc01"
    elif len(prefix) >= 8 and prefix[4:8] == b"ftyp":
        result["header_class"] = "mp4_plain_media"
    else:
        result["header_class"] = "unknown_legacy_envelope"
    return result


def read_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    password_path = Path(args.db_password_file)
    try:
        password = password_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"cannot read DB password file: {exc.strerror or exc}") from exc
    if not password:
        raise RuntimeError("DB password file is empty")

    conditions: list[str] = []
    query_params: list[Any] = []
    if not args.all_statuses:
        conditions.append(
            "a.status <> 'ready'" if args.include_non_ready else "a.status = 'failed'"
        )
    if args.video_id is not None:
        conditions.append("a.video_id = %s")
        query_params.append(args.video_id)
    where_clause = " AND ".join(conditions) if conditions else "TRUE"
    query = f"""
        SELECT
            a.id AS hls_artifact_id,
            a.video_id,
            a.artifact_kind,
            a.status AS hls_status,
            a.source_file_name AS hls_source_file_name,
            a.last_error,
            a.updated_at AS hls_updated_at,
            v.original_file_name AS video_original_file_name,
            v.raw_file,
            v.processed_file
        FROM endoreg_db_videohlsartifact AS a
        INNER JOIN endoreg_db_videofile AS v ON v.id = a.video_id
        WHERE {where_clause}
        ORDER BY a.video_id ASC, a.artifact_kind ASC
    """
    connection_args = {
        "host": args.db_host,
        "port": args.db_port,
        "dbname": args.db_name,
        "user": args.db_user,
        "password": password,
        "row_factory": dict_row,
    }
    try:
        with psycopg.connect(**connection_args, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute("BEGIN READ ONLY")
                cursor.execute(query, query_params)
                rows = list(cursor.fetchall())
                cursor.execute("COMMIT")
    finally:
        password = ""
    return rows


def make_report_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    storage_root = Path(args.storage_root).resolve()
    rows = read_rows(args)
    report: list[dict[str, Any]] = []
    for row in rows:
        source_field = "raw_file" if row["artifact_kind"] == "raw" else "processed_file"
        stored_file_name = str(row[source_field] or "")
        path, path_note = resolve_managed_path(storage_root, stored_file_name)
        record = {
            "hls_artifact_id": row["hls_artifact_id"],
            "video_id": row["video_id"],
            "artifact_kind": row["artifact_kind"],
            "hls_status": row["hls_status"],
            "hls_updated_at": row["hls_updated_at"].isoformat(),
            "video_original_file_name": row["video_original_file_name"] or "",
            "hls_source_file_name": row["hls_source_file_name"] or "",
            "source_field": source_field,
            "stored_file_name": stored_file_name,
            "last_error": row["last_error"] or "",
        }
        record.update(classify_path(path, path_note))
        if not args.show_header_hex:
            record.pop("header_prefix_hex")
        report.append(record)
    return report


def write_report(
    rows: list[dict[str, Any]], output_format: str, show_header_hex: bool
) -> None:
    if output_format == "jsonl":
        for row in rows:
            print(json.dumps(row, sort_keys=True, default=str))
        return

    fieldnames = [
        "hls_artifact_id",
        "video_id",
        "artifact_kind",
        "hls_status",
        "hls_updated_at",
        "video_original_file_name",
        "hls_source_file_name",
        "source_field",
        "stored_file_name",
        "source_path",
        "source_size_bytes",
        "header_class",
        "read_note",
        "last_error",
    ]
    if show_header_hex:
        fieldnames.append("header_prefix_hex")
    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames, dialect="excel-tab")
    writer.writeheader()
    writer.writerows(rows)


def main() -> int:
    args = parse_args()
    try:
        rows = make_report_rows(args)
    except Exception as exc:
        print(f"audit failed: {exc}", file=sys.stderr)
        return 1
    write_report(rows, args.format, args.show_header_hex)
    print(f"audited_hls_rows={len(rows)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY
