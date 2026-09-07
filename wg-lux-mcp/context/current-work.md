# Current work

Goal: deploy_wg_lux_mcp_context_service

## Invariants

- Every active machine resolves wg-lux-mcp.local to its local service.
- MCP and lx-annotate-local use HTTPS through lxSsl.
- Keycloak OAuth protects MCP connections.
- Repository and context access remains read-only and provenance-rich.

## Completed

- Implemented the initial repository inspection tools.
- Enabled local DNS, HTTPS termination, and deployment on active machines.
- Implemented Keycloak JWT validation and OAuth resource metadata.
- Added persistent context documents and progressive-disclosure tools.
- Integrated read-only progressive disclosure for endoreg-db and lx-annotate feature YAML.

## Open

- Provision the wg-lux-mcp client in Keycloak with exact client redirect URIs.
- Rebuild target machines and verify authenticated MCP calls end to end.

## Evidence

- repo: luxnix
  path: wg-lux-mcp/tests/
  verification: automated unit and contract tests

## Next

- Register the Keycloak client after its exact redirect URIs are known.
- Run a NixOS rebuild and an authenticated connection test on a target machine.
