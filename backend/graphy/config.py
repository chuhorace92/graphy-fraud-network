from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Every field can be set with a GRAPHY_<NAME> environment variable."""

    model_config = SettingsConfigDict(env_prefix="GRAPHY_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "staging", "prod"] = "dev"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://graphy:graphy@localhost:5432/graphy"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "graphy-dev-password"  # noqa: S105 - dev default, rejected in prod
    neo4j_database: str = "neo4j"

    # Keyed hash for secret attributes (SSN, bank account). Plain SHA-256 of a nine-digit SSN
    # is brute-forceable, so matching uses HMAC with this key. Rotating it requires a re-hash.
    hash_key: str = "dev-only-hash-key-change-me"

    auth_mode: Literal["dev", "oidc"] = "dev"
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    oidc_roles_claim: str = "groups"
    # IdP group name -> platform role, e.g. {"graphy-analysts": "analyst"}
    oidc_role_map: dict[str, str] = {}
    dev_user: str = "dev@localhost"
    dev_roles: list[str] = ["analyst", "steward", "detection_analyst", "compliance", "admin"]

    # Agent mode drafts a case's closing report with Claude. Without a key it is switched off.
    anthropic_api_key: str | None = None
    agent_model: str = "claude-opus-5-5"

    graph_max_nodes: int = 500
    graph_max_hops: int = 3
    graph_query_timeout_s: float = 10.0
    cors_origins: list[str] = ["http://localhost:5173"]

    @model_validator(mode="after")
    def _guard_production(self) -> "Settings":
        if self.env in ("staging", "prod"):
            if self.auth_mode != "oidc":
                raise ValueError("GRAPHY_AUTH_MODE must be 'oidc' outside dev/test")
            if self.hash_key.startswith("dev-only"):
                raise ValueError("GRAPHY_HASH_KEY must be set outside dev/test")
            if self.neo4j_password == "graphy-dev-password":  # noqa: S105
                raise ValueError("Dev passwords must be replaced outside dev/test")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
