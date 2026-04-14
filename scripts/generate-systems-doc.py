#!/usr/bin/env python3
"""
scripts/generate-systems-doc.py

Generates docs/systems.md from:
  - autoconf/merged_vars/<host>.yml  (source of truth for per-host settings)
  - systems/x86_64-linux/<host>/default.nix  (actual rendered roles block)

Usage:
  python scripts/generate-systems-doc.py
  devenv tasks run docs:systems

Free-text notes survive regeneration: anything between
  <!-- notes:hostname -->
  <!-- end-notes:hostname -->
is preserved verbatim across runs. Edit those blocks in docs/systems.md to add
per-host commentary without it being overwritten.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
MERGED_VARS_DIR = REPO_ROOT / "autoconf" / "merged_vars"
SYSTEMS_DIR = REPO_ROOT / "systems"
OUT_FILE = REPO_ROOT / "docs" / "systems.md"

# ---------------------------------------------------------------------------
# Host metadata
# ---------------------------------------------------------------------------
HOST_ORDER = [
    "s-01", "s-02", "s-03", "s-04",
    "gs-01", "gs-02",
    "gc-01", "gc-02", "gc-03", "gc-04", "gc-05",
    "gc-06", "gc-07", "gc-08", "gc-09", "gc-10",
    "c-01", "h-01",
]

HOST_TYPE = {
    "s-01":  "Base server (OpenVPN host)",
    "s-02":  "Base server (nginx / keycloak)",
    "s-03":  "Base server (nextcloud)",
    "s-04":  "Base server (central DB)",
    "gs-01": "GPU server",
    "gs-02": "GPU server (primary PostgreSQL)",
    "gc-01": "GPU client workstation",
    "gc-02": "GPU client workstation",
    "gc-03": "GPU client workstation",
    "gc-04": "GPU client workstation",
    "gc-05": "GPU client workstation",
    "gc-06": "GPU client workstation",
    "gc-07": "GPU client workstation",
    "gc-08": "GPU client workstation",
    "gc-09": "GPU client workstation",
    "gc-10": "GPU client workstation",
    "c-01":  "Client host",
    "h-01":  "Hetzner dedicated server",
}

# Roles shown in the fleet summary table (picked from the top-level enable keys)
SUMMARY_ROLES = [
    "base-server",
    "gpu-server",
    "endoreg-client",
    "aglnet.host",
    "keycloakHost",
    "nginxHost",
    "nextcloudHost",
    "hetzner",
    "postgres.main",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def strip_nix_str(val: Any) -> str:
    """Strip outer Nix double-quotes from a value that may look like '"foo"'."""
    if not isinstance(val, str):
        return str(val) if val is not None else ""
    v = val.strip()
    if v.startswith('"') and v.endswith('"') and len(v) > 1:
        return v[1:-1]
    return v


def is_true(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return False
    s = str(val).strip().strip('"').lower()
    return s in ("true", "1", "yes")


def host_key(hostname: str) -> str:
    """'gc-02' → 'gc_02' (form used in group_luxnix network host keys)."""
    return hostname.replace("-", "_")


def normalise_role(name: str) -> str:
    """Normalise Ansible-style role names (underscores) to Nix style (hyphens).

    Only transforms the leading role segment, not dotted sub-paths like
    'aglnet.client' or 'postgres.default'.
    """
    parts = name.split(".", 1)
    parts[0] = parts[0].replace("_", "-")
    return ".".join(parts)


def filter_top_roles(roles: list[str]) -> list[str]:
    """Drop sub-paths when their parent is also present.

    Example: if 'nginxHost' is enabled, drop 'nginxHost.keycloak'.
    """
    role_set = set(roles)
    return [
        r for r in roles
        if not any(
            r.startswith(parent + ".") and parent in role_set
            for parent in role_set
            if parent != r
        )
    ]


# ---------------------------------------------------------------------------
# Data extraction from merged_vars YAML
# ---------------------------------------------------------------------------

def load_merged_vars(host: str) -> dict:
    path = MERGED_VARS_DIR / f"{host}.yml"
    if not path.exists():
        return {}
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


def get_luxnix_value(mv: dict, key: str) -> Any:
    """Look up a dot-notation luxnix key: host_luxnix wins over group_luxnix."""
    for src in ("host_luxnix", "group_luxnix"):
        block = mv.get(src) or {}
        if key in block:
            return block[key]
    return None


def get_network_info(mv: dict, hostname: str) -> dict[str, Any]:
    """Extract this host's own network block from group_luxnix."""
    hk = host_key(hostname)
    prefix = f"generic_settings.network.hosts.{hk}."
    result: dict[str, Any] = {}
    # group_luxnix first, host_luxnix can override
    for src in ("group_luxnix", "host_luxnix"):
        block = mv.get(src) or {}
        for k, v in block.items():
            if k.startswith(prefix):
                field = k[len(prefix):]
                result[field] = v
    return result


