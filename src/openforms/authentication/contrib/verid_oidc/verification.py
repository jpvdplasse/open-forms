"""
Ver.iD disclosure JWT verification.

Ver.iD's disclosure flow returns an ``access_token`` that is a JWS-signed JWT
with ``typ: ver-id/ssi/disclosure/v1+JWT``. The token's standard claims do not
match the OIDC conventions mozilla-django-oidc enforces:

- ``iss`` is a Ver.iD URN such as ``urn:ver-id:crypto:key@production:oauth/v1``,
  not the OIDC Provider's issuer URL.
- ``aud`` is ``urn:ver-id:crypto:key@external:*``, not the OIDC client_id.

This module provides a verifier that:

1. Verifies the signature against the OIDC Provider's JWKS (resolved by
   ``kid`` from the JWS header), so tokens cannot be tampered with.
2. Optionally validates the ``iss`` and ``aud`` claims against configured
   expected values (sourced from the ``OIDCClient.options`` or Django
   settings). This is opt-in via the per-OIDCClient options so the demo can
   start without pinning, but production should always pin.
3. Does NOT use mozilla-django-oidc's strict ``iss``/``aud`` checks because
   they assume OIDC-spec values.
"""

from __future__ import annotations

import time
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import SuspiciousOperation
from josepy.jws import Header, JWS
from mozilla_django_oidc_db.jwt import verify_and_decode_token


class VerIDNonToken(Exception):
    """Raised when the input does not look like a Ver.iD disclosure JWT,
    signalling that the upstream OIDC verifier should handle it instead."""


def _jwks_cache_key(jwks_uri: str) -> str:
    return f"verid_oidc:jwks:{jwks_uri}"


def _fetch_jwks(jwks_uri: str, *, force_refresh: bool = False) -> dict[str, Any]:
    if not force_refresh:
        cached = cache.get(_jwks_cache_key(jwks_uri))
        if cached:
            return cached
    response = requests.get(
        jwks_uri,
        verify=getattr(settings, "OIDC_VERIFY_SSL", True),
        timeout=getattr(settings, "OIDC_TIMEOUT", 10),
    )
    response.raise_for_status()
    jwks = response.json()
    # short-ish cache to balance rotation-readiness with overhead
    cache.set(_jwks_cache_key(jwks_uri), jwks, timeout=300)
    return jwks


def _find_jwk(jwks: dict[str, Any], kid: str | None, alg: str | None) -> dict | None:
    for jwk in jwks.get("keys", []):
        if kid and jwk.get("kid") and jwk["kid"] != kid:
            continue
        if alg and jwk.get("alg") and jwk["alg"] != alg:
            continue
        return jwk
    return None


def verify_verid_token(token: str, *, config) -> dict[str, Any]:
    """Verify a Ver.iD disclosure JWT and return its decoded claims.

    Raises:
        VerIDNonToken: token shape suggests it isn't a Ver.iD disclosure JWT.
        SuspiciousOperation: signature, iss, aud, or exp validation failed.
    """
    if not token or token.count(".") != 2:
        raise VerIDNonToken("token does not look like a compact JWS")

    try:
        jws = JWS.from_compact(token.encode() if isinstance(token, str) else token)
    except Exception as exc:
        raise VerIDNonToken("could not parse compact JWS") from exc

    header = Header.json_loads(jws.signature.protected)
    if header.alg is None:
        raise SuspiciousOperation("Ver.iD token missing alg header")
    if header.alg.name == "none":
        raise SuspiciousOperation("Ver.iD token uses 'none' alg")

    # Resolve JWKS endpoint from the OIDCClient's provider config.
    provider = getattr(config, "oidc_provider", None)
    jwks_uri = getattr(provider, "oidc_op_jwks_endpoint", None) if provider else None
    if not jwks_uri:
        raise SuspiciousOperation(
            "OIDCClient is missing oidc_op_jwks_endpoint — cannot verify Ver.iD token"
        )

    kid = str(header.kid) if header.kid else None
    alg = header.alg.name

    jwks = _fetch_jwks(jwks_uri)
    matching_jwk = _find_jwk(jwks, kid=kid, alg=alg)
    # If the cached JWKS has no matching kid, the IdP may have rotated keys
    # since we last fetched. Bypass the cache once and try again before
    # giving up — this prevents a 5-minute stale-cache outage when Ver.iD
    # rotates signing keys.
    if matching_jwk is None and kid:
        jwks = _fetch_jwks(jwks_uri, force_refresh=True)
        matching_jwk = _find_jwk(jwks, kid=kid, alg=alg)
    if matching_jwk is None:
        raise SuspiciousOperation(
            "no JWK matching kid/alg found in Ver.iD JWKS"
        )

    # Signature + payload extraction via the same helper mozilla-django-oidc-db
    # uses for userinfo JWTs.
    claims = verify_and_decode_token(
        token.encode() if isinstance(token, str) else token, matching_jwk
    )

    _validate_temporal_claims(claims)
    _validate_iss_aud(claims, config)

    return claims


