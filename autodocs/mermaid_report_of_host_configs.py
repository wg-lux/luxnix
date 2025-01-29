import yaml
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, RootModel
import os

# Get the script's directory
BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

# Use absolute paths based on script location
HOST_CONFIGS_PATH = BASE_DIR / "../autoconf/host_configs_25-01-17.yml"
MERMAID_MARKDOWN_PATH = BASE_DIR / "../autoconf/host_data_report.md"
MERMAID_HTML_PATH = BASE_DIR / "../autoconf/host_data_report.html"

"""# Explicitly define the paths #automatic base path doesn't work
HOST_CONFIGS_PATH = Path("../autoconf/host_configs_25-01-17.yml")
MERMAID_MARKDOWN_PATH = Path("../autoconf/host_data_report.md")
MERMAID_HTML_PATH = Path("../autoconf/host_data_report.html")
"""

# Validate that the input file exists
if not HOST_CONFIGS_PATH.exists():
    raise FileNotFoundError(f"Input file {HOST_CONFIGS_PATH} does not exist!")

# Pydantic Models for Validation
class HostConfig(BaseModel):
    hostname: Optional[str]
    groups: List[str] = []
    host_vars: Optional[Dict] = {}
    role_configs: Optional[Dict] = {}
    host_services: Optional[Dict] = {}
    luxnix_configs: Optional[Dict] = {}
    vpn_ip: Optional[str] = None

class HostsData(RootModel[Dict[str, HostConfig]]):
    def parse_host_data(self) -> Dict[str, Dict]:
        """
        Extracts and structures host data, including groups, roles, IPs, services, and settings.
        """
        host_data = {}
        for host_name, config in self.root.items():
            hostname = config.hostname or host_name
            roles = list(config.role_configs.keys()) if config.role_configs else []
            services = list(config.host_services.keys())
            settings = list(config.luxnix_configs.keys())
            ip = config.vpn_ip

            host_data[hostname] = {
                "groups": config.groups,
                "roles": list(set(roles)),  # Deduplicate roles
                "services": services,
                "settings": settings,
                "ip": ip,
            }
        return host_data

# Function to generate host-to-group mapping
def generate_host_to_group_mapping(host_data: Dict[str, Dict]) -> str:
    """
    Generates a Mermaid.js diagram for host-to-group mapping.
    """
    lines = ["flowchart"]
    lines.append("  classDef hostStyle fill:#ede7f6,stroke:#5e35b1,stroke-width:2px;")
    lines.append("  classDef groupStyle fill:#f8f8f8,stroke:#888,stroke-width:1.5px;")
    
    for host, details in host_data.items():
        for group in details["groups"]:
            lines.append(f"  {host}[\"{host}\"]:::hostStyle --> {group}[\"{group}\"]:::groupStyle")
    return "\n".join(lines)

# Function to generate group-to-host mapping
def generate_group_to_host_mapping(host_data: Dict[str, Dict]) -> str:
    """
    Generates a Mermaid.js diagram for group-to-host mapping.
    """
    lines = ["flowchart"]
    lines.append("  classDef groupStyle fill:#f8f8f8,stroke:#888,stroke-width:1.5px;")
    lines.append("  classDef hostStyle fill:#ede7f6,stroke:#5e35b1,stroke-width:2px;")
    
    for host, details in host_data.items():
        for group in details["groups"]:
            lines.append(f"  {group}[\"{group}\"]:::groupStyle --> {host}[\"{host}\"]:::hostStyle")
    return "\n".join(lines)

