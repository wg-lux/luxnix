from pathlib import Path
import yaml
from ruamel.yaml import YAML


def remove_trailing_spaces(content: str) -> str:
    """Remove trailing spaces from each line in the content."""
    return "\n".join(line.rstrip() for line in content.splitlines())


def format_yaml(file: Path):
    """Format YAML file while preserving quotes and removing trailing spaces."""
    yaml_parser = YAML(typ="rt")
    yaml_parser.preserve_quotes = True

    with open(file, "r") as fr:
        data = yaml_parser.load(fr)

    yaml_parser.indent(mapping=2, sequence=4, offset=2)

    # First write to string to apply formatting
    from io import StringIO

    string_stream = StringIO()
    yaml_parser.dump(data, string_stream)
    formatted_content = remove_trailing_spaces(string_stream.getvalue())

    # Check if our content ends with newline, if not add it
    if not formatted_content.endswith("\n"):
        formatted_content += "\n"

    # Then write the cleaned content to file
    with open(file, "w") as fw:
        fw.write(formatted_content)


def ansible_lint_and_format(file: Path):
    import subprocess

    subprocess.run(["ansible-lint", file])


def ansible_lint(file: Path):
    import subprocess

    subprocess.run(["ansible-lint", file])


def dump_yaml(data, file: Path, format_func=format_yaml, lint_func=None):
    """Dump data to YAML file without trailing spaces."""
    with open(file, "w") as f:
        yaml.safe_dump(
            data,
            f,
            indent=2,
            default_flow_style=False,
            width=float("inf"),  # Prevent line wrapping
        )

    if format_func:
        format_func(file)

    if lint_func:
        lint_func(file)
