"""Azure identity, Key Vault and telemetry integration, lazy-loaded for local use."""

import os
from functools import lru_cache

from fastapi import HTTPException


@lru_cache(maxsize=1)
def credential():
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential(managed_identity_client_id=os.getenv("AZURE_CLIENT_ID"))


def secret(name):
    from azure.keyvault.secrets import SecretClient

    vault = os.environ["AZURE_KEY_VAULT_URL"]
    return SecretClient(vault_url=vault, credential=credential()).get_secret(name).value


@lru_cache(maxsize=1)
def jwks():
    import jwt

    tenant = os.environ["AZURE_TENANT_ID"]
    import uuid

    uuid.UUID(tenant)
    return jwt.PyJWKClient(
        f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys",
        cache_keys=True,
        lifespan=300,
    )


def verify_entra(authorization, required_role):
    import jwt

    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Entra bearer token required")
    token = authorization[7:]
    try:
        key = jwks().get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=os.environ["AZURE_API_AUDIENCE"],
            issuer=f"https://login.microsoftonline.com/{os.environ['AZURE_TENANT_ID']}/v2.0",
            options={"require": ["exp", "iat", "iss", "aud", "oid", "tid"]},
        )
        if claims["tid"] != os.environ["AZURE_TENANT_ID"]:
            raise ValueError("Tenant mismatch")
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(401, "Invalid Entra token") from None
    roles = set(claims.get("roles", []))
    accepted = (
        {"Maritime.Operator"}
        if required_role == "operator"
        else {"Maritime.Reader", "Maritime.Operator"}
    )
    if not roles & accepted:
        raise HTTPException(403, "Required Entra application role missing")
    return claims


def configure_telemetry():
    if os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(
            connection_string=os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"]
        )
