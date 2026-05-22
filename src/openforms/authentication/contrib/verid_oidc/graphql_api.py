"""
Optional Ver.iD GraphQL admin-API client for disclosure flow discovery.

Used by the form-builder UI to populate dropdowns:

- which disclosure flows exist on the org (UUID = OAuth client_id)
- which claims (mapping field names) a given flow returns

Both pieces live in Ver.iD Studio; without GraphQL access form authors have
to type UUIDs and claim names by hand. This module is entirely optional —
when no GraphQL credentials are configured, the form-builder falls back to
free-text inputs.

GraphQL config lives on the tenant ``OIDCClient.options.verid_settings``:

    {
      "verid_settings": {
        "graphql_client_id": "...",
        "graphql_client_secret": "...",
        "graphql_token_endpoint": "https://api.oauth.ver.id/token/grant",
        "graphql_endpoint": "https://graphql.ver.id"
      }
    }

The endpoints default to the production Ver.iD URLs.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests
import structlog
from django.core.cache import cache

logger = structlog.stdlib.get_logger(__name__)

DEFAULT_TOKEN_ENDPOINT = "https://api.oauth.ver.id/token/grant"
DEFAULT_GRAPHQL_ENDPOINT = "https://graphql.ver.id"

# Cache the GraphQL access token a little under its 24h lifetime to give a
# refresh window before expiry.
TOKEN_CACHE_TTL_SECONDS = 20 * 60 * 60
DISCLOSURES_CACHE_TTL_SECONDS = 5 * 60
CLAIMS_CACHE_TTL_SECONDS = 5 * 60


class GraphQLNotConfigured(Exception):
    """Raised when the GraphQL discovery feature is not configured."""


class GraphQLError(Exception):
    """Raised when the Ver.iD GraphQL API returns an error response."""


@dataclass(frozen=True)
class GraphQLConfig:
    client_id: str
    client_secret: str
    token_endpoint: str = DEFAULT_TOKEN_ENDPOINT
    graphql_endpoint: str = DEFAULT_GRAPHQL_ENDPOINT


def load_config_from_oidc_client(oidc_client) -> GraphQLConfig | None:
    """Build a GraphQLConfig from the tenant OIDCClient row, if configured.

    Returns ``None`` when GraphQL credentials are not set.
    """
    options = (getattr(oidc_client, "options", None) or {}).get("verid_settings") or {}
    cid = options.get("graphql_client_id") or ""
    csec = options.get("graphql_client_secret") or ""
    if not cid or not csec:
        return None
    return GraphQLConfig(
        client_id=cid,
        client_secret=csec,
        token_endpoint=options.get("graphql_token_endpoint") or DEFAULT_TOKEN_ENDPOINT,
        graphql_endpoint=options.get("graphql_endpoint") or DEFAULT_GRAPHQL_ENDPOINT,
    )


def _token_cache_key(config: GraphQLConfig) -> str:
    return f"verid_oidc:gql_token:{config.client_id}@{config.token_endpoint}"


def _get_access_token(config: GraphQLConfig) -> str:
    cached = cache.get(_token_cache_key(config))
    if cached:
        return cached
    resp = requests.post(
        config.token_endpoint,
        data={
            "grant_type": "client_credentials",
            "client_id": config.client_id,
            "client_secret": config.client_secret,
        },
        timeout=10,
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    cache.set(_token_cache_key(config), token, timeout=TOKEN_CACHE_TTL_SECONDS)
    return token


def _gql_request(config: GraphQLConfig, query: str, variables: dict | None = None) -> dict:
    token = _get_access_token(config)
    resp = requests.post(
        config.graphql_endpoint,
        json={"query": query, "variables": variables or {}},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=10,
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("errors"):
        raise GraphQLError(str(body["errors"]))
    return body["data"]


# --- Public helpers ---------------------------------------------------------


_DISCLOSURES_QUERY = """
{
  findManyDisclosures(input: { pagination: { first: 100 } }) {
    edges {
      node {
        uuid
        name
        state
        disclosureMappings {
          edges { node { mappingVerification { uuid name } } }
        }
      }
    }
  }
}
"""


def list_disclosures(config: GraphQLConfig) -> list[dict[str, Any]]:
    """Return the org's disclosure flows.

    Each entry has ``uuid`` (the OAuth client_id), ``name``, ``state``, and
    ``mapping_verification_uuid`` (used to look up the flow's claim names).
    Result is cached for a short window.
    """
    cache_key = (
        f"verid_oidc:gql_disclosures:{config.client_id}@{config.graphql_endpoint}"
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    data = _gql_request(config, _DISCLOSURES_QUERY)
    edges = data["findManyDisclosures"]["edges"]
    result: list[dict[str, Any]] = []
    for edge in edges:
        node = edge["node"]
        mapping_edges = (node.get("disclosureMappings") or {}).get("edges") or []
        mapping_uuid = None
        if mapping_edges:
            mv = (mapping_edges[0].get("node") or {}).get("mappingVerification") or {}
            mapping_uuid = mv.get("uuid")
        result.append(
            {
                "uuid": node["uuid"],
                "name": node["name"],
                "state": node.get("state"),
                "mapping_verification_uuid": mapping_uuid,
            }
        )
    cache.set(cache_key, result, timeout=DISCLOSURES_CACHE_TTL_SECONDS)
    return result


_CLAIMS_QUERY = """
query ($uuid: UUID!) {
  findMappingVerification(uuid: $uuid) {
    name
    mappingVerificationClaims {
      edges { node { uuid name claim } }
    }
  }
}
"""


def get_disclosure_claims(
    config: GraphQLConfig, mapping_verification_uuid: str
) -> list[dict[str, str]]:
    """Return the claim names a given disclosure flow's mapping returns.

    Each entry has ``name`` (admin-facing label) and ``claim`` (the JSON key
    the token will carry). Result is cached for a short window.
    """
    cache_key = (
        "verid_oidc:gql_claims:"
        f"{mapping_verification_uuid}@{config.graphql_endpoint}"
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    data = _gql_request(
        config, _CLAIMS_QUERY, variables={"uuid": mapping_verification_uuid}
    )
    mv = data.get("findMappingVerification") or {}
    edges = (mv.get("mappingVerificationClaims") or {}).get("edges") or []
    result = [
        {"name": e["node"]["name"], "claim": e["node"]["claim"]}
        for e in edges
        if e.get("node")
    ]
    cache.set(cache_key, result, timeout=CLAIMS_CACHE_TTL_SECONDS)
    return result


def invalidate_caches(config: GraphQLConfig | None = None) -> None:
    """Drop all cached tokens/disclosures/claims. Useful from a management
    command or after rotating credentials."""
    cache.delete_pattern("verid_oidc:gql_*") if hasattr(cache, "delete_pattern") else None
    _ = config  # reserved for future per-config invalidation
