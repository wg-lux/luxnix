"""Unambiguous YAML loading for LuxNix configuration files."""

from pathlib import Path

import yaml


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[object, object]:
    loader.flatten_mapping(node)
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_unique_yaml(content: str) -> object:
    """Load safe YAML while rejecting ambiguous duplicate keys."""
    return yaml.load(content, Loader=UniqueKeyLoader)


def load_unique_yaml_file(path: Path) -> object:
    """Load one UTF-8 YAML file while rejecting duplicate keys."""
    with path.open("r", encoding="utf-8") as source:
        return yaml.load(source, Loader=UniqueKeyLoader)
