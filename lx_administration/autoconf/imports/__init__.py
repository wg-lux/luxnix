# Avoid eager imports here to prevent circular imports when models import this package.
# Expose selected helpers lazily via lightweight wrappers.

__all__ = [
    "load_all_host_facts",
    "load_inventory_hostfile",
]


def load_all_host_facts(*args, **kwargs):  # type: ignore[no-redef]
    from .ansible_facts import load_all_host_facts as _impl

    return _impl(*args, **kwargs)


def load_inventory_hostfile(*args, **kwargs):  # type: ignore[no-redef]
    from .ansible_inventory import load_inventory_hostfile as _impl

    return _impl(*args, **kwargs)
