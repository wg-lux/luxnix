# Architectural decisions

## ADR-0001: Read-only service boundary

Status: accepted

Summary: The MCP server exposes only bounded repository and packaged-context reads.

Invariants:

- No file, Git, database, package, service, or network mutation tools.
- No arbitrary command execution.
- Repository access is restricted to configured allowlisted roots.

## ADR-0002: Progressive disclosure

Status: accepted

Summary: Discovery tools return compact, provenance-rich matches before full content.

Invariants:

- Do not eagerly inject every context document into model calls.
- Keep raw text reads as a bounded escape hatch.
- Prefer identifiers, summaries, paths, commits, and line spans for navigation.

## ADR-0003: Persistent context separation

Status: accepted

Summary: Durable rules, architecture, decisions, current work, and references have
separate documents with distinct lifetimes.

Invariants:

- AGENT.md contains durable operating rules rather than project history.
- decisions.md records architectural decisions and invariants.
- current-work.md is a replaceable checkpoint for active work.
- references.md contains curated external references and adopted principles.

## ADR-0004: Keycloak OAuth authentication

Status: accepted

Summary: Deployed MCP connections require Keycloak-issued OAuth access tokens.

Invariants:

- Validate signature, issuer, lifetime, client or audience, and required scopes.
- Advertise OAuth protected-resource metadata at the MCP endpoint.
- Do not store confidential client secrets in this repository.

## ADR-0005: YAML feature trackers are authoritative

Status: accepted

Summary: MCP exposes the existing endoreg-db and lx-annotate feature trackers through
progressive disclosure without maintaining a parallel readiness state.

Invariants:

- Feature YAML remains authoritative for intent, readiness, requirements, and evidence.
- Default feature retrieval excludes detailed evidence and tracking history.
- Requirement and evidence retrieval are separate, bounded operations.
- MCP never changes assessments, locks, messages, or tracker files.
