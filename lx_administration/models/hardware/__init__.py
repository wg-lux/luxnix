from typing import Optional
from pydantic import BaseModel


class BiosModel(BaseModel):
    vendor: Optional[str]
    version: Optional[str]
    date: Optional[str]


class NetworkInterfaceModel(BaseModel):
    interface: Optional[str]
    address: Optional[str]
    netmask: Optional[str]
    gateway: Optional[str]
