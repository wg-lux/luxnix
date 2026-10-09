from __future__ import annotations

from typing import Any

import anyio
import jwt
from jwt import PyJWKClient
from mcp.server.auth.provider import AccessToken


class KeycloakTokenVerifier:
    """Validate Keycloak JWT access tokens without handling client secrets."""

    def __init__(
        self,
        *,
        issuer_url: str,
        client_id: str,
        algorithms: list[str],
        resource_url: str,
    ) -> None:
        self.issuer_url = issuer_url.rstrip("/")
        self.client_id = client_id
        self.algorithms = algorithms
        self.resource_url = resource_url
        self.jwks = PyJWKClient(
            f"{self.issuer_url}/protocol/openid-connect/certs",
            cache_jwk_set=True,
            lifespan=300,
        )

    @staticmethod
    def _string_list(value: object) -> list[str]:
        if isinstance(value, str):
            return value.split()
        if isinstance(value, list):
            return [item for item in value if isinstance(item, str)]
        return []

    def _scopes(self, claims: dict[str, Any]) -> list[str]:
        scopes = set(self._string_list(claims.get("scope")))

        realm_access = claims.get("realm_access")
        if isinstance(realm_access, dict):
            scopes.update(self._string_list(realm_access.get("roles")))

        resource_access = claims.get("resource_access")
        if isinstance(resource_access, dict):
            client_access = resource_access.get(self.client_id)
            if isinstance(client_access, dict):
                scopes.update(self._string_list(client_access.get("roles")))

        return sorted(scopes)

    def _has_expected_client(self, claims: dict[str, Any]) -> bool:
        if claims.get("azp") == self.client_id:
            return True
        audience = claims.get("aud")
        return self.client_id in self._string_list(audience)

    def _verify_sync(self, token: str) -> AccessToken | None:
        try:
            signing_key = self.jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=self.algorithms,
                issuer=self.issuer_url,
                options={"require": ["exp", "iat", "iss", "sub"], "verify_aud": False},
                leeway=30,
            )
        except (jwt.PyJWTError, ValueError):
            return None

        if not self._has_expected_client(claims):
            return None

        expires_at = claims.get("exp")
        return AccessToken(
            token=token,
            client_id=self.client_id,
            scopes=self._scopes(claims),
            expires_at=expires_at if isinstance(expires_at, int) else None,
            resource=self.resource_url,
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        return await anyio.to_thread.run_sync(self._verify_sync, token)  # type: ignore[attr-defined]
