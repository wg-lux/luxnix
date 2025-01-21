from pydantic import BaseModel
from typing import Optional, List, Dict, Union
from datetime import datetime, timedelta
from pathlib import Path
from lx_administration.logging import get_logger
import shutil
import os
from lx_administration.yaml import dump_yaml, format_yaml, ansible_lint


from ..ansible import AnsibleInventory

OWNER_TYPES = ["local", "roles", "services", "luxnix", "clients"]


def generate_ansible_key(key_path: Path, encryption_key_path: Optional[Path] = None):
    # Generate a new ansible vault key
    import subprocess

    assert not key_path.exists(), f"File {key_path} already exists!"
    subprocess.run(["ansible-vault", "create", key_path])

    # make sure the key has current user as owner with permissions 700
    subprocess.run(["chown", f"{os.getlogin()}:users", key_path])

    if encryption_key_path:
        if not encryption_key_path.exists():
            raise FileNotFoundError(f"File {encryption_key_path} does not exist!")
        subprocess.run(
            ["ansible-vault", "encrypt", "--vault-password-file", encryption_key_path]
        )


def generate_access_key_path(name: str, vault_dir: Path, owner_type: str):
    assert owner_type in OWNER_TYPES, f"Invalid owner_type: {owner_type}"
    if not vault_dir.exists():
        vault_dir.mkdir(parents=True)
    return vault_dir / f"{owner_type}/{name}.key"


def generate_secret_dir_path(name: str, vault_dir: Path):
    secret_dir = vault_dir / "secrets" / name
    if not secret_dir.exists():
        secret_dir.mkdir(parents=True)

    return secret_dir


class AccessKey(BaseModel):
    name: str
    description: Optional[str] = ""
    vault_dir: str
    file: str  # Path to the file containing the encrypted ansible Vault Key
    local_vault_key: str = "~/.lxv.key"  # Path to the file containing the password to decrypt the ansible Vault Key
    created: Optional[datetime] = None
    updated: Optional[datetime] = None
    # 180d
    validity: Optional[timedelta] = timedelta(days=180)
    owner_type: Optional[str] = "roles"  # should be in OWNER_TYPES

    @classmethod
    def get_or_create(
        cls,
        name: str,
        owner_type: str,
        local_vault_key: str,
        vault_dir="~/.lxv/",
        logger=None,
    ):
        vault_dir = Path(vault_dir)
        if not vault_dir.exists():
            vault_dir.mkdir(parents=True)

        if not logger:
            logger = get_logger("AccessKey-get_or_create")

        created = datetime.now()
        updated = datetime.now()

        file = generate_access_key_path(name, vault_dir, owner_type)
        local_vault_key = Path(local_vault_key)
        if not local_vault_key.exists():
            logger.warning(
                f"Local vault key {local_vault_key} does not exist. Creating new key."
            )
            generate_ansible_key(local_vault_key)

        if not file.exists():
            logger.warning(
                f"Local vault key {local_vault_key} does not exist. Creating new key."
            )
            generate_ansible_key(file, local_vault_key)

        key = cls(
            name=name,
            file=file.as_posix(),
            vault_dir=vault_dir.as_posix(),
            local_vault_key=local_vault_key.as_posix(),
            created=created,
            updated=updated,
        )

        return key

    def read_key(self):
        file = Path(self.file)
        with open(file, "r") as f:
            return f.read()


def get_access_key(name, vault_dir: Path, owner_type="clients"):
    assert owner_type in OWNER_TYPES, f"Invalid owner_type: {owner_type}"
    access_key = AccessKey.get_or_create(
        name, owner_type, local_vault_key=vault_dir / "lxv.key", vault_dir=vault_dir
    )
    return access_key


