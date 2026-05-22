"""
Tests for Ver.iD disclosure-JWT verification.

Verification is the security-critical piece of the integration: a tampered
token must fail; iss/aud pinning must be enforced; expired tokens must be
rejected; tokens that are not Ver.iD disclosure JWTs must fall through to
the upstream OIDC verifier (via the VerIDNonToken sentinel).
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from unittest import mock

from django.core.cache import cache
from django.core.exceptions import SuspiciousOperation
from django.test import SimpleTestCase, override_settings

from cryptography.hazmat.primitives.asymmetric import ec
from josepy.jwa import ES384
from josepy.jwk import JWKEC
from josepy.jws import JWS

from openforms.authentication.contrib.verid_oidc.verification import (
    VerIDNonToken,
    _aud_matches,
    verify_verid_token,
)


def _make_signed_token(claims: dict, *, kid: str = "key-1", alg=ES384) -> tuple[str, dict]:
    """Sign a JWT with a fresh ES384 key and return (token, public_jwk)."""
    private_key = ec.generate_private_key(ec.SECP384R1())
    jwk = JWKEC(key=private_key)
    payload = json.dumps(claims).encode()
    # alg/kid must live in the *protected* header for compact serialization.
    jws = JWS.sign(
        payload=payload,
        key=jwk,
        alg=alg,
        kid=kid,
        include_jwk=False,
        protect=frozenset({"alg", "kid"}),
    )
    token = jws.to_compact().decode()
    public_jwk_dict = jwk.public_key().to_json()
    if isinstance(public_jwk_dict, str):
        public_jwk_dict = json.loads(public_jwk_dict)
    public_jwk_dict = {**public_jwk_dict, "kid": kid, "alg": alg.name}
    return token, public_jwk_dict


def _config(
    *,
    jwks_uri: str = "https://example.test/jwks.json",
    iss: str = "urn:test-iss",
    aud: str = "urn:test-aud",
    **options,
) -> SimpleNamespace:
    """Build an OIDCClient stub with iss/aud pinning configured by default.

    Tests that want to assert the no-pinning failure mode build a config
    without these defaults (use ``_config_unpinned``).
    """
    merged = {
        "verid_settings": {"expected_iss": iss, "expected_aud": aud},
        **options,
    }
    return SimpleNamespace(
        oidc_provider=SimpleNamespace(oidc_op_jwks_endpoint=jwks_uri),
        options=merged,
    )


def _config_unpinned(*, jwks_uri: str = "https://example.test/jwks.json") -> SimpleNamespace:
    return SimpleNamespace(
        oidc_provider=SimpleNamespace(oidc_op_jwks_endpoint=jwks_uri),
        options={},
    )


class VerifyVerIDTokenTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_valid_token_returns_decoded_claims(self):
        claims = {
            "iss": "urn:ver-id:crypto:key@production:oauth/v1",
            "aud": ["urn:ver-id:crypto:key@external:abc"],
            "exp": int(time.time()) + 3600,
            "mapping": {"straat": {"value": "Valkenboskade"}},
        }
        token, jwk = _make_signed_token(claims)
        config = _config(
            iss="urn:ver-id:crypto:key@production:oauth/v1",
            aud="urn:ver-id:crypto:key@external:*",
        )

        with mock.patch(
            "openforms.authentication.contrib.verid_oidc.verification._fetch_jwks",
            return_value={"keys": [jwk]},
        ):
            result = verify_verid_token(token, config=config)

        self.assertEqual(result["mapping"]["straat"]["value"], "Valkenboskade")

    def test_tampered_token_is_rejected(self):
        claims = {
            "exp": int(time.time()) + 3600,
            "iss": "urn:test-iss",
            "aud": "urn:test-aud",
        }
        token, jwk = _make_signed_token(claims)
        # mutate the payload segment (middle of the JWS) → signature mismatch
        header, _payload, sig = token.split(".")
        tampered = f"{header}.eyJleHAiOjk5OTk5OTk5OTl9.{sig}"

        with mock.patch(
            "openforms.authentication.contrib.verid_oidc.verification._fetch_jwks",
            return_value={"keys": [jwk]},
        ):
            with self.assertRaises(SuspiciousOperation):
                verify_verid_token(tampered, config=_config())

    def test_jwks_refresh_on_unknown_kid(self):
        # First fetch returns an old JWKS missing the kid; second fetch
        # returns the rotated JWKS with it. verify_verid_token should retry
        # once instead of failing on the stale cache.
        token, fresh_jwk = _make_signed_token(
            {
                "exp": int(time.time()) + 3600,
                "iss": "urn:test-iss",
                "aud": "urn:test-aud",
            },
            kid="new-kid",
        )
        stale_jwk = {**fresh_jwk, "kid": "old-kid"}

        call_log: list[bool] = []

        def fake_fetch(jwks_uri, *, force_refresh=False):
            call_log.append(force_refresh)
            return {"keys": [fresh_jwk if force_refresh else stale_jwk]}

        with mock.patch(
            "openforms.authentication.contrib.verid_oidc.verification._fetch_jwks",
            side_effect=fake_fetch,
        ):
            result = verify_verid_token(token, config=_config())

        self.assertEqual(call_log, [False, True])
        self.assertEqual(result["iss"], "urn:test-iss")

    def test_no_matching_kid_in_jwks_is_rejected(self):
        token, jwk = _make_signed_token(
            {
                "exp": int(time.time()) + 3600,
                "iss": "urn:test-iss",
                "aud": "urn:test-aud",
            },
            kid="known-kid",
        )
        # JWKS only has a key with a different kid
        wrong_jwk = {**jwk, "kid": "different-kid"}

        with mock.patch(
            "openforms.authentication.contrib.verid_oidc.verification._fetch_jwks",
            return_value={"keys": [wrong_jwk]},
        ):
            with self.assertRaisesMessage(SuspiciousOperation, "no JWK matching"):
                verify_verid_token(token, config=_config())

    def test_expired_token_is_rejected(self):
        token, jwk = _make_signed_token(
            {
                "exp": int(time.time()) - 3600,
                "iss": "urn:test-iss",
                "aud": "urn:test-aud",
            }
        )

        with mock.patch(
            "openforms.authentication.contrib.verid_oidc.verification._fetch_jwks",
            return_value={"keys": [jwk]},
        ):
            with self.assertRaisesMessage(SuspiciousOperation, "expired"):
                verify_verid_token(token, config=_config())

    def test_iss_mismatch_is_rejected_when_pinned(self):
        claims = {
            "iss": "urn:attacker",
            "aud": "urn:test-aud",
            "exp": int(time.time()) + 3600,
        }
        token, jwk = _make_signed_token(claims)
        config = _config(iss="urn:ver-id:crypto:key@production:oauth/v1")

        with mock.patch(
            "openforms.authentication.contrib.verid_oidc.verification._fetch_jwks",
            return_value={"keys": [jwk]},
        ):
            with self.assertRaisesMessage(SuspiciousOperation, "iss"):
                verify_verid_token(token, config=config)

    def test_aud_wildcard_match_succeeds(self):
        claims = {
            "iss": "urn:test-iss",
            "aud": ["urn:ver-id:crypto:key@external:abc"],
            "exp": int(time.time()) + 3600,
        }
        token, jwk = _make_signed_token(claims)
        config = _config(aud="urn:ver-id:crypto:key@external:*")

        with mock.patch(
            "openforms.authentication.contrib.verid_oidc.verification._fetch_jwks",
            return_value={"keys": [jwk]},
        ):
            result = verify_verid_token(token, config=config)

        self.assertEqual(result["aud"], ["urn:ver-id:crypto:key@external:abc"])

    def test_non_token_raises_verid_non_token(self):
        with self.assertRaises(VerIDNonToken):
            verify_verid_token("not-a-jwt", config=_config())

    def test_missing_jwks_uri_is_rejected(self):
        token, _ = _make_signed_token(
            {
                "exp": int(time.time()) + 3600,
                "iss": "urn:test-iss",
                "aud": "urn:test-aud",
            }
        )
        config = SimpleNamespace(oidc_provider=None, options={})

        with self.assertRaisesMessage(SuspiciousOperation, "oidc_op_jwks_endpoint"):
            verify_verid_token(token, config=config)

    def test_strict_pinning_required_by_default(self):
        # No verid_settings configured AND no Django settings → must fail.
        claims = {"exp": int(time.time()) + 3600}
        token, jwk = _make_signed_token(claims)

        with mock.patch(
            "openforms.authentication.contrib.verid_oidc.verification._fetch_jwks",
            return_value={"keys": [jwk]},
        ):
            with self.assertRaisesMessage(SuspiciousOperation, "expected_iss"):
                verify_verid_token(token, config=_config_unpinned())

    @override_settings(OIDC_VERID_REQUIRE_ISS_AUD_PINNING=False)
    def test_strict_pinning_can_be_opted_out_for_demos(self):
        claims = {"exp": int(time.time()) + 3600}
        token, jwk = _make_signed_token(claims)

        with mock.patch(
            "openforms.authentication.contrib.verid_oidc.verification._fetch_jwks",
            return_value={"keys": [jwk]},
        ):
            # Should NOT raise — opt-out lets the token through.
            result = verify_verid_token(token, config=_config_unpinned())
        self.assertEqual(result["exp"], claims["exp"])


class AudMatchTests(SimpleTestCase):
    def test_exact_match(self):
        self.assertTrue(_aud_matches("client-1", "client-1"))

    def test_wildcard_in_expected(self):
        self.assertTrue(_aud_matches("client-1-foo", "client-1-*"))
        self.assertFalse(_aud_matches("client-2-foo", "client-1-*"))

    def test_wildcard_in_actual_is_not_honoured(self):
        # Wildcards in `actual` would be attacker-controlled if a token were
        # forged. Only `expected` is allowed to contain a wildcard.
        self.assertFalse(_aud_matches("urn:foo:*", "urn:foo:bar"))

    def test_unrelated_strings(self):
        self.assertFalse(_aud_matches("a", "b"))
