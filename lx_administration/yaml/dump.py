import os
import stat
import subprocess
import tempfile
from collections.abc import Callable
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path

import yaml
from ruamel.yaml import YAML

from lx_administration.permissions import (
    PRIVATE_DIRECTORY_MODE as PRIVATE_DIRECTORY_MODE,
)
from lx_administration.permissions import PRIVATE_FILE_MODE as PRIVATE_FILE_MODE

YamlFileHook = Callable[[Path], None]
YAML_LINE_WIDTH = 4096


class _LuxNixSafeDumper(yaml.SafeDumper):
    """Safe YAML dumper with LuxNix's scalar conventions."""


def _represent_datetime(
    dumper: _LuxNixSafeDumper,
    value: datetime,
) -> yaml.Node:
    return dumper.represent_scalar("tag:yaml.org,2002:str", value.isoformat())


def _represent_timedelta(
    dumper: _LuxNixSafeDumper,
    value: timedelta,
) -> yaml.Node:
    return dumper.represent_scalar("tag:yaml.org,2002:str", f"P{value.days}D")


_LuxNixSafeDumper.add_representer(datetime, _represent_datetime)
_LuxNixSafeDumper.add_representer(timedelta, _represent_timedelta)


def remove_trailing_spaces(content: str) -> str:
    """Remove trailing spaces from each line in the content."""
    return "\n".join(line.rstrip() for line in content.splitlines())


def format_yaml(file: str | Path) -> None:
    """Format YAML file while preserving quotes and removing trailing spaces."""
    file_path = Path(file)
    yaml_parser = YAML(typ="rt")
    yaml_parser.preserve_quotes = True

    with file_path.open("r", encoding="utf-8") as source:
        data = yaml_parser.load(source)

    yaml_parser.indent(mapping=2, sequence=4, offset=2)

    string_stream = StringIO()
    yaml_parser.dump(data, string_stream)
    formatted_content = remove_trailing_spaces(string_stream.getvalue())
    if not formatted_content.endswith("\n"):
        formatted_content += "\n"

    file_path.write_text(formatted_content, encoding="utf-8")


def ansible_lint(file: str | Path) -> None:
    """Run ansible-lint and propagate failures to the caller."""
    subprocess.run(["ansible-lint", str(file)], check=True)


def _target_mode(file_path: Path, requested_mode: int | None) -> int:
    if requested_mode is not None:
        return requested_mode
    if file_path.exists() and not file_path.is_symlink():
        return stat.S_IMODE(file_path.stat().st_mode)
    return 0o644


def dump_yaml(
    data: object,
    file: str | Path,
    format_func: YamlFileHook | None = format_yaml,
    lint_func: YamlFileHook | None = None,
    *,
    directory_mode: int | None = None,
    file_mode: int | None = None,
) -> None:
    """Validate a temporary YAML file before atomically publishing it."""
    file_path = Path(file)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if directory_mode is not None:
        file_path.parent.chmod(directory_mode)

    output_mode = _target_mode(file_path, file_mode)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=file_path.parent,
        prefix=f".{file_path.stem}.",
        suffix=file_path.suffix,
        text=True,
    )
    temporary_path = Path(temporary_name)

    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            os.fchmod(output.fileno(), output_mode)
            yaml.dump(
                data,
                output,
                Dumper=_LuxNixSafeDumper,
                indent=2,
                default_flow_style=False,
                width=YAML_LINE_WIDTH,
            )

        if format_func:
            format_func(temporary_path)

        if lint_func:
            lint_func(temporary_path)

        temporary_path.chmod(output_mode)
        os.replace(temporary_path, file_path)
    finally:
        temporary_path.unlink(missing_ok=True)
