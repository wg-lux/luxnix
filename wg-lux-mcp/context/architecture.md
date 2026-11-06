# WG-Lux MCP architecture

## Purpose

WG-Lux MCP is a read-only, OAuth-protected context service for explicitly allowlisted
WG-Lux repositories. It gives agents progressively richer project information without
injecting whole repositories or the entire project memory into every model call.

## Retrieval flow

1. List repositories and retrieve durable agent guidance.
2. Search project context or code for relevant concepts.
3. Inspect matching symbols, files, decisions, tests, or history.
4. Read an exact bounded file only when deeper evidence is necessary.

## Trust boundaries

- Keycloak authenticates callers; the MCP server validates signed access tokens.
- Repository paths are configured explicitly and resolved beneath allowlisted roots.
- A separate outbound path policy excludes sensitive paths even when committed;
  repository tools read only regular committed Git blobs, never local checkout content.
- Git operations are fixed read-only commands executed without a shell.
- Context files are packaged with the service and cannot be changed through MCP.
- Tools expose no database access, service control, arbitrary shell, or write operation.

## Provenance contract

Repository discovery captures one commit and reads its immutable regular blobs.
Results identify repository, relative path, commit, blob and line span where
applicable. Dirty checkout contents are never attributed to HEAD. Internal Git
enumeration is bounded independently of response budgets and fails explicitly on
overflow. File prefixes are read with byte bounds; search reports oversized-file
exclusions and rejects scans exceeding its total budget. Summaries are navigation
aids; the identified committed blobs remain authoritative.
