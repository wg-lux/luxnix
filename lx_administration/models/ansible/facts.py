"""Validated subset of Ansible facts used by Autoconf."""

from pydantic import BaseModel, Field

from ..hardware import BiosModel, NetworkInterfaceModel


class AnsibleFactsModel(BaseModel):
    """Facts retained when generating LuxNix host configuration."""

    bios: BiosModel
    current_date: str | None
    machine: str | None
    default_ipv4: NetworkInterfaceModel | None
    all_ipv4_addresses: list[str] = Field(default_factory=list)
