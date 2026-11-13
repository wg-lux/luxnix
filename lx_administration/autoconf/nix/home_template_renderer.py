"""Render Home Manager templates with the shared Nix literal contract."""

from pathlib import Path

from .template_renderer import nix_literal, render_nix_template

to_nix = nix_literal


def render_home_nix_template(
    template_dir: str | Path,
    template_name: str,
    config_data: dict[str, object],
) -> str:
    return render_nix_template(
        template_dir,
        template_name,
        config_data,
        filter_name="to_nix",
        trim_blocks=True,
        lstrip_blocks=True,
    )
