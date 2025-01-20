from pydantic import BaseModel
from typing import Optional, List, Dict
from .keys import ClientKey, ClientKeys, AccessKey  # noqa: F401
import yaml


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

    def get_host_config(self, vault_clients_path: str, users: List[str] = []):
        # ...existing code...
        pass


class AutoConfHosts(BaseModel):
    hosts: Dict[str, AutoConfHost] = {}

    def add_host(self, host: AutoConfHost):
        # ...existing code...
        pass

    def get_host(self, hostname: str):
        # ...existing code...
        pass

    def get_hosts_by_group(self, group: str):
        # ...existing code...
        pass

    def get_hosts_by_role(self, role: str):
        # ...existing code...
        pass

    def get_hosts_by_service(self, service: str):
        # ...existing code...
        pass

    def get_groups(self):
        # ...existing code...
        pass

    def get_roles(self):
        # ...existing code...
        pass

    def get_services(self):
        # ...existing code...
        pass

    def get_luxnix_configs(self):
        # ...existing code...
        pass
