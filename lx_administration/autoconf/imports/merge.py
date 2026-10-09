"""Merge validated string-keyed Autoconf mappings."""

from typing import cast

from ..errors import AutoconfSourceError

ConfigMapping = dict[str, object]


def require_string_mapping(value: object, label: str) -> ConfigMapping:
    """Return a mapping after validating that all keys are strings."""
    if not isinstance(value, dict):
        raise AutoconfSourceError(f"{label} must be a mapping")
    if any(not isinstance(key, str) for key in value):
        raise AutoconfSourceError(f"{label} must use string keys")
    return cast("ConfigMapping", value)


def deep_update(base: ConfigMapping, updates: ConfigMapping) -> ConfigMapping:
    """Recursively merge updates into a shallow copy of base."""
    merged = base.copy()
    for key, value in updates.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = deep_update(
                require_string_mapping(existing, "Base nested configuration"),
                require_string_mapping(value, "Updated nested configuration"),
            )
        else:
            merged[key] = value
    return merged
