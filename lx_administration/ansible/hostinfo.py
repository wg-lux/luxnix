# lx_administration/ansible/hostinfo.py
# Pydantic Class to parse ansible host information.json files (from hostinfo.json)

from pydantic import BaseModel
from typing import List, Dict, Optional
from pathlib import Path
import json
from datetime import datetime as dt
from datetime import datetime

TEST_FILE = Path("example.json")


class AnsibleMount(BaseModel):
    block_available: int
    block_size: int
    block_total: int
    block_used: int
    device: str
    dump: int
    fstype: str
    mount: Path
    options: str
    size_available: int
    size_total: int
    uuid: str

    @property
    def parsed_options(self) -> List[str]:
        return self.options.split(",")


class AnsibleLocallyReachableIps(BaseModel):
    ipv4: List[str] = []
    ipv6: List[str] = []


class AnsibleEnv(BaseModel):
    FLAKE: Path
    HOME: Path
    PATH: str
    PWD: Path
    USER: str
    LANG: str


class AnsibleDefaultIpV4(BaseModel):
    address: str
    broadcast: str
    netmask: str
    network: str
    prefix: int
    type: str
    interface: str
    macaddress: str
    mtu: int
    interface: str
    alias: str


class AnsibleDateTime(BaseModel):
    date: str
    weeknumber: int
    iso8601_basic: str
    tz: str
    tz_dst: str
    tz_offset: str
    weekday: str
    weekday_number: int

    @property
    def parsed_date(self) -> Optional[datetime]:
        try:
            return datetime.strptime(self.date, "%Y-%m-%d")
        except ValueError:
            return None

    @property
    def parsed_iso_date(self) -> Optional[datetime]:
        try:
            return datetime.strptime(self.iso8601_basic, "%Y%m%dT%H%M%S%f")
        except ValueError:
            return None


class AnsibleCmdline(BaseModel):
    init: Path
    initrd: str
    loglevel: str
    quiet: bool
    resume: str
    root: str
    splash: bool


class _PyVersion(BaseModel):
    major: int
    minor: int
    micro: int
    releaselevel: str
    serial: int


class AnsiblePython(BaseModel):
    executable: Path
    version: _PyVersion


class AnsibleFacts(BaseModel):
    ansible_all_ipv4_addresses: List[str] = []
    ansible_all_ipv6_addresses: List[str] = []
    ansible_architecture: str
    ansible_board_name: str
    ansible_board_vendor: str
    ansible_board_version: str
    ansible_date_time: AnsibleDateTime
    # ansible_cmdline: AnsibleCmdline
    ansible_distribution: str
    ansible_board_name: str
    ansible_distribution_release: str
    ansible_distribution_version: str
    # ansible_env: AnsibleEnv
    # ansible_flags: List[str]
    ansible_interfaces: List[str]
    ansible_kernel: str
    ansible_mounts: List[AnsibleMount]
    ansible_nodename: str
    # ansible_processor: List[str]
    ansible_processor_cores: int
    ansible_processor_count: int
    ansible_processor_nproc: int
    ansible_processor_threads_per_core: int
    ansible_processor_vcpus: int
    ansible_product_name: str
    ansible_python: AnsiblePython
    ansible_python_version: str
    ansible_ssh_host_key_ed25519_public: str
    ansible_ssh_host_key_rsa_public: str
    ansible_system: str
    ansible_swapfree_mb: int
    ansible_swaptotal_mb: int


class HostInfo(BaseModel):
    name: str
    hostvars: Dict[str, str]
    ansible_facts: AnsibleFacts

    @property
    def result_path(self) -> Path:
        return Path(f"conf/hostinfos/{self.name}.json")

    def auto_dump_json(self):
        json_data = self.model_dump_json(indent=4)
        with open(self.result_path, "w") as file:
            file.write(json_data)


if __name__ == "__main__":
    with open(TEST_FILE, "r") as f:
        data = json.load(f)

    hosts = []
    for hostname, hostinfo in data.items():
        hosts.append(HostInfo(**hostinfo))

    for hostinfo in hosts:
        hostinfo.auto_dump_json()
