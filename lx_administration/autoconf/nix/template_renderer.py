"""Render Jinja templates with the shared LuxNix literal contract."""

import re
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

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


def nix_string(value: str) -> str:
    """Serialize a value that is semantically required to remain a string."""
    if not isinstance(value, str):
        raise TypeError(f"Expected Nix string, got {type(value).__name__}")
    return _quote_nix_string(value)


def nix_literal(value: object) -> str:
    """Serialize supported configuration values as Nix expressions."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        if "\n" in value:
            return _quote_nix_string(value)
        return value if _is_raw_nix_expression(value) else _quote_nix_string(value)
    if isinstance(value, list):
        return "[ " + " ".join(nix_literal(item) for item in value) + " ]"
    if isinstance(value, dict):
        assignments = [f"{key} = {nix_literal(item)};" for key, item in value.items()]
        return "{ " + " ".join(assignments) + " }"
    raise TypeError(f"Unsupported Nix literal type: {type(value).__name__}")


@dataclass(frozen=True)
class NixAttrEntry:
    """One binding of a nested attribute tree.

    ``name`` may contain several dotted segments when a branch has only one
    child; a branch with several children is rendered as a nested set.
    """

    name: str
    value: object = None
    children: tuple["NixAttrEntry", ...] = ()


def split_attr_path(path: str) -> tuple[str, ...]:
    """Split a dotted Nix attribute path, keeping quoted segments intact."""
    segments: list[str] = []
    current = ""
    in_string = False
    interpolation_depth = 0
    index = 0
    while index < len(path):
        char = path[index]
        if in_string and char == "\\" and index + 1 < len(path):
            current += path[index : index + 2]
            index += 2
            continue
        if in_string and path.startswith("${", index):
            interpolation_depth += 1
            current += "${"
            index += 2
            continue
        if in_string and interpolation_depth and char == "}":
            interpolation_depth -= 1
        elif char == '"' and not interpolation_depth:
            in_string = not in_string
        elif char == "." and not in_string:
            if not current:
                raise ValueError(f"Empty segment in Nix attribute path {path!r}")
            segments.append(current)
            current = ""
            index += 1
            continue
        current += char
        index += 1
    if in_string or interpolation_depth or not current:
        raise ValueError(f"Malformed Nix attribute path {path!r}")
    segments.append(current)
    return tuple(segments)


def _segment_sort_key(segment: str) -> tuple[str, str]:
    return segment.strip('"').lower(), segment


def _attr_entries(
    tree: dict[str, dict], top_level_order: tuple[str, ...] = ()
) -> tuple[NixAttrEntry, ...]:
    def sort_key(segment: str) -> tuple[int, tuple[str, str]]:
        if segment in top_level_order:
            return top_level_order.index(segment), ("", "")
        return len(top_level_order), _segment_sort_key(segment)

    entries = []
    for segment in sorted(tree, key=sort_key):
        node = tree[segment]
        name = segment
        while "value" not in node and len(node["children"]) == 1:
            (child_segment, node), = node["children"].items()
            name = f"{name}.{child_segment}"
        if "value" in node:
            entries.append(NixAttrEntry(name, value=node["value"]))
        else:
            entries.append(NixAttrEntry(name, children=_attr_entries(node["children"])))
    return tuple(entries)


def nix_attr_layers(
    sections: list[tuple[str, dict[str, object]]],
    top_level_order: tuple[str, ...] = (),
) -> list[tuple[NixAttrEntry, ...]]:
    """Group ``(prefix, options)`` sections of dotted paths into nested trees.

    A path below another configured path (for example ``a.b."/x"`` below an
    expression-valued ``a.b``) cannot live in the same attribute set, so it
    is placed in a later layer that the template merges with
    ``lib.recursiveUpdate``. Exact duplicate paths are rejected, including
    the same option configured through two namespaces.
    """
    paths: dict[tuple[str, ...], tuple[str, object]] = {}
    for prefix, options in sections:
        for key, value in options.items():
            path = prefix + key
            segments = split_attr_path(path)
            if segments in paths:
                raise ValueError(f"Duplicate Nix option path {path!r}")
            paths[segments] = (path, value)

    layers: list[dict[str, dict]] = []
    for segments, (_path, value) in paths.items():
        depth = sum(
            1
            for other in paths
            if len(other) < len(segments) and segments[: len(other)] == other
        )
        while len(layers) <= depth:
            layers.append({})
        node = {"children": layers[depth]}
        for segment in segments:
            node = node["children"].setdefault(segment, {"children": {}})
        node["value"] = value
    return [_attr_entries(layer, top_level_order) for layer in layers]


def render_nix_template(
    template_dir: str | Path,
    template_name: str,
    config_data: dict[str, object],
    *,
    filter_name: str = "nix",
    trim_blocks: bool = False,
    lstrip_blocks: bool = False,
) -> str:
    """Render one template using the shared Nix literal serializer."""
    environment = Environment(
        loader=FileSystemLoader(Path(template_dir)),
        undefined=StrictUndefined,
        trim_blocks=trim_blocks,
        lstrip_blocks=lstrip_blocks,
        autoescape=False,
    )
    environment.filters[filter_name] = nix_literal
    environment.filters["nix_string"] = nix_string
    environment.filters["nix_attr_layers"] = nix_attr_layers
    template = environment.get_template(template_name)
    return template.render(**config_data)
