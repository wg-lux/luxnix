from pydantic import BaseModel, Field
from typing import List, Optional
from ..hardware import BiosModel, NetworkInterfaceModel


class AnsibleFactsModel(BaseModel):
    bios: BiosModel
    current_date: Optional[str]
    machine: Optional[str]
    default_ipv4: Optional[NetworkInterfaceModel]
    all_ipv4_addresses: List[str] = Field(default_factory=list)
