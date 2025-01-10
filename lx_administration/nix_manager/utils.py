from pathlib import Path
from yaml import safe_load
import re


def find_duplicates(content, section):
    pattern = re.compile(rf"{section} = \{{(.*?)\}};", re.DOTALL)
    match = pattern.search(content)
    if not match:
        return {}

    section_content = match.group(1)
    lines = section_content.split("\n")
    keys = {}
    in_multiline = False
    multiline_key = None
    multiline_value = []
    for line in lines:
        if "''" in line:
            in_multiline = not in_multiline
            if in_multiline:
                # Found start of multiline block, parse key
                raw_line = line.strip()
                raw_key = raw_line.split("=")[0].strip()
                norm_key = raw_key.replace("_", "-")
                multiline_key = norm_key
                multiline_value = [raw_line.split("''", 1)[1]]
            else:
                # End of multiline block, store
                multiline_value.append(line.split("''", 1)[0])
                keys[multiline_key] = (
                    f"{multiline_key} = ''\n" + "\n".join(multiline_value) + "'';"
                )
                multiline_key = None
                multiline_value = []
        elif in_multiline:
            multiline_value.append(line)
        else:
            if "=" in line:
                raw_line = line.strip()
                raw_key = raw_line.split("=")[0].strip()
                norm_key = raw_key.replace("_", "-")
                if norm_key not in keys:
                    # Rebuild line to use the normalized key
                    remainder = raw_line.split("=", 1)[1]
                    keys[norm_key] = f"{norm_key}={remainder}"
    return keys


def remove_duplicates(content, section):
    keys = find_duplicates(content, section)
    pattern = re.compile(rf"{section} = \{{(.*?)\}};", re.DOTALL)
    match = pattern.search(content)
    if not match:
        return content

    section_content = match.group(1)
    lines = section_content.split("\n")
    indent = ""
    for line in lines:
        if line.strip():
            indent = line[: len(line) - len(line.lstrip())]
            break

    new_section_content = "\n".join(indent + line for line in keys.values())
    new_content = (
        content[: match.start()]
        + f"{section} = {{\n"
        + new_section_content
        + "\n"
        + indent
        + "};"
        + content[match.end() :]
    )
    in_multiline = False
    new_section_lines = []
    for line in lines:
        if "''" in line:
            in_multiline = not in_multiline
        if in_multiline:
            new_section_lines.append(line)
        else:
            new_section_lines.append(line)
    return new_content


def parse_nix_file(filepath):
    with open(filepath, "r") as file:
        content = file.read()
    content = remove_duplicates(content, "user")
    content = remove_duplicates(content, "roles")
    return content


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
