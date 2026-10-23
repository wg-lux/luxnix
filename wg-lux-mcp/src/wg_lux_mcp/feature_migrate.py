"""Administrative CLI for deterministic legacy feature-state migration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from .tools.features import (
    DeployedSubject,
    FeatureResolver,
    migrate_combined_tracker,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Split one combined feature tracker into a specification and event ledger."
    )
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--specification-root", type=Path, required=True)
    parser.add_argument("--assessed-by", default="legacy-feature-migration")
    args = parser.parse_args()

    resolver = FeatureResolver(args.registry, args.state_root)
    descriptor = resolver.registry.providers.get(args.provider)
    if descriptor is None or descriptor.kind != "nix" or descriptor.package_store_path is None:
        parser.error(f"{args.provider!r} is not a deployed Nix provider")
    feature_value = args.source.stem
    source_data = args.source.read_text(encoding="utf-8")
    loaded = yaml.safe_load(source_data)
    if isinstance(loaded, dict) and isinstance(loaded.get("id"), str):
        feature_value = loaded["id"]
    subject = DeployedSubject(
        provider=args.provider,
        feature_id=feature_value,
        nix_store_path=descriptor.package_store_path,
        drv_path=descriptor.drv_path,
        revision=descriptor.revision,
        version=descriptor.version,
        system_generation=descriptor.system_generation,
    )
    specification, events = migrate_combined_tracker(
        provider=args.provider,
        source_path=args.source,
        specification_root=args.specification_root,
        ledger=resolver.ledger,
        subject=subject,
        default_assessor=args.assessed_by,
    )
    print(
        json.dumps(
            {
                "feature": {"provider": args.provider, "id": feature_value},
                "specification": str(specification),
                "events": [str(path) for path in events],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
