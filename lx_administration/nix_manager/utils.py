from pathlib import Path
from yaml import safe_load

TEMPLATE_LOOKUP = {
    "gc-06": "gpu-client-dev",
    "gc-07": "gpu-client-dev",
    "gc-08": "gpu-client-dev",
    # "gc-09": "gpu-client-dev",
    # Fallback if no specific template is found:
    "s-": "base-server",
    "gc-": "gpu-client-dev",
    "gs-": "gpu-server",
    "h-": "hetzner-server",
}


def get_ansible_inventory_dir(ansible_root: Path) -> Path:
    inventory_dir = ansible_root / "inventory"

    return inventory_dir


def get_ansible_group_vars_dir(ansible_root: Path) -> Path:
    _ = get_ansible_inventory_dir(ansible_root)
    group_vars_dir = _ / "group_vars"
    return group_vars_dir


def get_ansible_host_vars_dir(ansible_root: Path) -> Path:
    _ = get_ansible_inventory_dir(ansible_root)
    host_vars_dir = _ / "host_vars"
    return host_vars_dir


def get_ansible_group_vars_file(hostname: str, ansible_root: Path) -> Path:
    group_vars_dir = get_ansible_group_vars_dir(ansible_root)
    group_vars_file = group_vars_dir / f"{hostname}.yml"
    assert group_vars_file.is_file()

    return group_vars_file


def get_ansible_host_vars_file(hostname: str, ansible_root: Path) -> Path:
    host_vars_dir = get_ansible_host_vars_dir(ansible_root)
    host_vars_file = host_vars_dir / f"{hostname}.yml"
    assert host_vars_file.is_file(), f"Host vars file not found: {host_vars_file}"

    return host_vars_file


def get_ansible_inventory_file(hostname: str, ansible_root: Path) -> Path:
    inventory_dir = get_ansible_inventory_dir(hostname, ansible_root)
    inventory_file = inventory_dir / "hosts.ini"
    assert inventory_file.is_file()

    return inventory_file


def get_template_name(hostname: str) -> str:
    template_name = TEMPLATE_LOOKUP.get(hostname, None)

    if not template_name:
        for prefix, template in TEMPLATE_LOOKUP.items():
            if hostname.startswith(prefix):
                template_name = template
                break

    return template_name


def get_merged_host_config(
    hostname: str,
    ansible_root: Path = Path("./ansible"),
) -> str:
    merged_config = {}
    host_vars_file = get_ansible_host_vars_file(hostname, ansible_root)
    host_vars = safe_load(host_vars_file.read_text())

    primary_group = host_vars.get("primary_group", None)
    assert primary_group, f"Primary group not found for {hostname}"

    group_vars_file = get_ansible_group_vars_file(primary_group, ansible_root)
    group_vars = safe_load(group_vars_file.read_text())
    group_vars["primary_group"] = primary_group

    # add group vars to merged config:
    merged_config.update(group_vars)

    # add host vars to merged config:
    merged_config.update(host_vars)

    # FIXME: both group_vars and host_vars have a 'nvidia_prime' key
    nvidia_prime_h = host_vars.get("nvidia_prime", {})
    nvidia_prime_g = group_vars.get("nvidia_prime", {})

    nvidia_prime = {**nvidia_prime_g, **nvidia_prime_h}
    merged_config["nvidia_prime"] = nvidia_prime

    return merged_config
