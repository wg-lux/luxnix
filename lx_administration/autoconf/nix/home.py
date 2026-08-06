"""Render Home Manager configurations from merged Autoconf host data."""

import logging

from jinja2 import TemplateError

from lx_administration.logging import get_logger
from lx_administration.models import MergedHostVars

from ..config import AutoconfConfig
from ..errors import AutoconfPipelineError
from .home_template_renderer import render_home_nix_template as render_nix_template
from .utils import RenderedNixOutput


def render_home_outputs(
    config: AutoconfConfig,
    logger: logging.Logger | None = None,
) -> list[RenderedNixOutput]:
    """Render every Home Manager output without publishing files."""
    if logger is None:
        logger = get_logger(
            "autoconf_home_render",
            log_dir=config.log_dir,
            reset=True,
        )

    rendered_outputs: list[RenderedNixOutput] = []
    for merged_vars_file in sorted(config.output_layout.home_vars_dir.glob("*.yml")):
        hostname = merged_vars_file.stem
        try:
            merged_vars = MergedHostVars.load_home_from_file(merged_vars_file)
            platform = merged_vars.get_host_platform()
        except ValueError as exc:
            raise AutoconfPipelineError(
                f"Cannot render Home Manager configuration for {hostname} "
                f"({type(exc).__name__})"
            ) from exc
        users = merged_vars.system_users or config.home_default_users

        logger.info("Loading Home Manager variables from %s", merged_vars_file)
        logger.info("Home Manager platform: %s", platform)

        template_path = config.template_layout.home_template_dir(platform)
        if not template_path.is_dir():
            raise AutoconfPipelineError(
                f"Home Manager template directory not found: {template_path}"
            )
        for user in users:
            try:
                home_config = merged_vars.prepare_home_config(
                    username=user,
                    state_version=config.home_state_version,
                )
                rendered = render_nix_template(
                    template_path,
                    "default.nix.j2",
                    home_config,
                )
            except (TypeError, ValueError, TemplateError) as exc:
                raise AutoconfPipelineError(
                    f"Cannot render Home Manager configuration for "
                    f"{user}@{hostname} ({type(exc).__name__})"
                ) from exc
            output_path = config.nix_output_layout.home_file(platform, user, hostname)
            rendered_outputs.append((output_path, rendered))

    return rendered_outputs