# Updated function to generate host-to-role mapping
def generate_host_role_mapping(host_data: Dict[str, Dict]) -> str:
    """
    Generates a Mermaid.js diagram for host-to-role mapping with hierarchical grouping,
    applying unique colors for each hierarchy level.
    """
    lines = ["flowchart TB"]
    # Define colors for hierarchy levels
    lines.append("  classDef hostStyle fill:#ede7f6,stroke:#5e35b1,stroke-width:2px;")  # Hosts in purple
    lines.append("  classDef roleStyleLevel1 fill:#ffebee,stroke:#d32f2f,stroke-width:2px;")  # Level 1 in red
    lines.append("  classDef roleStyleLevel2 fill:#e3f2fd,stroke:#0288d1,stroke-width:2px;")  # Level 2 in blue
    lines.append("  classDef roleStyleLevel3 fill:#e8f5e9,stroke:#388e3c,stroke-width:2px;")  # Level 3 in green
    lines.append("  classDef roleStyleLevel4 fill:#fff9c4,stroke:#f9a825,stroke-width:2px;")  # Level 4 in yellow

    def build_hierarchy(roles):
        """
        Parses roles into a nested dictionary.
        """
        hierarchy = {}
        for role in roles:
            parts = role.split(".")
            current = hierarchy
            for part in parts:
                if part not in current:
                    current[part] = {}
                current = current[part]
        return hierarchy

    def render_hierarchy(parent_id, hierarchy, level=1):
        """
        Recursively renders the hierarchy into Mermaid.js format, with colors per level.
        """
        class_name = f"roleStyleLevel{min(level, 4)}"  # Limit levels to 4 predefined styles
        for key, children in hierarchy.items():
            node_id = f"{parent_id}_{key.replace('-', '_').replace('.', '_')}"
            lines.append(f'  {node_id}["{key}"]:::{class_name}')
            lines.append(f"  {parent_id} --> {node_id}")
            render_hierarchy(node_id, children, level + 1)

    for host, details in host_data.items():
        # Add host and role count nodes
        role_count = len(details["roles"])
        lines.append(f"  {host}[\"{host}\"]:::hostStyle")
        lines.append(f"  RoleCount_{host}{{\"{role_count} roles\"}}:::roleStyleLevel1")
        lines.append(f"  {host} --> RoleCount_{host}")

        # Build and render the hierarchy
        hierarchy = build_hierarchy(details["roles"])
        render_hierarchy(f"RoleCount_{host}", hierarchy)

    return "\n".join(lines)
   


# Function to generate host-to-IP mapping
def generate_host_ip_mapping(host_data: Dict[str, Dict]) -> str:
    """
    Generates a Mermaid.js diagram for host-to-IP mapping.
    """
    lines = ["flowchart"]
    lines.append("  classDef hostStyle fill:#ede7f6,stroke:#5e35b1,stroke-width:2px;")
    lines.append("  classDef ipStyle fill:#e3f2fd,stroke:#1e88e5,stroke-width:2px;")
    
    for host, details in host_data.items():
        ip = details["ip"] or "No IP Assigned"
        lines.append(f"  {host}[\"{host}\"]:::hostStyle --> {host}_IP[\"IP: {ip}\"]:::ipStyle")
    return "\n".join(lines)

def generate_host_service_mapping(host_data: Dict[str, Dict]) -> str:
    """
    Generates a Mermaid.js diagram for host-to-service mapping.
    If no services are defined for any host, it shows a "No services available" message.
    """
    lines = ["flowchart TD"]
    lines.append("  classDef hostStyle fill:#ede7f6,stroke:#5e35b1,stroke-width:2px;")  # Hosts in purple
    lines.append("  classDef serviceStyle fill:#fff9c4,stroke:#fbc02d,stroke-width:2px;")  # Services in yellow

    # Check if there are any services defined for any host
    has_services = any(details["services"] for details in host_data.values())

    if not has_services:
        # Add a single "No services available" node if no services exist
        lines.append("  NoServices[\"No services available\"]:::serviceStyle")
    else:
        for host, details in host_data.items():
            # Host node
            lines.append(f"  {host}[\"{host}\"]:::hostStyle")
            
            for service in details["services"]:
                # Service nodes
                lines.append(f"  {host} --> {host}_{service}[\"Service: {service}\"]:::serviceStyle")

    return "\n".join(lines)



# Function to generate host-to-settings mapping
def generate_host_settings_mapping(host_data: Dict[str, Dict]) -> str:
    """
    Generates a Mermaid.js diagram for host-to-settings mapping, replacing dots with spaces in setting names,
    and displaying counts without any shapes. Background for settings is light grey for better readability.
    """
    lines = ["flowchart TB"]
    lines.append("  classDef hostStyle fill:#ede7f6,stroke:#5e35b1,stroke-width:2px;")  # Hosts in purple
    lines.append("  classDef settingStyle fill:#f8f9fa,stroke:#6c757d,stroke-width:2px;")  # Settings in light grey

    for host, details in host_data.items():
        setting_count = len(details["settings"])
        settings = [setting.replace(".", " ") for setting in details["settings"]]  # Remove dots, replace with spaces
        settings_str = ", ".join(settings) if settings else "No Settings Configured"

        # Host node
        lines.append(f"  {host}[\"{host}\"]:::hostStyle")
        
        # Settings detail node
        lines.append(f'  SettingDetails_{host}["{settings_str}"]:::settingStyle')
        
        # Connect host to settings detail with a count label on the edge
        lines.append(f"  {host} --> |{setting_count} settings| SettingDetails_{host}")

    return "\n".join(lines)
   

