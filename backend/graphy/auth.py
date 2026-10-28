"""Authentication (OIDC bearer tokens) and role checks (TRD section 9)."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from graphy.config import Settings, get_settings


class Role(StrEnum):
    ANALYST = "analyst"
    STEWARD = "steward"
    DETECTION_ANALYST = "detection_analyst"
    COMPLIANCE = "compliance"
    ADMIN = "admin"
    READ_ONLY = "read_only"


@dataclass(frozen=True)
class User:
    subject: str
    roles: frozenset[Role]


_bearer = HTTPBearer(auto_error=False)


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url)


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> User:
    if settings.auth_mode == "dev":
        return User(settings.dev_user, frozenset(Role(r) for r in settings.dev_roles))

    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    if not settings.oidc_jwks_url:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "OIDC is not configured")
    try:
        key = _jwks_client(settings.oidc_jwks_url).get_signing_key_from_jwt(creds.credentials)
        claims = jwt.decode(
            creds.credentials,
            key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from exc

    groups = claims.get(settings.oidc_roles_claim) or []
    roles = frozenset(
        Role(settings.oidc_role_map[g]) for g in groups if g in settings.oidc_role_map
    )
    return User(claims["sub"], roles)


def require_roles(*allowed: Role) -> Callable[..., User]:
    """Dependency that admits a user holding any of the given roles."""

    def dependency(user: User = Depends(current_user)) -> User:
        if not user.roles.intersection(allowed):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Requires one of: {', '.join(sorted(allowed))}",
            )
        return user

    return dependency


# Shorthands for the common role sets.
READERS = (
    Role.ANALYST,
    Role.STEWARD,
    Role.DETECTION_ANALYST,
    Role.COMPLIANCE,
    Role.ADMIN,
    Role.READ_ONLY,
)
can_read = require_roles(*READERS)
can_steward = require_roles(Role.STEWARD, Role.ADMIN)
can_detect = require_roles(Role.DETECTION_ANALYST, Role.ADMIN)
can_investigate = require_roles(Role.ANALYST, Role.STEWARD, Role.DETECTION_ANALYST)
can_audit = require_roles(Role.COMPLIANCE)
can_ingest = require_roles(Role.ADMIN)
