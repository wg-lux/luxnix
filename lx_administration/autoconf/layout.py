"""Canonical filesystem layouts used by the Autoconf pipeline."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AnsibleInventoryLayout:
    """Fixed input paths below one Ansible inventory directory."""

    root: Path

    @property
    def hosts_file(self) -> Path:
        return self.root / "hosts.ini"

    @property
    def home_manifest(self) -> Path:
        return self.root / "home-hosts.yml"

    @property
    def group_vars_dir(self) -> Path:
        return self.root / "group_vars"

    @property
    def host_vars_dir(self) -> Path:
        return self.root / "host_vars"

    @property
    def home_vars_dir(self) -> Path:
        return self.host_vars_dir / "home"


@dataclass(frozen=True)
class AutoconfSourceLayout:
    """Fixed input paths below one configured Ansible root."""

    root: Path

    @property
    def inventory(self) -> AnsibleInventoryLayout:
        return AnsibleInventoryLayout(self.root / "inventory")

    @property
    def facts_dir(self) -> Path:
        return self.root / "cmdb"

    @property
    def roles_dir(self) -> Path:
        return self.root / "roles"


@dataclass(frozen=True)
class AutoconfOutputLayout:
    """Fixed generated artifacts below one configured output root."""

    root: Path

    @property
    def inventory_file(self) -> Path:
        return self.root / "inventory.yml"

    @property
    def system_vars_dir(self) -> Path:
        return self.root / "merged_vars"

    @property
    def home_vars_dir(self) -> Path:
        return self.root / "home_merged_vars"

    @property
    def log_dir(self) -> Path:
        return self.root / "logs"


@dataclass(frozen=True)
class NixTemplateLayout:
    """Fixed system and Home Manager paths below one Nix template root."""

    root: Path

    @property
    def systems_dir(self) -> Path:
        return self.root / "systems"

    @property
    def homes_dir(self) -> Path:
        return self.root / "homes"

    def system_template_dir(self, platform: str, template_name: str) -> Path:
        return self.systems_dir / platform / template_name

    def home_template_dir(self, platform: str) -> Path:
        return self.homes_dir / platform


@dataclass(frozen=True)
class NixOutputLayout:
    """Fixed generated paths below one Nix output root."""

    root: Path

    @property
    def systems_dir(self) -> Path:
        return self.root / "systems"

    @property
    def homes_dir(self) -> Path:
        return self.root / "homes"

    def system_file(self, platform: str, hostname: str) -> Path:
        return self.systems_dir / platform / hostname / "default.nix"

    def home_file(self, platform: str, user: str, hostname: str) -> Path:
        return self.homes_dir / platform / f"{user}@{hostname}" / "default.nix"