def get_roles(mv: dict) -> dict[str, Any]:
    """Merge group_roles and host_roles; host_roles wins."""
    merged: dict[str, Any] = {}
    for src in ("group_roles", "host_roles"):
        block = mv.get(src) or {}
        merged.update(block)
    return merged


def enabled_top_roles(roles: dict) -> list[str]:
    """Return sorted, normalised, deduplicated list of enabled role paths."""
    raw = [
        normalise_role(k[: -len(".enable")])
        for k, v in roles.items()
        if k.endswith(".enable") and is_true(v)
    ]
    return sorted(set(raw))


def disabled_top_roles(roles: dict) -> list[str]:
    """Return sorted, normalised, deduplicated list of explicitly-disabled role paths."""
    raw = [
        normalise_role(k[: -len(".enable")])
        for k, v in roles.items()
        if k.endswith(".enable") and not is_true(v)
    ]
    return sorted(set(raw))


def custom_package_bundles(roles: dict) -> list[str]:
    """Return custom-packages.* bundle flags that are true (excluding .enable / ld.*)."""
    return sorted(set(
        k[len("custom_packages."):].replace("_", "-")
        for k, v in roles.items()
        if k.startswith("custom_packages.")
        and not k.endswith(".enable")
        and not k.startswith("custom_packages.ld")
        and is_true(v)
    ))


# ---------------------------------------------------------------------------
# Data extraction from generated default.nix
# ---------------------------------------------------------------------------

def parse_nix_roles(hostname: str) -> tuple[list[str], list[str]]:
    """
    Parse the roles = { … } block of systems/x86_64-linux/<host>/default.nix.
    Returns (enabled, disabled) as sorted, normalised lists of role paths.
    """
    nix_path = SYSTEMS_DIR / "x86_64-linux" / hostname / "default.nix"
    if not nix_path.exists():
        return [], []

    text = nix_path.read_text()
    m = re.search(r"\broles\s*=\s*\{(.*?)\};", text, re.DOTALL)
    if not m:
        return [], []

    block = m.group(1)
    enabled_raw, disabled_raw = [], []

    for line in block.splitlines():
        line = line.strip()
        rm = re.match(r"^([\w.\-]+)\.enable\s*=\s*(.+?);", line)
        if not rm:
            continue
        path = normalise_role(rm.group(1).strip())
        expr = rm.group(2).strip()
        if "false" in expr:
            disabled_raw.append(path)
        elif "true" in expr:
            enabled_raw.append(path)

    enabled_set = set(enabled_raw)
    disabled_raw = [r for r in disabled_raw if r not in enabled_set]

    return sorted(enabled_set), sorted(set(disabled_raw))


def load_inventory_ips(hosts_ini: Path) -> dict[str, str]:
    """Read ansible_host= values from hosts.ini as a fallback IP source."""
    ips: dict[str, str] = {}
    if not hosts_ini.exists():
        return ips
    for line in hosts_ini.read_text().splitlines():
        m = re.match(r"^(\S+)\s+ansible_host=(\S+)", line)
        if m:
            ips[m.group(1)] = m.group(2)
    return ips


# ---------------------------------------------------------------------------
# Notes preservation
# ---------------------------------------------------------------------------
NOTES_START = re.compile(r"<!-- notes:(\S+?) -->")
NOTES_END   = re.compile(r"<!-- end-notes:(\S+?) -->")


def extract_existing_notes(text: str) -> dict[str, str]:
    """Extract all <!-- notes:X --> … <!-- end-notes:X --> blocks."""
    notes: dict[str, str] = {}
    lines = text.splitlines(keepends=True)
    current_host: str | None = None
    buf: list[str] = []

    for line in lines:
        if current_host is None:
            m = NOTES_START.search(line)
            if m:
                current_host = m.group(1)
                buf = []
        else:
            m = NOTES_END.search(line)
            if m and m.group(1) == current_host:
                notes[current_host] = "".join(buf).strip()
                current_host = None
                buf = []
            else:
                buf.append(line)

    return notes


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def fleet_table(hosts: list[str], host_data: dict[str, dict]) -> str:
    header = "| Host | Type | VPN IP | CPU | GPU | Auto-updates |"
    sep    = "|------|------|--------|-----|-----|--------------|"
    rows   = [header, sep]

    for h in hosts:
        d = host_data.get(h, {})
        htype  = HOST_TYPE.get(h, "")
        vpn_ip = d.get("vpn_ip") or "—"
        cpu    = d.get("cpu", "—")
        gpu    = d.get("gpu_summary", "—")
        au     = "✓" if d.get("auto_updates") else "✗"
        ip_cell = f"`{vpn_ip}`" if vpn_ip != "—" else "—"
        rows.append(f"| [{h}](#{h}) | {htype} | {ip_cell} | {cpu} | {gpu} | {au} |")

    return "\n".join(rows)


