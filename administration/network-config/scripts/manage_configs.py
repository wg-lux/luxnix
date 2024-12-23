#!/usr/bin/env python3
"""
manage_configs.py
Script to validate and process network_config.yaml
"""

import os
import sys
import yaml
from jinja2 import Environment, FileSystemLoader
from jsonschema import validate, ValidationError

SCHEMA_FILE = os.path.join('schemas', 'network_config.schema.yaml')
CONFIG_FILE = os.path.join('config', 'network_config.yaml')
CCD_OUTPUT_DIR = os.path.join('output', 'openvpn_ccd')
TEMPLATE_DIR = 'templates'
CCD_TEMPLATE_FILE = 'openvpn_ccd_template.j2'


def load_yaml(file_path):
    """Loads a YAML file and returns Python dict."""
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)


def load_schema(schema_path):
    """Loads a JSON/YAML schema file."""
    return load_yaml(schema_path)


def validate_config(config_data, schema_data):
    """Validates config_data against schema_data."""
    try:
        validate(instance=config_data, schema=schema_data)
        print("Schema validation passed.")
    except ValidationError as e:
        print(f"Schema validation failed: {e.message}")
        sys.exit(1)


def check_uniqueness(config_data):
    """Ensure hostnames and openvpn IPs are unique."""
    hostnames = []
    openvpn_ips = []

    for system in config_data.get('systems', []):
        hn = system['hostname']
        ip = system['openvpnIp']

        if hn in hostnames:
            raise ValueError(f"Duplicate hostname detected: {hn}")
        if ip in openvpn_ips:
            raise ValueError(f"Duplicate OpenVPN IP detected: {ip}")

        hostnames.append(hn)
        openvpn_ips.append(ip)

    print("Uniqueness checks passed (hostnames, IPs).")


def render_openvpn_ccd(config_data):
    """Render a CCD file for each system to CCD_OUTPUT_DIR."""
    if not os.path.exists(CCD_OUTPUT_DIR):
        os.makedirs(CCD_OUTPUT_DIR)

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    template = env.get_template(CCD_TEMPLATE_FILE)

    systems = config_data.get('systems', [])
    for system in systems:
        hostname = system['hostname']
        openvpn_ip = system['openvpnIp']
        
        # Render template
        ccd_content = template.render(openvpnIp=openvpn_ip)
        
        # Write CCD file named after hostname
        ccd_file_path = os.path.join(CCD_OUTPUT_DIR, hostname)
        with open(ccd_file_path, 'w') as f:
            f.write(ccd_content)
        
        print(f"Generated CCD file for {hostname}")


def main():
    """Main entry point for validation and generation."""
    config_data = load_yaml(CONFIG_FILE)
    schema_data = load_schema(SCHEMA_FILE)

    # 1) Validate YAML structure via JSON Schema
    validate_config(config_data, schema_data)

    # 2) Additional checks: uniqueness
    check_uniqueness(config_data)

    # 3) Render CCD files for each system
    render_openvpn_ccd(config_data)


if __name__ == "__main__":
    main()
