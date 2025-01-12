from typing import List


def get_host_configs(host_facts: dict, inventory: dict, subnet: str) -> dict:
    host_configs = {}

    for host, data in host_facts.items():
        ip_addresses: List[str] = data.get("ansible_facts", {}).get(
            "ansible_all_ipv4_addresses", []
        )
        ip_addresses = [_ for _ in ip_addresses if _.startswith(subnet[:-1])]

        assert len(ip_addresses) == 1, f"Expected one IP address, got {ip_addresses}"
        ip_address = ip_addresses[0]

        host_configs[host] = {
            "vpn_ip": ip_address,
            "hostname": host,
            "groups": [_ for _, __ in inventory.items() if host in __],
        }

    return host_configs
