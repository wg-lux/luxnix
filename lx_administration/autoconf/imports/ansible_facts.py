import json
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from lx_administration.models.ansible.facts import AnsibleFactsModel
from lx_administration.models.hardware import BiosModel, NetworkInterfaceModel

from ..errors import AnsibleFactFormatError

FactMapping = dict[str, object]


def _invalid_structure(source: Path) -> AnsibleFactFormatError:
    return AnsibleFactFormatError(
        f"Invalid Ansible fact snapshot structure: {source.name}"
    )


def _fact_mapping(value: object, source: Path) -> FactMapping:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise _invalid_structure(source)
    return cast("FactMapping", value)


def _extract_ansible_facts(data: object, source: Path) -> FactMapping:
    """Accept raw Ansible setup output and the normalized on-disk wrapper."""
    result: object = data
    if isinstance(data, dict) and "ansible_facts" not in data and len(data) == 1:
        wrapped_result = next(iter(data.values()))
        if isinstance(wrapped_result, list) and len(wrapped_result) == 1:
            result = wrapped_result[0]

    result_mapping = _fact_mapping(result, source)
    if bool(result_mapping.get("failed", False)):
        raise _invalid_structure(source)

    return _fact_mapping(result_mapping.get("ansible_facts"), source)


def _read_bios(facts: FactMapping) -> BiosModel:
    return BiosModel.model_validate(
        {
            "vendor": facts.get("ansible_bios_vendor"),
            "version": facts.get("ansible_bios_version"),
            "date": facts.get("ansible_bios_date"),
        }
    )


def _read_network_interface(network_facts: FactMapping) -> NetworkInterfaceModel:
    return NetworkInterfaceModel.model_validate(
        {
            "interface": network_facts.get("interface"),
            "address": network_facts.get("address"),
            "netmask": network_facts.get("netmask"),
            "gateway": network_facts.get("gateway"),
        }
    )


def import_ansible_facts(json_path: str | Path) -> AnsibleFactsModel:
    source = Path(json_path)
    try:
        data: object = json.loads(source.read_text())
    except json.JSONDecodeError as error:
        raise AnsibleFactFormatError(
            f"Invalid JSON in Ansible fact snapshot: {source.name}"
        ) from error

    facts = _extract_ansible_facts(data, source)

    date_value = facts.get("ansible_date_time")
    network_value = facts.get("ansible_default_ipv4")
    date_facts = _fact_mapping({} if date_value is None else date_value, source)
    network_facts = _fact_mapping(
        {} if network_value is None else network_value,
        source,
    )

    try:
        return AnsibleFactsModel.model_validate(
            {
                "bios": _read_bios(facts),
                "current_date": date_facts.get("iso8601"),
                "machine": facts.get("ansible_machine"),
                "default_ipv4": _read_network_interface(network_facts),
                "all_ipv4_addresses": facts.get("ansible_all_ipv4_addresses", []),
            }
        )
    except ValidationError as error:
        raise AnsibleFactFormatError(
            f"Invalid Ansible fact snapshot values: {source.name}"
        ) from error


def load_all_host_facts(facts_dir: Path) -> dict[str, AnsibleFactsModel]:
    """
    Load all host facts from a directory of json files.
    Resulting structure is a dictionary with hostnames as keys and facts as values.
    """
    facts: dict[str, AnsibleFactsModel] = {}
    for fact_file in sorted(facts_dir.glob("*.json")):
        facts[fact_file.stem] = import_ansible_facts(fact_file)
    return facts
