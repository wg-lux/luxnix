from lx_administration.logging import get_logger
from icecream import ic


def get_secrets_for_access_keys(access_keys, all_secrets, logger=None):
    matched_secrets = []
    if not logger:
        logger = get_logger("get_secrets_for_access_keys", reset=True)

    # iterate over all secrets and check if the secrets access key is
    # in the list of access keys
    for secret in all_secrets:
        access_key = secret.get("access_key")
        if access_key in access_keys:
            matched_secrets.append(secret)

    logger.info(f"Matched Secrets: {matched_secrets}")

    return matched_secrets


def get_access_keys_for_client(client, all_access_keys, logger=None):
    matched_keys = []
    if not logger:
        logger = get_logger("get_access_keys_for_client", reset=True)

    all_access_keys = [ak.model_dump() for ak in all_access_keys]

    logger.info("-----get_access_keys_for_client-----")

    roles = client.get("ansible_role_names", [])
    groups = client.get("ansible_group_names", [])
    hostname = client.get("hostname", "")

    logger.info(f"Hostname: {hostname}")
    logger.info(f"Roles: {roles}")
    logger.info(f"Groups: {groups}")

    for ak in all_access_keys:
        owner_type = ak.get("owner_type", "")
        ak_name = ak.get("name", "")

        assert owner_type, "owner_type is required"
        assert ak_name, "ak_name is required"

        if owner_type == "roles":
            if ak_name in roles:
                matched_keys.append(ak)
        elif owner_type == "groups":
            if ak_name in groups:
                matched_keys.append(ak)
        elif owner_type == "local":
            if ak_name.endswith(f"@{hostname}"):
                matched_keys.append(ak)

        else:
            logger.warning(f"Unknown owner_type: {owner_type}")

    logger.info(f"Matched Keys: {matched_keys}")

    return matched_keys
