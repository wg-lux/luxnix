#!/usr/bin/env python3
"""Validate public cross-repository rotation contracts and display ordered gates.

This command does not open credential files, invoke processes or execute a plan.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from lx_administration.yaml import load_unique_yaml_file

Repository = Literal["luxnix", "endoreg_db", "lx_annotate"]
PHASES = ("inventory", "prepare", "activate", "verify", "retire")


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class Family(Contract):
    owner: str = Field(min_length=1)
    routine: bool
    contracts: dict[Repository, list[str]] = Field(min_length=1)
    inventory: str = Field(min_length=1)
    prepare: str = Field(min_length=1)
    activate: str = Field(min_length=1)
    verify: str = Field(min_length=1)
    retire: str = Field(min_length=1)
    incident: str = Field(min_length=1)


class Catalog(Contract):
    schema_version: int = Field(ge=1, le=1)
    readiness: str
    runbook: str
    repositories: dict[Repository, str]
    phases: list[str]
    families: dict[str, Family] = Field(min_length=1)

    @field_validator("phases")
    @classmethod
    def ordered_gates(cls, value: list[str]) -> list[str]:
        if tuple(value) != PHASES:
            raise ValueError("rotation must preserve all ordered gates")
        return value

    @field_validator("repositories")
    @classmethod
    def all_repositories(cls, value: dict[Repository, str]) -> dict[Repository, str]:
        if set(value) != {"luxnix", "endoreg_db", "lx_annotate"}:
            raise ValueError("all three repository contracts are required")
        return value


def require_source(root: Path, relative: str) -> None:
    path = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("contract must be a repository-relative source path")
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"missing or external source contract: {relative}")


def check_catalog(path: Path, roots: dict[Repository, Path]) -> Catalog:
    catalog = Catalog.model_validate(load_unique_yaml_file(path))
    for repository, manifest in catalog.repositories.items():
        require_source(roots[repository], manifest)
    require_source(roots["luxnix"], catalog.readiness)
    require_source(roots["luxnix"], catalog.runbook)
    for family in catalog.families.values():
        for repository, references in family.contracts.items():
            if not references:
                raise ValueError("repository contract cannot be empty")
            for reference in references:
                require_source(roots[repository], reference)
    return catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endoreg-db", type=Path, required=True)
    parser.add_argument("--lx-annotate", type=Path, required=True)
    parser.add_argument(
        "--family", help="Display gates for one family; never execute them"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        catalog = check_catalog(
            root / "secrets-management.yml",
            {
                "luxnix": root,
                "endoreg_db": args.endoreg_db,
                "lx_annotate": args.lx_annotate,
            },
        )
        if args.family:
            if args.family not in catalog.families:
                parser.error("unknown secret family")
            family = catalog.families[args.family]
            print(f"{args.family}: {family.owner}; routine={family.routine}")
            for phase in catalog.phases:
                print(f"{phase}: {getattr(family, phase)}")
            print(f"incident: {family.incident}")
    except (OSError, ValueError, ValidationError, yaml.YAMLError):
        print(
            "Secret rotation catalog invalid or source contracts missing; "
            "no operations performed."
        )
        return 2
    print(
        f"Validated {len(catalog.families)} secret families across three repositories;"
        " no runtime acceptance implied."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
