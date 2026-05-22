"""
Tests for the monkey-patches installed in :func:`VerIDOIDCApp.ready`.

The patches mutate ``mozilla_django_oidc.auth.OIDCAuthenticationBackend`` so
the same effect applies regardless of which Open Forms config the request
uses. We assert behaviour at that mutated callable directly.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from mozilla_django_oidc import auth as _mdo_auth

from openforms.authentication.contrib.verid_oidc.constants import (
    OIDC_CLIENT_IDENTIFIER,
    SESSION_FORM_CLIENT_ID_KEY,
    SESSION_FORM_CLIENT_SECRET_KEY,
)


def _verid_backend(*, session: dict | None = None) -> SimpleNamespace:
    """`self` stand-in for a Ver.iD-tagged OIDC backend with a session."""
    request = SimpleNamespace(session=session if session is not None else {})
    return SimpleNamespace(
        config=SimpleNamespace(identifier=OIDC_CLIENT_IDENTIFIER),
        request=request,
    )


def _non_verid_backend() -> SimpleNamespace:
    return SimpleNamespace(
        config=SimpleNamespace(identifier="oidc-digid"),
        request=SimpleNamespace(session={}),
    )


def _apply_patch(fake_original):
    """Reset the patch guard and re-apply our patches with a fake upstream."""
    from openforms.authentication.contrib.verid_oidc.apps import VerIDOIDCApp

    if hasattr(_mdo_auth, "_verid_token_patch_applied"):
        del _mdo_auth._verid_token_patch_applied
    return mock.patch.object(
        _mdo_auth.OIDCAuthenticationBackend, "get_token", fake_original
    ), VerIDOIDCApp


class GetTokenPatchTests(SimpleTestCase):
    def test_form_client_id_and_secret_injected_from_session(self):
        captured: dict = {}

        def fake_original(self, payload):
            captured.update(payload)
            return {"id_token": "X.Y.Z"}

        ctx, VerIDOIDCApp = _apply_patch(fake_original)
        with ctx:
            VerIDOIDCApp._patch_oidc_token_handling()
            backend = _verid_backend(
                session={
                    SESSION_FORM_CLIENT_ID_KEY: "form-flow-uuid",
                    SESSION_FORM_CLIENT_SECRET_KEY: "form-secret",
                }
            )
            _mdo_auth.OIDCAuthenticationBackend.get_token(
                backend,
                {
                    "client_id": "tenant-placeholder",
                    "client_secret": "tenant-placeholder-secret",
                    "code_verifier": "v",
                    "grant_type": "authorization_code",
                    "code": "abc",
                },
            )

        self.assertEqual(captured["client_id"], "form-flow-uuid")
        self.assertEqual(captured["client_secret"], "form-secret")

    def test_pkce_with_no_form_secret_drops_secret(self):
        captured: dict = {}

        def fake_original(self, payload):
            captured.update(payload)
            return {"id_token": "X.Y.Z"}

        ctx, VerIDOIDCApp = _apply_patch(fake_original)
        with ctx:
            VerIDOIDCApp._patch_oidc_token_handling()
            backend = _verid_backend(
                session={SESSION_FORM_CLIENT_ID_KEY: "form-flow-uuid"}
            )
            _mdo_auth.OIDCAuthenticationBackend.get_token(
                backend,
                {
                    "client_id": "tenant-placeholder",
                    "client_secret": "tenant-placeholder-secret",
                    "code_verifier": "v",
                    "grant_type": "authorization_code",
                },
            )

        self.assertEqual(captured["client_id"], "form-flow-uuid")
        self.assertNotIn("client_secret", captured)

    def test_access_token_copied_to_id_token_for_verid_client(self):
        def fake_original(self, payload):
            return {"access_token": "ACC.TO.KEN"}

        ctx, VerIDOIDCApp = _apply_patch(fake_original)
        with ctx:
            VerIDOIDCApp._patch_oidc_token_handling()
            result = _mdo_auth.OIDCAuthenticationBackend.get_token(
                _verid_backend(), {"code_verifier": "v"}
            )

        self.assertEqual(result["id_token"], "ACC.TO.KEN")

    def test_non_verid_client_is_pass_through(self):
        """A non-Ver.iD identifier must NOT have its payload mutated."""
        captured: dict = {}

        def fake_original(self, payload):
            captured.update(payload)
            return {"id_token": "X.Y.Z"}

        ctx, VerIDOIDCApp = _apply_patch(fake_original)
        with ctx:
            VerIDOIDCApp._patch_oidc_token_handling()
            _mdo_auth.OIDCAuthenticationBackend.get_token(
                _non_verid_backend(),
                {
                    "client_id": "c",
                    "client_secret": "kept",
                    "code_verifier": "verifier",
                    "grant_type": "authorization_code",
                },
            )

        self.assertEqual(captured.get("client_secret"), "kept")


class VerifyTokenPatchTests(SimpleTestCase):
    """The Ver.iD-only verify_token patch (D1 gating)."""

    def test_non_verid_identifier_falls_through_to_upstream_verify(self):
        called: dict = {}

        def fake_original_verify(self, token, **kwargs):
            called["used"] = True
            return {"sub": "from-upstream"}

        if hasattr(_mdo_auth, "_verid_token_patch_applied"):
            del _mdo_auth._verid_token_patch_applied

        with mock.patch.object(
            _mdo_auth.OIDCAuthenticationBackend, "verify_token", fake_original_verify
        ):
            from openforms.authentication.contrib.verid_oidc.apps import VerIDOIDCApp

            VerIDOIDCApp._patch_oidc_token_handling()
            result = _mdo_auth.OIDCAuthenticationBackend.verify_token(
                _non_verid_backend(), "irrelevant.token.value"
            )

        self.assertEqual(called.get("used"), True)
        self.assertEqual(result, {"sub": "from-upstream"})
