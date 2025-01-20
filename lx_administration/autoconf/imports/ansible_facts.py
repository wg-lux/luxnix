import json
from lx_administration.models import AnsibleFactsModel, BiosModel, NetworkInterfaceModel
from pathlib import Path


def _flatten_fact_dict(facts: dict):
    assert len(list(facts.keys())) == 1
    key = list(facts.keys())[0]

    assert len(facts[key]) == 1

    facts = facts[key][0]

    assert "ansible_facts" in facts

    facts = facts["ansible_facts"]

    return facts


def _read_bios(facts: dict) -> BiosModel:
    return BiosModel(
        vendor=facts.get("ansible_bios_vendor"),
        version=facts.get("ansible_bios_version"),
        date=facts.get("ansible_bios_date"),
    )


def _read_network_interface(network_facts: dict) -> NetworkInterfaceModel:
    return NetworkInterfaceModel(
        interface=network_facts.get("interface"),
        address=network_facts.get("address"),
        netmask=network_facts.get("netmask"),
        gateway=network_facts.get("gateway"),
    )


def import_ansible_facts(json_path: str) -> AnsibleFactsModel:
    with open(json_path, "r") as f:
        data = json.load(f)

    facts = _flatten_fact_dict(data)

    bios = _read_bios(facts)
    _network_facts = facts.get("ansible_default_ipv4")
    network_interface = _read_network_interface(_network_facts)

    return AnsibleFactsModel(
        bios=bios,
        current_date=facts.get("ansible_date_time", {}).get("iso8601"),
        machine=facts.get("ansible_machine"),
        default_ipv4=network_interface,
        all_ipv4_addresses=facts.get("ansible_all_ipv4_addresses", []),
    )


def load_all_host_facts(facts_dir: Path) -> dict:
    """
    Load all host facts from a directory of json files.
    Resulting structure is a dictionary with hostnames as keys and facts as values.
    """
    facts = {}
    for fact_file in facts_dir.glob("*"):
        hostname = fact_file.name

        # Filename is hostname so we need to strip the extension
        if "." in hostname:
            hostname = hostname.split(".")[0]

        facts[hostname] = import_ansible_facts(fact_file)
    return facts
