import warnings
from configparser import ConfigParser
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field


def _config_section(values: dict[str, object]) -> dict[str, str]:
    """Convert model data to values accepted by ConfigParser."""
    return {key: str(value) for key, value in values.items() if value is not None}


class AnsibleCfgDefaults(BaseModel):
    """Default paths and vault identities for Ansible."""

    inventory: str = "./ansible/inventory/hosts.ini"
    group_vars: str = "./ansible/inventory/group_vars"
    host_vars: str = "./ansible/inventory/host_vars"
    roles_path: str = "./ansible/roles"
    log_path: str = "./logs/ansible.log"
    library: str = "./ansible/modules"
    vault_identity_list: str | None = None
    private_key_file: str | None = None

    def get_vid_list(self) -> list[str]:
        """Return the configured non-empty vault identity entries."""
        if not self.vault_identity_list:
            return []
        return [
            entry.strip()
            for entry in self.vault_identity_list.split(",")
            if entry.strip()
        ]

    def get_vid_dict(self) -> dict[str, str]:
        """Return vault identities keyed by host."""
        return {
            host: path
            for entry in self.get_vid_list()
            if "@" in entry
            for host, path in [entry.split("@", 1)]
        }

    @staticmethod
    def vid_dict2list(vid_dict: dict[str, str]) -> list[str]:
        """Format host-to-path mappings as Ansible vault identities."""
        return [f"{host}@{path}" for host, path in vid_dict.items()]

    @staticmethod
    def vid_list2str(vid_list: list[str]) -> str:
        return ",".join(vid_list)

    def update_vid_entry(self, host: str, path: str) -> None:
        vid_dict = self.get_vid_dict()
        vid_dict[host] = path
        vault_identity_list = self.vid_dict2list(vid_dict)
        self.vault_identity_list = self.vid_list2str(vault_identity_list)
        self.drop_missing_vid()

    def drop_missing_vid(self) -> None:
        missing_hosts: list[str] = []
        vid_dict = self.get_vid_dict()
        for host, path in vid_dict.items():
            if not Path(path).expanduser().exists():
                missing_hosts.append(host)

        for host in missing_hosts:
            del vid_dict[host]

        self.vault_identity_list = self.vid_list2str(self.vid_dict2list(vid_dict))

        if missing_hosts:
            warnings.warn(
                "Removing vault_identities with missing files in ansible.cfg: "
                f"{missing_hosts}",
                stacklevel=2,
            )

    def validate_cfg(self) -> None:
        self.drop_missing_vid()


class AnsibleCfgPrivilegeEscalation(BaseModel):
    become: bool = True
    become_method: str = "sudo"
    become_user: str = "admin"
    become_ask_pass: bool = False


class AnsibleCfg(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    defaults: AnsibleCfgDefaults = Field(default_factory=AnsibleCfgDefaults)
    privilege_escalation: AnsibleCfgPrivilegeEscalation = Field(
        default_factory=AnsibleCfgPrivilegeEscalation
    )

    @classmethod
    def ensure_vault_id_pwdfile(
        cls,
        cfg_path: str | Path,
        host: str,
        path: str | Path,
    ) -> None:
        """Ensure one host-to-password-file entry exists in ansible.cfg."""
        host = host.replace("@", "_")
        path_string = str(path).replace("@", "_")
        ansible_cfg = cls.from_file(cfg_path)
        ansible_cfg.defaults.update_vid_entry(host, path_string)
        ansible_cfg.save_to_file(cfg_path)

    @classmethod
    def from_file(cls, file: str | Path) -> Self:
        """Load an existing ansible.cfg file."""
        config_path = Path(file).expanduser().resolve()
        if not config_path.is_file():
            raise FileNotFoundError(f"Ansible config not found: {config_path}")

        config = ConfigParser()
        config.read(config_path, encoding="utf-8")

        data: dict[str, dict[str, str | bool]] = {
            "defaults": {},
            "privilege_escalation": {},
        }

        if config.has_section("defaults"):
            data["defaults"] = dict(config["defaults"])

        if config.has_section("privilege_escalation"):
            privilege_escalation: dict[str, str | bool] = dict(
                config["privilege_escalation"]
            )
            for key in ["become", "become_ask_pass"]:
                if key in privilege_escalation:
                    privilege_escalation[key] = config.getboolean(
                        "privilege_escalation", key
                    )
            data["privilege_escalation"] = privilege_escalation

        return cls.model_validate(data)

    def validate_cfg(self) -> None:
        """Remove vault identities whose files no longer exist."""
        self.defaults.validate_cfg()

    def save_to_file(self, file: str | Path) -> None:
        """Save ansible.cfg, omitting unset optional values."""
        config_path = Path(file).expanduser().resolve()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        config = ConfigParser()
        config["defaults"] = _config_section(self.defaults.model_dump())
        config["privilege_escalation"] = _config_section(
            self.privilege_escalation.model_dump()
        )

        with config_path.open("w", encoding="utf-8") as output:
            config.write(output)
