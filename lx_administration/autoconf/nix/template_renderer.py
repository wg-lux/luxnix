from jinja2 import Environment, FileSystemLoader
from typing import Dict, Any
import re


_RAW_NIX_STRING_VALUES = {"true", "false", "null", "{}", "[]"}
_RAW_NIX_STRING_PREFIXES = (
    '"',
    "''",
    "'",
    "./",
    "../",
    "/",
    "pkgs.",
    "lib.",
    "config.",
    "inputs.",
    "{",
    "[",
    "(",
)


def _is_raw_nix_expression(value: str) -> bool:
    stripped = value.strip()
    if stripped in _RAW_NIX_STRING_VALUES:
        return True
    if re.fullmatch(r"-?[0-9]+(\.[0-9]+)?", stripped):
        return True
    return stripped.startswith(_RAW_NIX_STRING_PREFIXES)


def _quote_nix_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def nix_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value if _is_raw_nix_expression(value) else _quote_nix_string(value)
    if isinstance(value, list):
        return "[ " + " ".join(nix_literal(item) for item in value) + " ]"
    if isinstance(value, dict):
        assignments = [
            f"{key} = {nix_literal(item)};"
            for key, item in value.items()
        ]
        return "{ " + " ".join(assignments) + " }"
    return str(value)


def render_nix_template(
    template_dir: str, template_name: str, config_data: Dict[str, Any]
) -> str:
    env = Environment(loader=FileSystemLoader(template_dir))
    env.filters["nix"] = nix_literal
    template = env.get_template(template_name)
    return template.render(**config_data)
