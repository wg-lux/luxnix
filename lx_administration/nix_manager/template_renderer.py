# my_nix_manager/template_renderer.py
from jinja2 import Environment, FileSystemLoader
import os
from typing import Dict, Any


def render_nix_template(
    template_dir: str, template_name: str, config_data: Dict[str, Any]
) -> str:
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template(template_name)
    return template.render(**config_data)
