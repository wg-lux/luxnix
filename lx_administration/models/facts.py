from pydantic import BaseModel, Field
from typing import List
from .ansible.facts import AnsibleFactsModel


class HostConfigModel(BaseModel):
    vpn_ip: str
    hostname: str
    groups: List[str]
    role_configs: dict = Field(default_factory=dict)
    service_configs: dict = Field(default_factory=dict)
    luxnix_configs: dict = Field(default_factory=dict)
    ansible_facts: AnsibleFactsModel
