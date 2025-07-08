from jinja2 import Environment, FileSystemLoader
from typing import Dict, Any


def to_nix(value):
    if isinstance(value, str):
        return '"' + value.strip('"') + '"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def render_home_nix_template(
    template_dir: str, template_name: str, config_data: Dict[str, Any]
) -> str:
    #  Enable whitespace control
    env = Environment(
        loader=FileSystemLoader(template_dir),
        trim_blocks=True,    # Removes newlines after {% blocks %}
        lstrip_blocks=True   # Removes leading spaces before {% blocks %}
    )
    env.filters["to_nix"] = to_nix  # Inject the custom filter
    template = env.get_template(template_name)
    return template.render(**config_data)

