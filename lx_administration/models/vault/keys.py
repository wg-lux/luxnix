from pydantic import BaseModel
from typing import Optional, List, Dict
import yaml


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
