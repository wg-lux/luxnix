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
- Git operations are fixed read-only commands executed without a shell.
- Context files are packaged with the service and cannot be changed through MCP.
- Tools expose no database access, service control, arbitrary shell, or write operation.

## Provenance contract

Discovery results should identify the repository, relative path, current commit, and
line span whenever those values exist. Summaries are navigation aids; repository files
remain authoritative.
