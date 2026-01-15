from configparser import ConfigParser
from pydantic import BaseModel
from pydantic import ConfigDict
from pathlib import Path
from typing import Optional, Dict, Any, List
import warnings


class AnsibleCfgDefaults(BaseModel):
    """
    Default configuration settings for Ansible.

    This class defines the default paths and settings used in the Ansible configuration,
    including inventory locations, variable paths, roles path, logging, and vault identities.
    """

    inventory: str = "./ansible/inventory/hosts.ini"
    group_vars: str = "./ansible/inventory/group_vars"
    host_vars: str = "./ansible/inventory/host_vars"
    roles_path: str = "./ansible/roles"
    log_path: str = "./logs/ansible.log"
    library: str = "./ansible/modules"
    vault_identity_list: Optional[str] = None
    private_key_file: Optional[str] = None

    def get_vid_list(self) -> List[str]:
        """
        Get the vault identity list as a list of strings.

        Returns:
            list: List of vault identity strings split by comma, or empty list if no vault identities exist.
        """
        if self.vault_identity_list:
            return self.vault_identity_list.split(",")
        else:
            return []

    def get_vid_dict(self) -> Dict[str, str]:
        """
        Convert vault identity list into a dictionary mapping hosts to paths.

        Returns:
            dict: Dictionary with host as key and path as value.
        """
        vid_list = self.get_vid_list()
        vid_dict: Dict[str, str] = {}
        for vid in vid_list:
            if "@" in vid:
                host, path = vid.split("@", 1)
                vid_dict[host] = path

        return vid_dict

    def vid_dict2list(self, vid_dict: Dict[str, str]) -> List[str]:
        """
        Convert a dictionary of vault identities to a list format.

        Args:
            vid_dict (dict): Dictionary with host as key and path as value.

        Returns:
            list: List of strings in format 'host@path'.
        """
        vid_list: List[str] = []
        for host, path in vid_dict.items():
            vid_list.append(f"{host}@{path}")
        return vid_list

    def vid_list2str(self, vid_list: List[str]) -> str:
        return ",".join(vid_list)

    def update_vid_entry(self, host: str, path: str):
        vid_dict = self.get_vid_dict()
        vid_dict[host] = path
        vault_identity_list = self.vid_dict2list(vid_dict)
        self.vault_identity_list = self.vid_list2str(vault_identity_list)
        self.drop_missing_vid()

    def drop_missing_vid(self):
        file_not_found: List[str] = []
        vid_dict = self.get_vid_dict()
        for host, path in vid_dict.items():
            if not Path(path).exists():
                file_not_found.append(host)

        for host in file_not_found:
            del vid_dict[host]

        self.vault_identity_list = self.vid_list2str(self.vid_dict2list(vid_dict))

        if file_not_found:
            warnings.warn(
                f"Removing vault_identities with missing files in ansible.cfg: {file_not_found}"
            )

    def validate_cfg(self):
        self.drop_missing_vid()


class AnsibleCfgPrivilegeEscalation(BaseModel):
    become: bool = True
    become_method: str = "sudo"
    become_user: str = "admin"
    become_ask_pass: bool = False

    def validate_cfg(self):
        pass


class AnsibleCfg(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    defaults: AnsibleCfgDefaults = AnsibleCfgDefaults()
    privilege_escalation: AnsibleCfgPrivilegeEscalation = (
        AnsibleCfgPrivilegeEscalation()
    )

    @classmethod
    def ensure_vault_id_pwdfile(cls, cfg_path: str, host: str, path: str):
        """Ensure vault_id and password_file entries in ansible.cfg"""
        host = host.replace("@", "_")
        path = path.replace("@", "_")
        ansible_cfg = cls.from_file(cfg_path)
        ansible_cfg.defaults.update_vid_entry(host, path)
        ansible_cfg.save_to_file(cfg_path)

    @classmethod
    def from_file(cls, file: str):
        """Load ansible.cfg file"""
        config = ConfigParser()
        config.read(file)

        # Convert ConfigParser to dict structure
        data: Dict[str, Dict[str, Any]] = {"defaults": {}, "privilege_escalation": {}}

        if config.has_section("defaults"):
            data["defaults"] = dict(config["defaults"])

        if config.has_section("privilege_escalation"):
            # Convert string 'True'/'False' to boolean for boolean fields
            priv_esc: Dict[str, Any] = dict(config["privilege_escalation"])
            for key in ["become", "become_ask_pass"]:
                if key in priv_esc:
                    priv_esc[key] = config.getboolean("privilege_escalation", key)
            data["privilege_escalation"] = priv_esc

        return cls.model_validate(data)

    def validate_cfg(self):
        """Validate ansible.cfg model"""
        self.defaults.validate_cfg()
        self.privilege_escalation.validate_cfg()

    def save_to_file(self, file: str):
        """Save ansible.cfg file"""
        config = ConfigParser()
        config["defaults"] = self.defaults.model_dump()
        config["privilege_escalation"] = self.privilege_escalation.model_dump()

        with open(file, "w") as f:
            config.write(f)
