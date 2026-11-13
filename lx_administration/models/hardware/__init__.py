"""Hardware facts retained by the Autoconf data models."""

from pydantic import BaseModel


class BiosModel(BaseModel):
    """BIOS identity reported by Ansible."""

    vendor: str | None
    version: str | None
    date: str | None


class NetworkInterfaceModel(BaseModel):
    """Default network interface reported by Ansible."""

    interface: str | None
    address: str | None
    netmask: str | None
    gateway: str | None
