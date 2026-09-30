from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WG_LUX_MCP_",
        env_file=".env",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8765
    public_host: str = "mcp.example.org"
    bearer_token: str | None = None
    command_timeout_s: float = 8.0
    max_output_chars: int = 40_000
    oauth_enabled: bool = True
    oauth_issuer_url: str = "https://keycloak.endo-reg.net/realms/master"
    oauth_client_id: str = "wg-lux-mcp"
    oauth_required_scopes: list[str] = ["openid"]
    oauth_jwt_algorithms: list[str] = ["RS256"]

    repo_lx_annotate: Path = Field(default=Path("/srv/wg-lux/lx-annotate"))
    repo_endoreg_db: Path = Field(default=Path("/srv/wg-lux/endoreg-db"))
    repo_lx_data_models: Path = Field(default=Path("/srv/wg-lux/lx-data-models"))
    feature_provider_registry: Path = Field(
        default=Path("/etc/wg-lux/features/providers.json")
    )
    feature_state_root: Path = Field(default=Path("/var/lib/wg-lux/features"))

    @field_validator("public_host")
    @classmethod
    def validate_public_host(cls, value: str) -> str:
        value = value.strip().lower()
        if not value or "/" in value or "://" in value:
            raise ValueError("public_host must be a hostname, e.g. mcp.example.org")
        return value

    @field_validator("oauth_issuer_url")
    @classmethod
    def validate_oauth_issuer_url(cls, value: str) -> str:
        value = value.rstrip("/")
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("oauth_issuer_url must be an HTTPS issuer URL")
        return value

    @field_validator("oauth_client_id")
    @classmethod
    def validate_oauth_client_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("oauth_client_id must not be empty")
        return value

    @property
    def oauth_resource_url(self) -> str:
        return f"https://{self.public_host}/mcp"

    @property
    def repositories(self) -> dict[str, Path]:
        return {
            "lx-annotate": self.repo_lx_annotate,
            "endoreg-db": self.repo_endoreg_db,
            "lx-data-models": self.repo_lx_data_models,
        }


settings = Settings()
