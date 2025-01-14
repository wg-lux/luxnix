from pydantic import BaseModel, model_validator
from typing import Optional, List, Dict, Union
import os
import subprocess
import shutil
import yaml
import warnings
from ..logging import get_logger
from ..password.generator import PasswordGenerator
from datetime import datetime, timedelta
from pathlib import Path

GROUP_KEY_PREFIX = "group_"
ROLE_KEY_PREFIX = "role_"
SERVICE_KEY_PREFIX = "service_"
ACCESS_KEY_PREFIX = "access_"
LOCAL_PWD_KEY_PREFIX = "pwd_"
MACHINE_KEY_PREFIX = "host_"


class ClientKey(BaseModel):
    name: str
    raw: Optional[str] = None
    file: Optional[str] = None


class ClientKeys(BaseModel):
    keys: Dict[str, ClientKey] = {}
    file: Optional[str] = "./client_keys.yml"

    def add_key(self, key: ClientKey):
        self.keys[key.name] = key

    def get_key(self, name: str):
        return self.keys.get(name, None)

    def get_or_create(self, name: str):
        if name not in self.keys:
            self.keys[name] = ClientKey(name=name)
        return self.keys[name]

    @classmethod
    def load_from_file(cls, file: str = "./client_keys.yml"):
        with open(file, "r") as f:
            raw = yaml.safe_load(f)
            raw[file] = file

        return cls(**raw)

    def save_to_file(self, file: str = "./client_keys.yml"):
        with open(file, "w") as f:
            yaml.dump(self.model_dump(), f)


class PreSharedKey(BaseModel):
    name: str
    raw: Optional[str] = None
    file: Optional[str] = None

    hosts: List[ClientKey] = []
    roles: List[ClientKey] = []
    groups: List[ClientKey] = []


class AccessKey(BaseModel):
    name: str
    raw: Optional[str] = None
    file: Optional[str] = None

    sensitivity: int
    hosts: List[ClientKey] = []
    roles: List[ClientKey] = []
    groups: List[ClientKey] = []

    def can_decrypt(self, required_sensitivity: int) -> bool:
        return self.sensitivity >= required_sensitivity


class RawSecret(BaseModel):
    name: str
    raw: str


class EncryptedSecret(BaseModel):
    name: str
    source_file: str
    destination_file: str

    access_key: AccessKey
    client_key: ClientKey


class VaultGroup(BaseModel):
    name: str


class VaultGroups(BaseModel):
    groups: Dict[str, VaultGroup] = {}

    def add_group(self, group: VaultGroup):
        self.groups[group.name] = group

    def get_group(self, name: str):
        return self.groups.get(name, None)

    def get_vault_clients_by_group(self, name: str):
        group = self.get_group(name)
        if group is not None:
            return group.vault_clients
        return []

    def get_vault_client_by_name(self, name: str):
        clients = []
        for group in self.groups.values():
            for client in group.vault_clients:
                if client.name == name:
                    clients.append(client)

        # make set to remove duplicates
        clients = list(set(clients))

        assert len(clients) == 1
        return clients[0]


class VaultClient(BaseModel):
    name: str
    key: ClientKey = None
    vault_group: Optional[VaultGroup] = None


class VaultClients(BaseModel):
    clients: Dict[str, VaultClient] = {}
    client_keys: ClientKeys = ClientKeys()
    file: str = "./vault_clients.yml"

    def get_or_create(self, name: str):
        if name not in self.clients:
            key = self.client_keys.get_or_create(name)
            self.clients[name] = VaultClient(name=name, key=key)
            self.save_to_file(self.file)
        return self.clients[name]

    @classmethod
    def load_from_file(cls, file: str = "./vault_clients.yml"):
        with open(file, "r") as f:
            raw = yaml.safe_load(f)
            raw[file] = file

            return cls(**raw)
            # for name, client in raw["clients"].items():
            #     self.clients[name] = VaultClient(**client)

            # for name, key in raw["client_keys"].items():
            #     self.client_keys.keys[name] = ClientKey(**key)

    def save_to_file(self, file: Optional[str] = None):
        with open(file, "w") as f:
            yaml.dump(self.model_dump(), f)


