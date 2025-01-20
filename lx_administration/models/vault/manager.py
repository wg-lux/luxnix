from pydantic import BaseModel
from typing import Optional, List, Dict, Union
import os
import subprocess
import shutil
import yaml
import warnings
from lx_administration.logging import get_logger
from lx_administration.password.generator import PasswordGenerator
from datetime import datetime, timedelta
from pathlib import Path
from .hosts import (
    Hosts,
    ClientKey,
    ClientKeys,
    VaultClient,
    VaultClients,
    VaultGroup,
    VaultGroups,
    HostConfig,
    AutoConfHost,
    AutoConfHosts,
)


GROUP_KEY_PREFIX = "group_"
ROLE_KEY_PREFIX = "role_"
SERVICE_KEY_PREFIX = "service_"
ACCESS_KEY_PREFIX = "access_"
LOCAL_PWD_KEY_PREFIX = "pwd_"
MACHINE_KEY_PREFIX = "host_"


class Vault:
    def __init__(
        self,
        vault_dir: Optional[str] = None,
        ansible_key_path: Optional[str] = None,
        host_configs: Optional[str] = None,
        hosts_file: Optional[str] = None,
        vault_clients_file: Optional[str] = None,
        vault_clients: Optional[VaultClients] = None,
        hosts: Optional[Hosts] = None,
        autoconf_host_file: Optional[str] = None,
        autoconf_hosts: Optional[AutoConfHosts] = None,
        log_dir: Optional[str] = None,
        client_keys: Optional[ClientKeys] = None,
        client_keys_file: Optional[str] = None,
        default_users: List[str] = [
            "admin",
            "dev-01",
            "maintenance-user",
            "postgres",
            "lxAnonxmizer",
        ],
        pg=PasswordGenerator(),
    ):
        self.default_users = default_users

        if vault_dir is None:
            vault_dir = os.path.expanduser("~/lx-vault")
        self.vault_dir = vault_dir

        if not vault_clients_file:
            self.vault_clients_file = os.path.join(vault_dir, "vault_clients.yml")

        if not vault_clients:
            if not os.path.exists(self.vault_clients_file):
                warnings.warn("Vault clients file not found. Creating new.")
                self.vault_clients = VaultClients()
                self.vault_clients.save_to_file(self.vault_clients_file)
            else:
                self.vault_clients = VaultClients.load_from_file(
                    self.vault_clients_file
                )

        if not hosts_file:
            hosts_file = os.path.join(self.vault_dir, "hosts.yml")

        self.hosts_file = hosts_file

        if ansible_key_path is None:
            ansible_key_path = os.path.expanduser("~/lx-vault.key")
        self.ansible_key_path = ansible_key_path

        if not os.path.exists(ansible_key_path):
            self.generate_vault_key(ansible_key_path)
        if not log_dir:
            log_dir = os.path.join(vault_dir, "lx-vault-logs")
            if not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)

        if not client_keys_file:
            client_keys_file = os.path.join(vault_dir, "client_keys.yml")

        if not client_keys:
            if not os.path.exists(client_keys_file):
                warnings.warn("Client keys file not found. Creating new.")
                client_keys = ClientKeys()
                client_keys.save_to_file(client_keys_file)
            else:
                client_keys = ClientKeys.load_from_file(client_keys_file)

        self.logger = get_logger("lx-vault", Path(log_dir), reset=True)

        # Print heading and timestamp
        self.logger.info("----" * 4)
        self.logger.info("lx-vault initialized")
        self.logger.info("----" * 4)

        os.makedirs(self.vault_dir, exist_ok=True)

        if host_configs is None:
            host_configs = "./autoconf/host_configs.yml"

        if not autoconf_host_file:
            self.autoconf_host_file = os.path.join(self.vault_dir, "autoconf-hosts.yml")

        self.host_configs = host_configs

        if not os.path.exists(self.autoconf_host_file):
            self.logger.warning("Autoconf-hosts file not found. Attempting bootstrap")

            if not os.path.exists(self.host_configs):
                self.logger.error("Host-configs file not found. Cannot bootstrap.")
                raise FileNotFoundError(
                    "Autoconf-hosts and Host-configs file both unavailable."
                )

            self.autoconf_hosts = self.bootstrap_hosts()

        self.load_autoconf_hosts()
        # print list of hosts
        self.logger.info("----" * 4)
        self.logger.info("Autoconf Hosts:")
        for hostname in self.autoconf_hosts.hosts.keys():
            self.logger.info(f"\t{hostname}")
        self.logger.info("----" * 4)

    def load_autoconf_hosts(self):
        with open(self.autoconf_host_file, "r") as f:
            raw_autoconf_hosts = yaml.safe_load(f)
            self.autoconf_hosts = AutoConfHosts(**raw_autoconf_hosts)

    def generate_vault_key(self, key_path: Optional[str] = None):
        if not key_path:
            key_path = self.ansible_key_path

        # run ansible-vault to generate key
        subprocess.run(["ansible-vault", "keygen", key_path])

    def encrypt_secret(self, secret: str, key_path: Optional[str] = None) -> str:
        if not shutil.which("ansible-vault"):
            # ...fallback or raise exception...
            return ""
        if not key_path:
            key_path = self.ansible_key_path

        subprocess.run(
            [
                "ansible-vault",
                "encrypt_string",
                "--vault-password-file",
                key_path,
                secret,
                "--name",
                "secret",
            ]
        )
        return "encrypted_secret_stub"

    def decrypt_secret(
        self, encrypted_secret: str, key_path: Optional[str] = None
    ) -> str:
        if not shutil.which("ansible-vault"):
            raise Exception("ansible-vault CLI not found")
        if not key_path:
            key_path = self.ansible_key_path

        subprocess.run(
            [
                "ansible-vault",
                "decrypt",
                "encrypted_file_name",
                "--vault-password-file",
                key_path,
            ]
        )
        return "decrypted_secret_stub"

    def generate_hosts_file(self):
        # load autoconf_hosts
        self.load_autoconf_hosts()

        # create Hosts model
        hosts = Hosts()

        for hostname, autoconf_host in self.autoconf_hosts.hosts.items():
            new_host_config = autoconf_host.get_host_config(
                self.vault_clients_file, self.default_users
            )
            hosts.add_host(new_host_config)

        # dump to yml
        with open(self.hosts_file, "w") as f:
            yaml.dump(hosts.model_dump(), f)

        self.logger.info(f"Hosts file created at {self.hosts_file}")

    def bootstrap_hosts(self) -> Dict[str, AutoConfHost]:
        # load host_configs as AutoConfHosts
        autoconf_hosts = AutoConfHosts()
        self._log_heading("Bootstrapping hosts")
        with open(self.host_configs, "r") as f:
            host = yaml.safe_load(f)
            for hostname, host_config in host.items():
                autoconf_hosts.add_host(AutoConfHost(**host_config))

        # save autoconf_hosts to file
        with open(self.autoconf_host_file, "w") as f:
            # dump readable yml
            yaml.dump(autoconf_hosts.model_dump(), f)

        self.logger.info(f"Bootstrapping complete. {len(autoconf_hosts.hosts)} hosts.")

        if not os.path.exists(self.hosts_file):
            self.logger.warning("Hosts file not found. Attempting to create.")
            self.generate_hosts_file()

    def _log_heading(self, message: str):
        self.logger.info(("----" * 4))
        self.logger.info(f"{message}")
        self.logger.info(("----" * 4))

    def load_hosts_file(self):
        with open(self.hosts_file, "r") as f:
            raw_hosts = yaml.safe_load(f)
            self.hosts = Hosts(**raw_hosts)

    def write_hosts_file(self):
        with open(self.hosts_file, "w") as f:
            yaml.dump(self.hosts.model_dump(), f)

    def sync_hosts_file(self):
        self.load_autoconf_hosts()
        ac_hosts = self.autoconf_hosts

        # load hosts file
        self.load_hosts_file()
        hosts = self.hosts

        # iterate over ac_hosts and generate new hosts if not in hosts
        for hostname, autoconf_host in ac_hosts.hosts.items():
            if hostname not in hosts.hosts:
                hosts.add_host(autoconf_host.get_host_config())

        # write hosts file
        self.write_hosts_file()

    def check_user_passwords(self, validity_days=90):
        pass

    def sync(self):
        self._log_heading("Syncing vault")

        if not os.path.exists(self.host_configs):
            self.logger.error("Host-configs file not found. Cannot sync.")
            return

        # generate autoconf-hosts file
        self.bootstrap_hosts()
        self.check_user_passwords()

        # sync hosts_file
        self.sync_hosts_file()

        self._log_heading("Vault synced")
