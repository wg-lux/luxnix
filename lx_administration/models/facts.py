import pydantic
from pydantic import BaseModel
from typing import List, Optional
import json
from .ansible import AnsibleFactsModel


class HostConfigModel(BaseModel):
    vpn_ip: str
    hostname: str
    groups: List[str]
    role_configs: dict = {}
    service_configs: dict = {}
    luxnix_configs: dict = {}
    ansible_facts: AnsibleFactsModel
