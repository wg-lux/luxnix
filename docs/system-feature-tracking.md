# System feature tracking

WG-Lux feature identity is the pair `(provider, feature_id)`. A checkout path,
virtual environment, Python installation directory, and Nix store path are
deployment details and never form the semantic identity.

## Ownership and lifecycle

`lx-data-models`, `endoreg-db`, and `lx-annotate` own their feature
specifications. Their derivations install assessment-free YAML below
`$out/share/<provider>/features`. A specification contains intent, owners,
invariants, requirements, acceptance criteria, and verification definitions.
It does not contain current work, requirement status, evidence, or assessment
history.

LuxNix owns deployment resolution and mutable state. The
`services.wg-lux-features` module generates
`/etc/wg-lux/features/providers.json` directly from configured derivations and
creates `/var/lib/wg-lux/features/{events,projections,assessments}`. Nix store
paths in the generated registry are provenance, not identities. Rebuilding a
package changes its deployed subject while `(provider, feature_id)` remains
stable.

Assessment events are append-only YAML. Each event records the semantic
feature and requirement identities, status, evidence, assessor, timestamp, and
available package output, derivation, revision, version, and deployment
identity. The atomic JSON projection contains only current requirement state
and current work. It can be rebuilt deterministically from the event ledger.

## Resolution and progressive disclosure

Deployed resolution is strictly:

`provider -> NixOS registry -> package feature root -> feature_id -> YAML specification`

Assessment resolution is strictly:

`provider + feature_id -> system projection`

There is no implicit checkout fallback. A development registry may declare a
provider with `kind: development`, but deployed resolver calls reject it. The
compact status API returns identity, criticality, high-level state,
invariants, requirement-state groups, current objective, and next actions.
Full specifications, individual requirements, evidence history, and deployed
subjects require separate calls.

## Migration and recovery

`migrate_combined_tracker` splits a legacy combined tracker into an immutable
specification and assessment/current-work events. It preserves requirement
IDs, statuses, evidence, notes, assessors, timestamps, source documents, and
available deployment provenance. Keep the legacy file until the generated
specification and rebuilt projection have been reviewed.

To recover current state, retain the `events` tree, create an
`AssessmentLedger` for `/var/lib/wg-lux/features`, and call
`rebuild_projection(provider, feature_id)`. Projection files are replaceable;
event history is authoritative. Back up the state root as persistent system
data and never copy it into a package output.

Deployment verification must inspect the generated provider descriptor and
confirm that `feature_root` is below the exact current `package_store_path`.
Then resolve a known semantic feature, append an assessment bearing that
subject, rebuild its projection, and verify that a replacement derivation
changes provenance without changing semantic identity.
