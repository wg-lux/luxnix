from __future__ import annotations

try:
    from mcp.server import MCPServer

    LEGACY_MCP = False
except ImportError:  # MCP 1.x, as packaged by NixOS 25.11
    from mcp.server.fastmcp import FastMCP as MCPServer  # type: ignore[assignment]

    LEGACY_MCP = True

from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl

from .auth import KeycloakTokenVerifier
from .config import settings
from .tools import context, features, repos, search

instructions = (
    "Read-only, progressively disclosed development context for explicitly allowlisted "
    "WG-Lux repositories. Start with guidance and discovery tools, then retrieve exact "
    "source only when needed. Never claim that this server can modify files, Git state, "
    "services, or databases."
)

if settings.oauth_enabled:
    mcp = MCPServer(
        "wg-lux-dev",
        instructions=instructions,
        token_verifier=KeycloakTokenVerifier(
            issuer_url=settings.oauth_issuer_url,
            client_id=settings.oauth_client_id,
            algorithms=settings.oauth_jwt_algorithms,
            resource_url=settings.oauth_resource_url,
        ),
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(settings.oauth_issuer_url),
            resource_server_url=AnyHttpUrl(settings.oauth_resource_url),
            required_scopes=settings.oauth_required_scopes,
        ),
    )
else:
    mcp = MCPServer("wg-lux-dev", instructions=instructions)


@mcp.tool()
def list_repositories() -> list[str]:
    """List repository names exposed by this server."""
    return repos.list_repositories()


@mcp.tool()
def get_repo_status(repo: str) -> dict[str, object]:
    """Return branch, HEAD commit, and porcelain status for one allowlisted repository."""
    return repos.get_repo_status(repo)


@mcp.tool()
def get_recent_commits(repo: str, limit: int = 10) -> list[dict[str, str]]:
    """Return recent commits from an allowlisted repository, newest first."""
    return repos.get_recent_commits(repo, limit)


@mcp.tool()
def read_text_file(repo: str, relative_path: str, max_chars: int = 20_000) -> dict[str, object]:
    """Read a bounded UTF-8 file as a fallback after targeted discovery."""
    return repos.read_text_file(repo, relative_path, max_chars)


@mcp.tool()
def get_pyproject(repo: str) -> dict[str, object]:
    """Return pyproject.toml as text plus basic existence metadata."""
    return repos.get_pyproject(repo)


@mcp.tool()
def inspect_django_migrations(repo: str, app: str) -> list[str]:
    """List migration filenames for a Django app without importing or executing Django."""
    return repos.inspect_django_migrations(repo, app)


@mcp.tool()
def search_code(repo: str, query: str, max_results: int = 20) -> dict[str, object]:
    """Find compact, ranked code matches with commit and line provenance."""
    return search.search_code(repo, query, max_results)


@mcp.tool()
def find_symbol(repo: str, symbol: str, max_results: int = 20) -> dict[str, object]:
    """Locate Python definitions by simple or class-qualified symbol name."""
    return search.find_symbol(repo, symbol, max_results)


@mcp.tool()
def get_related_tests(repo: str, path: str, max_results: int = 20) -> dict[str, object]:
    """Find test files related to a source path, returning compact provenance."""
    return search.get_related_tests(repo, path, max_results)


@mcp.tool()
def get_agent_guidance() -> dict[str, object]:
    """Return concise durable instructions for working on WG-Lux projects."""
    return context.get_agent_guidance()


@mcp.tool()
def search_project_context(query: str, max_results: int = 10) -> dict[str, object]:
    """Find relevant architectural decisions and project notes."""
    return context.search_project_context(query, max_results)


@mcp.tool()
def get_current_work() -> dict[str, object]:
    """Return the current goal, completed work, blockers, evidence, and next steps."""
    return context.get_current_work()


@mcp.tool()
def get_decision(decision_id: str) -> dict[str, object]:
    """Retrieve one architectural decision in full."""
    return context.get_decision(decision_id)


@mcp.tool()
def list_references() -> list[dict[str, object]]:
    """Return curated external engineering references."""
    return context.list_references()


def _feature_resolver() -> features.FeatureResolver:
    return features.deployed_resolver(
        settings.feature_provider_registry,
        settings.feature_state_root,
    )


@mcp.tool()
def list_feature_providers() -> list[dict[str, object]]:
    """List semantic identities for feature providers in the deployed Nix registry."""
    return _feature_resolver().list_feature_providers()


@mcp.tool()
def list_features(provider: str) -> list[dict[str, object]]:
    """List compact semantic feature identities for one deployed provider."""
    return _feature_resolver().list_features(provider)


@mcp.tool()
def get_feature(provider: str, feature_id: str) -> dict[str, object]:
    """Return the immutable specification and current work without assessment history."""
    return _feature_resolver().get_feature(provider, feature_id)


@mcp.tool()
def get_feature_status(provider: str, feature_id: str) -> dict[str, object]:
    """Return the compact current readiness status for one tracked feature."""
    return _feature_resolver().get_feature_status(provider, feature_id)


@mcp.tool()
def get_current_feature_work(provider: str, feature_id: str) -> dict[str, object]:
    """Return mutable operational work from the system assessment projection."""
    return _feature_resolver().get_current_work(provider, feature_id)


@mcp.tool()
def get_feature_requirement(
    provider: str, feature_id: str, requirement_id: str
) -> dict[str, object]:
    """Retrieve one requirement definition and current assessment without evidence."""
    return _feature_resolver().get_requirement(provider, feature_id, requirement_id)


@mcp.tool()
def get_feature_evidence(
    provider: str,
    feature_id: str,
    requirement_id: str,
    offset: int = 0,
    limit: int = 20,
) -> dict[str, object]:
    """Retrieve a bounded page of assessment events carrying detailed evidence."""
    return _feature_resolver().get_feature_evidence(
        provider, feature_id, requirement_id, offset, limit
    )


@mcp.tool()
def get_deployed_feature_subject(provider: str, feature_id: str) -> dict[str, object]:
    """Return exact deployed Nix provenance for a semantic feature identity."""
    return _feature_resolver().get_deployed_feature_subject(provider, feature_id)


@mcp.tool()
def server_capabilities() -> dict[str, object]:
    """Describe the deliberate security boundary and retrieval strategy."""
    return {
        "mode": "read-only",
        "retrieval": "progressive-disclosure",
        "provenance": ["repository", "path", "commit", "lines"],
        "shell": False,
        "arbitrary_commands": False,
        "filesystem_scope": "allowlisted repositories, deployed feature roots, and packaged context",
        "feature_tracking": {
            "provider_registry": str(settings.feature_provider_registry),
            "state_root": str(settings.feature_state_root),
            "source_of_truth": "deployed Nix provider registry",
            "writes": False,
        },
        "authentication": "keycloak-oauth" if settings.oauth_enabled else "disabled",
        "oauth_issuer": settings.oauth_issuer_url if settings.oauth_enabled else None,
        "oauth_client_id": settings.oauth_client_id if settings.oauth_enabled else None,
        "oauth_required_scopes": settings.oauth_required_scopes if settings.oauth_enabled else [],
        "git_writes": False,
        "database_access": False,
        "service_control": False,
    }
