from pydantic import BaseModel
from typing import Optional, List, Dict, Union
from datetime import datetime, timedelta
from .hosts import VaultClient, AccessKey, ClientKey
from lx_administration.password.generator import PasswordGenerator


class RawSecret(BaseModel):
    name: str
    raw: str


class EncryptedSecret(BaseModel):
    name: str
    source_file: str
    destination_file: str

    access_key: AccessKey
    client_key: ClientKey


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
