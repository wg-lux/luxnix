from lx_administration.models.vault.hosts import VaultClient, HostConfig


def mock_vault_client(name="test_client"):
    return VaultClient(name=name)


def mock_host_config(hostname="test_host"):
    return HostConfig(
        hostname=hostname,
        ip_address="192.168.0.1",
        # ...other fields...
    )