class Secret(BaseModel):
    name: str
    raw: Optional[str] = None
    raw_file: Optional[str] = None
    secret_type: Optional[str] = None
    updated: Optional[datetime] = None
    validity: Optional[timedelta] = None

    vault_clients: List[VaultClient] = []
    sensitivity: int

    encrypted: Dict[int, EncryptedSecret] = {}

    def re_encrypt_for(self, target_access_key: AccessKey):
        if not target_access_key.can_decrypt(self.sensitivity):
            raise ValueError("Target key does not meet sensitivity requirement.")
        # ...logic for decrypting self with current AccessKey...
        # ...logic for encrypting with target_access_key...
        pass

    def is_valid(self):
        return self.raw is not None or self.raw_file is not None

    def open(self, key: Optional[Union[AccessKey, ClientKey]] = None):
        if self.raw:
            return self.raw
        if self.raw_file:
            with open(self.raw_file, "r") as f:
                return f.read()
        if not key:
            key = self.va
            self.logger.info("")
        else:
            if isinstance(key, AccessKey):
                if key.can_decrypt(self.sensitivity):
                    # ...decrypt and return...
                    return "decrypted_secret_stub"
            elif isinstance(key, ClientKey):
                # ...decrypt and return...
                return "decrypted_secret_stub"

    def add_vault_client(self, client: VaultClient):
        self.vault_clients.append(client)

    def remove_vault_client(self, client: VaultClient):
        self.vault_clients.remove(client)

    def update(self):
        if self.secret_type == "password":
            if not self.updated():
                pp = PasswordGenerator()
                self.raw = pp.generate_random_passphrase(2)
                self.initialized = True
                self.updated = datetime.now()


class Secrets(BaseModel):
    secrets: Dict[str, Secret] = {}


class HostConfig(BaseModel):
    hostname: str
    ip_address: str
    roles: List[VaultClient] = []
    groups: List[VaultClient] = []
    services: List[VaultClient] = []
    users: List[str] = []

    vault_client: Optional[VaultClient] = None
    all_vault_clients: List[VaultClient] = []


class Hosts(BaseModel):
    hosts: Dict[str, HostConfig] = {}

    def add_host(self, host: HostConfig):
        self.hosts[host.hostname] = host

    def get_all_clients(self):
        clients = []
        for host in self.hosts.values():
            clients.extend(host.all_vault_clients)
        return clients


class AutoConfHost(BaseModel):
    group_vars: dict = {}
    groups: List[str] = []
    host_vars: dict = {}
    hostname: Optional[str] = None
    luxnix_configs: dict = {}
    role_configs: dict = {}
    service_configs: dict = {}
    vpn_ip: Optional[str] = None

    def get_host_config(
        self, vault_clients_path: str, users: List[str] = []
    ):  # -> HostConfig
        vault_clients = VaultClients.load_from_file(vault_clients_path)

        print(f"Creating host config for {self.hostname}")
        print(vault_clients)

        host_config = HostConfig(
            hostname=self.hostname,
            ip_address=self.host_vars.get("vpn_ip", ""),
            roles=[],
            groups=[],
            services=[],
            users=users,
            machine_client=vault_clients.get_or_create(
                name=f"{MACHINE_KEY_PREFIX}{self.hostname}"
            ),
        )

        for group in self.groups:
            host_config.groups.append(
                vault_clients.get_or_create(name=f"{GROUP_KEY_PREFIX}{group}")
            )

        for role, value in self.role_configs.items():
            if role.endswith("_key") or role.endswith("_access"):
                if value is True:
                    host_config.roles.append(
                        vault_clients.get_or_create(name=f"{ROLE_KEY_PREFIX}{role}")
                    )

        for service in self.service_configs:
            host_config.services.append(
                vault_clients.get_or_create(name=f"{SERVICE_KEY_PREFIX}{service}")
            )

        for user in users:
            host_config.users.append(user)

        return host_config


class AutoConfHosts(BaseModel):
    hosts: Dict[str, AutoConfHost] = {}

    def add_host(self, host: AutoConfHost):
        self.hosts[host.hostname] = host

    def get_host(self, hostname: str):
        return self.hosts.get(hostname, None)

    def get_hosts_by_group(self, group: str):
        hosts = []
        for host in self.hosts.values():
            if group in host.groups:
                hosts.append(host)
        return hosts

    def get_hosts_by_role(self, role: str):
        hosts = []
        for host in self.hosts.values():
            if role in host.role_configs:
                hosts.append(host)
        return hosts

    def get_hosts_by_service(self, service: str):
        hosts = []
        for host in self.hosts.values():
            if service in host.service_configs:
                hosts.append(host)
        return hosts

    def get_groups(self):
        groups = set()
        for host in self.hosts.values():
            for group in host.groups:
                groups.add(group)
        return groups

    def get_roles(self):
        roles = set()
        for host in self.hosts.values():
            for role in host.roles:
                roles.add(role)
        return roles

    def get_services(self):
        services = set()
        for host in self.hosts.values():
            for service in host.groups:
                services.add(service)
        return services

    def get_luxnix_configs(self):
        configs = set()
        for host in self.hosts.values():
            for config in host.luxnix_configs:
                configs.add(config)
        return configs


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
