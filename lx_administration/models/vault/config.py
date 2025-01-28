import yaml
from datetime import datetime as dt, timedelta as td
from ..config import DEFAULT_USERS


def datetime_representer(dumper, data):
    """Custom representer for datetime objects"""
    return dumper.represent_scalar("tag:yaml.org,2002:str", data.isoformat())


def timedelta_representer(dumper, data):
    """Custom representer for timedelta objects - using ISO format"""
    return dumper.represent_scalar("tag:yaml.org,2002:str", f"P{data.days}D")


yaml.add_representer(dt, datetime_representer, Dumper=yaml.SafeDumper)
yaml.add_representer(td, timedelta_representer, Dumper=yaml.SafeDumper)

OWNER_TYPES = ["local", "roles", "services", "luxnix", "clients", "groups"]
SECRET_TYPES = [
    "password",
    "system_password",
    "id_ed25519",
    "id_rsa",
    "ssh_cert",
    "openvpn_cert",
    # Removed "vault_key" as it's replaced by pre-shared key system
]


LOCAL_USER_SECRET_TYPES = ["password", "id_ed25519", "id_rsa"]
for _ in LOCAL_USER_SECRET_TYPES:
    assert _ in SECRET_TYPES, f"Invalid secret_type: {_}"

BASE_CLIENT_SECRET_TYPES = [
    "id_ed25519",
    "id_rsa",
    "ssh_cert",
    "openvpn_cert",
]

# New PSK configuration
PSK_DIR = "psk"  # Directory under vault dir for pre-shared keys
PSK_LENGTH = 32  # Length in bytes for pre-shared keys