class Secret(BaseModel):
    name: str
    directory: str
    access_key: AccessKey
    secret_type: str = (
        "password"  # password, id_ed25519, id_rsa, ssh_cert, gpg_key, gpg_cert
    )

    role_names: List[str] = []
    client_names: List[str] = []
    group_names: List[str] = []
    luxnix_names: List[str] = []

    created: Optional[datetime] = None
    updated: Optional[datetime] = None
    validity: Optional[timedelta] = timedelta(days=180)

    @classmethod
    def create_secret(cls, secret: str, name: str, file: str, access_key_path: str):
        access_key_path = Path(access_key_path)
        access_key = AccessKey
        import subprocess

        with open(file, "w") as f:
            f.write(secret)

        # use ansible-vault to encrypt the file using the access_key
        subprocess.run(
            [
                "ansible-vault",
                "encrypt",
                "--vault-password-file",
                access_key_path,
                file,
            ]
        )

        return cls(name=name, file=file, access_key=access_key)

    def generate_deployment_secrets():
        pass


def _get_by_name(obj_list: List[Union[Secret, AccessKey]], name: str, logger=None):
    if not logger:
        logger = get_logger("lx_vault__get_by_name")
    objs = [obj for obj in obj_list if obj.name == name]
    if not len(objs) <= 1:
        logger.warning(f"Found more than one object: {len(objs)}")

    if objs:
        return objs[0]
    else:
        return None


def _resolve_home(path: str) -> str:
    if not path.startswith("~/"):
        return path

    else:
        return Path(path).expanduser().as_posix()


class Vault(BaseModel):
    secrets: List[Secret] = []
    access_keys: List[AccessKey] = []
    dir: str = "~/.lxv/"
    key: str = "~/.lxv.key"
    inventory: Optional[AnsibleInventory] = None

    @classmethod
    def _get_vault_paths(cls, dir: str, key: str):
        dir = Path(dir).expanduser()
        key = Path(key).expanduser()
        vault = dir / "vault.yml"
        return dir, key, vault

    @classmethod
    def load_dir(cls, dir: str = "~/.lxv/", key: str = "~/.lxv.key"):
        import yaml

        dir, key, vault_file = cls._get_vault_paths(dir, key)

        if not dir.exists():
            raise FileNotFoundError(f"Directory {dir} does not exist!")

        if not vault_file.exists():
            raise FileNotFoundError(f"File {vault_file} does not exist!")

        with open(vault_file, "r") as f:
            data = yaml.load(f, Loader=yaml.SafeLoader)
        vault = cls.model_validate(data)
        return vault

    @classmethod
    def load_or_create(cls, dir: str = "~/.lxv/", key: str = "~/.lxv.key"):
        dir, key, vault_file = cls._get_vault_paths(dir, key)

        if not vault_file.exists():
            print("No vault file found. Creating new vault.")
            vault = cls()
            vault.save_to_file(vault_file)

        else:
            vault = cls.load_dir(dir, key)

    def save_to_file(self, file: str = None):
        """dump as yml"""
        if not file:
            file = Path(self.dir) / "vault.yml"
        else:  # make sure the directory exists
            file = Path(file)

        file: Path = file.expanduser()

        if not file.parent.exists():
            file.parent.mkdir(parents=True)

        raw = self.model_dump(
            mode="python",
        )
        file = Path(file)
        dump_yaml(raw, file, format_yaml, ansible_lint)

    # Utility Methods:
    def get_access_key_by_name(self, name: str, logger=None):
        if not logger:
            logger = get_logger("Vaults-get_access_key_by_name", reset=True)

        key = _get_by_name(self.access_keys, name, logger)
        return key

    def get_or_create_key(
        self,
        name: str,
        owner_type: str,
        local_vault_key: str,
        vault_dir="~/.lxv/",
        logger=None,
    ):
        if not logger:
            logger = get_logger("Vaults-get_or_create_key", reset=True)

        key = AccessKey.get_or_create(
            name, owner_type, local_vault_key, vault_dir, logger
        )
        self.access_keys.append(key)
        return key