def host_section(hostname: str, mv: dict, nix_enabled: list[str],
                 nix_disabled: list[str], existing_note: str,
                 fallback_ip: str = "") -> str:
    parts: list[str] = []

    # ---- Identity ----
    htype = HOST_TYPE.get(hostname, "")
    net = get_network_info(mv, hostname)
    vpn_ip   = strip_nix_str(net.get("ip_vpn", "")) or fallback_ip
    local_ip = strip_nix_str(net.get("ip_local", ""))
    domains  = net.get("domains", [])
    if isinstance(domains, list):
        domains = [strip_nix_str(d) for d in domains]

    parts.append(f"## {hostname}")
    parts.append("")
    parts.append(f"**Type:** {htype}  ")
    parts.append(f"**VPN IP:** `{vpn_ip or '—'}`" + (f"  \n**Local IP:** `{local_ip}`" if local_ip else ""))
    if domains:
        parts.append(f"**Domains:** {', '.join(f'`{d}`' for d in domains)}")

    # ---- Hardware ----
    cpu        = strip_nix_str(get_luxnix_value(mv, "generic_settings.linux.cpuMicrocode") or "")
    kernel_pkg = strip_nix_str(get_luxnix_value(mv, "generic_settings.linux.kernelPackages") or "")
    kmods      = get_luxnix_value(mv, "generic_settings.linux.kernelModules") or []
    state_ver  = strip_nix_str(get_luxnix_value(mv, "generic_settings.systemStateVersion") or "")
    platform   = strip_nix_str(get_luxnix_value(mv, "generic_settings.hostPlatform") or "x86_64-linux")

    gpu_en     = is_true(get_luxnix_value(mv, "generic_settings.gpu.nvidia.enable"))
    gpu_drv    = strip_nix_str(get_luxnix_value(mv, "generic_settings.gpu.nvidia.driver") or "")
    gpu_prime  = is_true(get_luxnix_value(mv, "generic_settings.gpu.nvidia.prime.enable"))
    nvidia_bus = strip_nix_str(get_luxnix_value(mv, "generic_settings.gpu.nvidia.prime.nvidiaBusId") or "")
    oboard_bus = strip_nix_str(get_luxnix_value(mv, "generic_settings.gpu.nvidia.prime.onboardBusId") or "")
    oboard_typ = strip_nix_str(get_luxnix_value(mv, "generic_settings.gpu.nvidia.prime.onboardType") or "")

    auto_up    = is_true(get_luxnix_value(mv, "maintenance.autoUpdates.enable"))
    au_dates   = strip_nix_str(get_luxnix_value(mv, "maintenance.autoUpdates.dates") or "")
    au_flake   = strip_nix_str(get_luxnix_value(mv, "maintenance.autoUpdates.flake") or "")

    parts.append("")
    parts.append("### Hardware")
    parts.append("")
    hw_rows = [
        ("Platform",        f"`{platform}`"),
        ("State version",   f"`{state_ver}`" if state_ver else None),
        ("CPU microcode",   f"`{cpu}`"        if cpu        else None),
        ("Kernel packages", f"`{kernel_pkg}`" if kernel_pkg else None),
        ("Kernel modules",  f"`{', '.join(kmods)}`" if kmods else None),
    ]
    if gpu_en:
        hw_rows.append(("NVIDIA GPU", f"`{gpu_drv}` driver"))
        if gpu_prime and nvidia_bus:
            hw_rows.append((
                "NVIDIA PRIME",
                f"nvidia `{nvidia_bus}` + {oboard_typ} `{oboard_bus}`",
            ))

    parts.append("| Property | Value |")
    parts.append("|----------|-------|")
    for label, value in hw_rows:
        if value:
            parts.append(f"| {label} | {value} |")

    # ---- Roles ----
    roles_mv  = get_roles(mv)
    mv_en     = enabled_top_roles(roles_mv)
    mv_dis    = disabled_top_roles(roles_mv)
    cp_flags  = custom_package_bundles(roles_mv)

    # Merge: nix-file is the authoritative final output; filter sub-role noise
    all_enabled  = filter_top_roles(sorted(set(mv_en)  | set(nix_enabled)))
    all_disabled = filter_top_roles(sorted(set(mv_dis) | set(nix_disabled)))
    all_disabled = [r for r in all_disabled if r not in set(all_enabled)]

    parts.append("")
    parts.append("### Enabled roles")
    parts.append("")
    if all_enabled:
        for r in all_enabled:
            parts.append(f"- `{r}`")
    else:
        parts.append("_none_")

    if all_disabled:
        parts.append("")
        parts.append("**Explicitly disabled:**")
        parts.append("")
        for r in all_disabled:
            parts.append(f"- `{r}`")

    if cp_flags:
        parts.append("")
        parts.append("**Custom package bundles:**")
        parts.append("")
        for f in cp_flags:
            parts.append(f"- `{f}`")

    # ---- Maintenance ----
    parts.append("")
    parts.append("### Maintenance")
    parts.append("")
    parts.append("| Property | Value |")
    parts.append("|----------|-------|")
    parts.append(f"| Auto-updates | {'**enabled**' if auto_up else 'disabled'} |")
    if auto_up:
        if au_dates:
            parts.append(f"| Update time  | `{au_dates}` |")
        if au_flake:
            parts.append(f"| Flake target | `{au_flake}` |")

    # ---- Notes (preserved across regenerations) ----
    parts.append("")
    parts.append("### Notes")
    parts.append("")
    parts.append(f"<!-- notes:{hostname} -->")
    if existing_note:
        parts.append(existing_note)
    else:
        parts.append("_No notes yet._")
    parts.append(f"<!-- end-notes:{hostname} -->")

    parts.append("")
    parts.append("---")
    parts.append("")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not MERGED_VARS_DIR.exists():
        print(
            f"ERROR: {MERGED_VARS_DIR} not found.\n"
            "Run 'devenv tasks run autoconf:finished' first.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Discover hosts: use HOST_ORDER + anything in merged_vars not in that list
    known = set(HOST_ORDER)
    extra = sorted(
        p.stem for p in MERGED_VARS_DIR.glob("*.yml") if p.stem not in known
    )
    all_hosts = [h for h in HOST_ORDER if (MERGED_VARS_DIR / f"{h}.yml").exists()]
    all_hosts += extra

    # Fallback IPs from hosts.ini for hosts without group_luxnix network entries
    inventory_ips = load_inventory_ips(
        REPO_ROOT / "ansible" / "inventory" / "hosts.ini"
    )

    # Preserve existing notes
    existing_notes: dict[str, str] = {}
    if OUT_FILE.exists():
        existing_notes = extract_existing_notes(OUT_FILE.read_text())

    # Build per-host data for the fleet table
    host_data: dict[str, dict] = {}
    for h in all_hosts:
        mv = load_merged_vars(h)
        net = get_network_info(mv, h)
        vpn_ip    = strip_nix_str(net.get("ip_vpn", "")) or inventory_ips.get(h, "")
        cpu       = strip_nix_str(get_luxnix_value(mv, "generic_settings.linux.cpuMicrocode") or "")
        gpu_en    = is_true(get_luxnix_value(mv, "generic_settings.gpu.nvidia.enable"))
        gpu_drv   = strip_nix_str(get_luxnix_value(mv, "generic_settings.gpu.nvidia.driver") or "")
        gpu_prime = is_true(get_luxnix_value(mv, "generic_settings.gpu.nvidia.prime.enable"))
        auto_up   = is_true(get_luxnix_value(mv, "maintenance.autoUpdates.enable"))

        if gpu_en:
            gpu_summary = f"NVIDIA {gpu_drv}" + (" PRIME" if gpu_prime else "")
        else:
            gpu_summary = "—"

        host_data[h] = {
            "vpn_ip":      vpn_ip,
            "cpu":         cpu or "—",
            "gpu_summary": gpu_summary,
            "auto_updates": auto_up,
        }

    # Assemble document
    doc_parts: list[str] = [
        "# Systems",
        "",
        "_Auto-generated from `autoconf/merged_vars/` and `systems/x86_64-linux/`",
        "by `scripts/generate-systems-doc.py`._",
        "",
        "_Re-run after `devenv tasks run autoconf:finished` to pick up inventory changes._",
        "_Free-text notes between `<!-- notes:X -->` and `<!-- end-notes:X -->` are preserved.",
        "Edit them directly in this file._",
        "",
        "---",
        "",
        "## Fleet summary",
        "",
        fleet_table(all_hosts, host_data),
        "",
        "---",
        "",
    ]

    for h in all_hosts:
        mv = load_merged_vars(h)
        nix_en, nix_dis = parse_nix_roles(h)
        note = existing_notes.get(h, "")
        fallback = inventory_ips.get(h, "")
        doc_parts.append(host_section(h, mv, nix_en, nix_dis, note, fallback))

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text("\n".join(doc_parts))
    print(f"Written {OUT_FILE.relative_to(REPO_ROOT)}")
    print(f"  {len(all_hosts)} hosts documented.")
    if existing_notes:
        preserved = [h for h in all_hosts if h in existing_notes and existing_notes[h]]
        if preserved:
            print(f"  Preserved notes for: {', '.join(preserved)}")


if __name__ == "__main__":
    main()
