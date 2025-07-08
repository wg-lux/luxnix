from pathlib import Path
from lx_administration.logging import get_logger, log_heading
from lx_administration.models import MergedHostVars
from .home_template_renderer import render_home_nix_template as render_nix_template
from .utils import write_nix_file



def home_pipe(autoconf_out: Path, nix_template_dir: Path, nix_out: Path, logger=None):
    if not logger:
        logger = get_logger("home_pipe", reset=True)

    merged_vars_dir = autoconf_out

    for merged_vars_file in merged_vars_dir.glob("*.yml"):
        hostname = merged_vars_file.stem
        merged_vars = MergedHostVars.load_home_from_file(merged_vars_file)
        platform = merged_vars.get_host_platform()
        users = merged_vars.system_users or ["admin"] #this needs to ensure

        # Move logging after the merged_vars_file is loaded
        logger.info(f"Loading merged vars from: {merged_vars_file}")
        logger.info(f"Platform = {platform}")

        for user in users:
            #home_config = merged_vars.prepare_home_config()
            home_config = merged_vars.prepare_home_config(username=user)



            template_path = nix_template_dir / "homes" / platform
            rendered = render_nix_template(
                template_path,
                "default.nix.j2",
                home_config,
            )

            output_path = nix_out / "homes" / platform / f"{user}@{hostname}" / "default.nix"
            output_path.parent.mkdir(parents=True, exist_ok=True)

            #print(f"[WRITE] ---------- Writing home config for {user}@{hostname}")
            #print(f"[WRITE] ---------- Output path: {output_path}")

            write_nix_file(rendered, output_path, logger)

            #print("forth")

            # Logging after rendering
            logger.info(f"Template path: {template_path}")
            logger.info(f"Rendered: {rendered}")
            if output_path.exists():
                logger.info("File exists after write!")
            else:
                logger.warning("File write may have failed!")