# Function to write Mermaid diagrams to Markdown
def write_to_markdown(host_data: Dict[str, Dict], output_path: Path):
    content = []

    
     # Group-to-Host Mapping
    content.append("\n## Group-to-Host Mapping")
    content.append("```mermaid")
    content.append(generate_group_to_host_mapping(host_data))
    content.append("```")
    
    # Host-to-Group Mapping
    content.append("# Host-to-Group Mapping")
    content.append("```mermaid")
    content.append(generate_host_to_group_mapping(host_data))
    content.append("```")

   

    # Host-to-Role Mapping
    content.append("\n## Host-to-Role Mapping")
    content.append("```mermaid")
    content.append(generate_host_role_mapping(host_data))
    content.append("```")

    # Host-to-IP Mapping
    content.append("\n## Host-to-IP Mapping")
    content.append("```mermaid")
    content.append(generate_host_ip_mapping(host_data))
    content.append("```")

    # Host-to-Services Mapping
    content.append("\n## Host-to-Services Mapping")
    content.append("```mermaid")
    content.append(generate_host_service_mapping(host_data))
    content.append("```")

    # Host-to-Settings Mapping
    content.append("\n## Host-to-Settings Mapping")
    content.append("```mermaid")
    content.append(generate_host_settings_mapping(host_data))
    content.append("```")

    # Write to file
    output_path.write_text("\n".join(content))
    print(f"Markdown file with Mermaid diagrams saved to: {output_path}")

# Function to write Mermaid diagrams to HTML
def write_to_html(host_data: Dict[str, Dict], output_path: Path):
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
        <script>mermaid.initialize({ startOnLoad: true });</script>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            h1, h2 { color: #333; }
            .mermaid { margin: 20px 0; }
        </style>
    </head>
    <body>
        <h1>Host Data Report</h1>
    """
      # Group-to-Host Mapping
    html_content += """
        <h2>Group-to-Host Mapping</h2>
        <div class="mermaid">
    """
    html_content += generate_group_to_host_mapping(host_data)
    html_content += "</div>"

    # Host-to-Group Mapping
    html_content += """
        <h2>Host-to-Group Mapping</h2>
        <div class="mermaid">
    """
    html_content += generate_host_to_group_mapping(host_data)
    html_content += "</div>"


    # Host-to-Role Mapping
    html_content += """
        <h2>Host-to-Role Mapping</h2>
        <div class="mermaid">
    """
    html_content += generate_host_role_mapping(host_data)
    html_content += "</div>"

    # Host-to-IP Mapping
    html_content += """
        <h2>Host-to-IP Mapping</h2>
        <div class="mermaid">
    """
    html_content += generate_host_ip_mapping(host_data)
    html_content += "</div>"

    # Host-to-Services Mapping
    html_content += """
        <h2>Host-to-Services Mapping</h2>
        <div class="mermaid">
    """
    html_content += generate_host_service_mapping(host_data)
    html_content += "</div>"

    # Host-to-Settings Mapping
    html_content += """
        <h2>Host-to-Settings Mapping</h2>
        <div class="mermaid">
    """
    html_content += generate_host_settings_mapping(host_data)
    html_content += "</div>"

    html_content += """
    </body>
    </html>
    """
    output_path.write_text(html_content)
    print(f"HTML file with Mermaid diagrams saved to: {output_path}")

# Main function
def main():
    with open(HOST_CONFIGS_PATH, "r") as f:
        raw_data = yaml.safe_load(f)

    hosts_data = HostsData.model_validate(raw_data)
    host_data = hosts_data.parse_host_data()

    # Generate Markdown and HTML reports
    write_to_markdown(host_data, MERMAID_MARKDOWN_PATH)
    write_to_html(host_data, MERMAID_HTML_PATH)

    print("\nReports generated successfully!")
    print(f"- Markdown: {MERMAID_MARKDOWN_PATH}")
    print(f"- HTML: {MERMAID_HTML_PATH}")

if __name__ == "__main__":
    main()