def _validate_temporal_claims(claims: dict[str, Any]) -> None:
    now = int(time.time())
    leeway = int(getattr(settings, "OIDC_VERID_CLOCK_SKEW_SECONDS", 60))
    exp = claims.get("exp")
    if isinstance(exp, (int, float)) and now > exp + leeway:
        raise SuspiciousOperation("Ver.iD token is expired")
    nbf = claims.get("nbf")
    if isinstance(nbf, (int, float)) and now + leeway < nbf:
        raise SuspiciousOperation("Ver.iD token is not yet valid")


def _validate_iss_aud(claims: dict[str, Any], config) -> None:
    """
    Verify ``iss`` and ``aud`` against pinned expectations.

    Pinning is REQUIRED by default. Set
    ``OIDC_VERID_REQUIRE_ISS_AUD_PINNING = False`` in Django settings to opt
    out (only intended for local demos that haven't yet been configured
    with their tenant's real URN values).
    """
    options = getattr(config, "options", {}) or {}
    verid_settings = options.get("verid_settings") or {}

    expected_iss = verid_settings.get("expected_iss") or getattr(
        settings, "OIDC_VERID_EXPECTED_ISS", None
    )
    expected_aud = verid_settings.get("expected_aud") or getattr(
        settings, "OIDC_VERID_EXPECTED_AUD", None
    )

    require_pinning = getattr(settings, "OIDC_VERID_REQUIRE_ISS_AUD_PINNING", True)
    if require_pinning:
        if not expected_iss:
            raise SuspiciousOperation(
                "Ver.iD token verification requires a pinned `expected_iss` — "
                "set it on the OIDCClient options.verid_settings or via the "
                "OIDC_VERID_EXPECTED_ISS Django setting. To opt out (demo "
                "only), set OIDC_VERID_REQUIRE_ISS_AUD_PINNING = False."
            )
        if not expected_aud:
            raise SuspiciousOperation(
                "Ver.iD token verification requires a pinned `expected_aud` — "
                "set it on the OIDCClient options.verid_settings or via the "
                "OIDC_VERID_EXPECTED_AUD Django setting."
            )

    if expected_iss:
        actual_iss = claims.get("iss")
        if actual_iss != expected_iss:
            raise SuspiciousOperation(
                f"Ver.iD token iss '{actual_iss}' does not match expected '{expected_iss}'"
            )

    if expected_aud:
        actual_aud = claims.get("aud") or []
        if isinstance(actual_aud, str):
            actual_aud = [actual_aud]
        if isinstance(expected_aud, str):
            expected_aud = [expected_aud]
        matched = any(_aud_matches(a, e) for a in actual_aud for e in expected_aud)
        if not matched:
            raise SuspiciousOperation(
                f"Ver.iD token aud {actual_aud!r} does not match expected {expected_aud!r}"
            )


def _aud_matches(actual: str, expected: str) -> bool:
    """Equality with optional trailing ``*`` wildcard support in *expected*.

    Mirrors Ver.iD's own ``urn:...:external:*`` convention, but only in one
    direction — a wildcard in ``actual`` (which would be attacker-controlled
    if the token were forged) is never honoured.
    """
    if actual == expected:
        return True
    if expected.endswith("*"):
        return actual.startswith(expected[:-1])
    return False
