from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import anyio
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from wg_lux_mcp.auth import KeycloakTokenVerifier

ISSUER = "https://keycloak.example.test/realms/test"
RESOURCE = "https://wg-lux-mcp.local/mcp"
CLIENT_ID = "wg-lux-mcp"


def make_verifier() -> tuple[KeycloakTokenVerifier, Any]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = KeycloakTokenVerifier(
        issuer_url=ISSUER,
        client_id=CLIENT_ID,
        algorithms=["RS256"],
        resource_url=RESOURCE,
    )
    verifier.jwks = cast(
        Any,
        SimpleNamespace(
            get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private_key.public_key())
        ),
    )
    return verifier, private_key


def encode(private_key: Any, **overrides: object) -> str:
    import time

    claims: dict[str, object] = {
        "iss": ISSUER,
        "sub": "user-123",
        "azp": CLIENT_ID,
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "scope": "openid profile",
        "realm_access": {"roles": ["mcp:read"]},
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test"})


def test_accepts_valid_keycloak_token_and_collects_scopes() -> None:
    verifier, private_key = make_verifier()
    token = encode(private_key)

    access = anyio.run(verifier.verify_token, token)

    assert access is not None
    assert access.client_id == CLIENT_ID
    assert access.resource == RESOURCE
    assert access.scopes == ["mcp:read", "openid", "profile"]


def test_rejects_wrong_issuer_or_client() -> None:
    verifier, private_key = make_verifier()

    wrong_issuer = anyio.run(verifier.verify_token, encode(private_key, iss="https://evil.test"))
    wrong_client = anyio.run(verifier.verify_token, encode(private_key, azp="other-client"))

    assert wrong_issuer is None
    assert wrong_client is None
