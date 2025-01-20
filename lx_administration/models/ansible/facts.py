import pydantic
from pydantic import BaseModel
from typing import List, Optional
import json
from ..hardware import BiosModel, NetworkInterfaceModel


class AnsibleFactsModel(BaseModel):
    bios: BiosModel
    current_date: Optional[str]
    machine: Optional[str]
    default_ipv4: Optional[NetworkInterfaceModel]
    all_ipv4_addresses: List[str] = []
