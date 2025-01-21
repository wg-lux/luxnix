from pathlib import Path
import yaml


def format_yaml(file: Path):
    from ruamel.yaml import YAML

    yaml_parser = YAML(typ="rt")
    yaml_parser.preserve_quotes = True
    with open(file, "r") as fr:
        data = yaml_parser.load(fr)

    yaml_parser.indent(mapping=2, sequence=4, offset=2)
    with open(file, "w") as fw:
        yaml_parser.dump(data, fw)


def ansible_lint_and_format(file: Path):
    import subprocess

    subprocess.run(["ansible-lint", file])


def ansible_lint(file: Path):
    import subprocess

    subprocess.run(["ansible-lint", file])


def dump_yaml(data, file: Path, format_func=format_yaml, lint_func=None):
    with open(file, "w") as f:
        yaml.dump(data, f, indent=2)

    if format_func:
        format_func(file)

    if lint_func:
        lint_func(file)
