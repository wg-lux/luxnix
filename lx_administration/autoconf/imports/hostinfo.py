from pathlib import Path
import yaml
import json


def load_host_facts(facts_path: Path) -> dict:
    """Load a json file containing host facts"""
    with open(facts_path, "r") as f:
        return json.load(f)


def load_all_host_facts(facts_dir: Path) -> dict:
    """
    Load all host facts from a directory of json files.
    Resulting structure is a dictionary with hostnames as keys and facts as values.
    """
    facts = {}
    for fact_file in facts_dir.glob("*"):
        hostname = fact_file.name
        facts[hostname] = load_host_facts(fact_file)
    return facts
