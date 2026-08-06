import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lx_administration.autoconf import (  # noqa: E402
    AUTOCONF_OPTION_NAMES,
    DEFAULT_CONFIG_PATH,
    AutoconfConfig,
    AutoconfConfigError,
    AutoconfPipelineError,
)
from lx_administration.autoconf.main import run_pipeline  # noqa: E402

# Refresh local host facts when needed with:
# devenv tasks run autoconf:refresh-facts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate LuxNix configurations from the central autoconf YAML config."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"configuration file (default: {DEFAULT_CONFIG_PATH})",
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--check",
        action="store_true",
        help="validate and display resolved options without generating files",
    )
    action.add_argument(
        "--print-option",
        choices=AUTOCONF_OPTION_NAMES,
        help="print one resolved option value for scripts and exit",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = AutoconfConfig.load(args.config)
        if not args.print_option:
            config.require_valid()
    except AutoconfConfigError as exc:
        print(f"autoconf configuration error: {exc}", file=sys.stderr)
        return 2

    if args.print_option:
        print(config.get_option(args.print_option))
        return 0

    print(config.summary())
    if args.check:
        print("autoconf configuration is valid")
        return 0

    try:
        run_pipeline(config)
    except AutoconfPipelineError as exc:
        print(f"autoconf generation error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
