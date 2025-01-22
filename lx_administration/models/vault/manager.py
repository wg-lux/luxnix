from pydantic import BaseModel
from typing import Optional, List, Dict, Union
from datetime import datetime, timedelta
from pathlib import Path
from lx_administration.logging import get_logger
import os
from lx_administration.yaml import dump_yaml, format_yaml, ansible_lint
from lx_administration.utils.paths import str2path


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

        return key, created

    def read_key(self):
        file = Path(self.file)
        with open(file, "r") as f:
            return f.read()


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


class SecretTemplate(BaseModel):
    owner_type: str
    template_dir: str

    @classmethod
    def create_template(cls, owner_type: str, template_dir: str):
        return cls(owner_type=owner_type, template_dir=template_dir)

    def get_template_dir(self, return_as_string=False):
        p = self.template_dir
        p = str2path(
            p, expanduser=True, resolve=True, return_as_string=return_as_string
        )
        return p


class Vault(BaseModel):
    secrets: List[Secret] = []
    access_keys: List[AccessKey] = []
    dir: str = "~/.lxv/"
    key: str = "~/.lxv.key"
    key_owner_types: List[str] = OWNER_TYPES.copy()
    inventory: Optional[AnsibleInventory] = None
    default_system_users: List[str] = ["admin"]
    subnet: str = "172.16.255."
    secret_templates: List[SecretTemplate] = []

    @classmethod
    def _get_vault_paths(cls, dir: str, key: str) -> Union[Tuple[Path, Path, Path]]:
        key = str2path(key, expanduser=True, resolve=False, return_as_string=False)
        dir = str2path(dir, expanduser=True, resolve=False, return_as_string=False)
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
            data = yaml.load(f, Loader=yaml.FullLoader)
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

    def load_inventory(self, inventory_file: str):
        """load inventory from file and set self.inventory"""

        self.inventory = AnsibleInventory.from_file(inventory_file)
        return self.inventory

    # def sync_secret_templates(self):
    #     inventory = self.inventory.model_copy()

    #     # extract roles
    #     role_names = inventory.get_role_names()

    #     # extract clients
    #     client_names = inventory.get_hostnames()

    #     # extract groups
    #     group_names = inventory.get_group_names()

    #     local_system_user_names = self.default_system_users

    def sync_inventory(self, inventory_file: str):
        logger = get_logger("Vaults-sync_inventory", reset=True)
        inventory_file: Path = Path(inventory_file)
        assert inventory_file.exists(), f"File {inventory_file} does not exist!"
        # read inventory file and set self.inventory
        vault_dir, _vault_key, vault_file = self.get_paths()
        logger.info(f"Loading inventory from {inventory_file}")
        _inventory = self.load_inventory(inventory_file.resolve().as_posix())

        # TODO Update stuff

        self.save_to_file()

    # def fetch_secret_list_from_inventory(self):

    def get_paths(self):
        return self._get_vault_paths(self.dir, self.key)

    def save_to_file(self, file: str = None):
        """dump as yml"""
        if not file:
            vault_dir, _vault_key, vault_file = self.get_paths()
        else:
            vault_file = Path(file)
            vault_dir = vault_file.parent

        if not vault_dir.exists():
            vault_dir.mkdir(parents=True)

        raw = self.model_dump(mode="python", round_trip=True)
        print("save to file", vault_file)
        dump_yaml(raw, vault_file, format_yaml, ansible_lint)

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

        assert owner_type in self.key_owner_types, f"Invalid owner_type: {owner_type}"

        key = AccessKey.get_or_create(
            name, owner_type, local_vault_key, vault_dir, logger
        )
        self.access_keys.append(key)
        return key
