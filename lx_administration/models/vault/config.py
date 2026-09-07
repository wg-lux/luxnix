OWNER_TYPES = ["local", "roles", "services", "luxnix", "clients", "groups"]
SECRET_TYPES = [
    "password",
    "system_password",
    "id_ed25519",
    "id_rsa",
    "ssh_cert",
    "openvpn_cert",
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
