"""
Tests for the Open Forms Ver.iD authentication plugin.

These exercise ``VerIDOIDCAuthentication`` directly (no HTTP layer), focusing
on the small unit of logic we own: deciding which auth attribute came back,
shaping the ``FormAuth`` and ``VerIDContext`` payloads, and selecting the
per-form OIDC client identifier from the form options.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from openforms.authentication.constants import AuthAttribute
from openforms.authentication.contrib.verid_oidc.config import (
    VerIDOptions,
    VerIDOptionsSerializer,
)
from openforms.authentication.contrib.verid_oidc.plugin import (
    VerIDOIDCAuthentication,
)
from openforms.authentication.models import AuthInfo


class OptionsSerializerTests(SimpleTestCase):
    def test_client_id_is_required(self):
        s = VerIDOptionsSerializer(data={})
        self.assertFalse(s.is_valid())
        self.assertIn("client_id", s.errors)

    def test_client_secret_defaults_blank(self):
        s = VerIDOptionsSerializer(data={"client_id": "uuid-1"})
        self.assertTrue(s.is_valid(), s.errors)
        self.assertEqual(s.validated_data["client_id"], "uuid-1")
        self.assertEqual(s.validated_data.get("client_secret", ""), "")

    def test_explicit_client_secret_is_accepted(self):
        s = VerIDOptionsSerializer(
            data={"client_id": "uuid-1", "client_secret": "shh"}
        )
        self.assertTrue(s.is_valid(), s.errors)
        self.assertEqual(s.validated_data["client_secret"], "shh")


class GetAuthAttributeTests(SimpleTestCase):
    def test_bsn_wins(self):
        claims = {"bsn_claim": "123456782"}
        self.assertEqual(
            VerIDOIDCAuthentication._get_auth_attribute(claims), AuthAttribute.bsn
        )

    def test_kvk_when_no_bsn(self):
        claims = {"kvk_claim": "12345678"}
        self.assertEqual(
            VerIDOIDCAuthentication._get_auth_attribute(claims), AuthAttribute.kvk
        )

    def test_bsn_takes_precedence_over_kvk(self):
        claims = {"bsn_claim": "123", "kvk_claim": "456"}
        self.assertEqual(
            VerIDOIDCAuthentication._get_auth_attribute(claims), AuthAttribute.bsn
        )

    def test_pseudo_fallback(self):
        self.assertEqual(
            VerIDOIDCAuthentication._get_auth_attribute({}), AuthAttribute.pseudo
        )
        self.assertEqual(
            VerIDOIDCAuthentication._get_auth_attribute({"pseudo_claim": "abc"}),
            AuthAttribute.pseudo,
        )


class TransformClaimsTests(SimpleTestCase):
    def setUp(self):
        # The auth plugin reads `self.identifier` for FormAuth["plugin"].
        # Build a minimal stand-in so we don't need the full registry.
        self.plugin = VerIDOIDCAuthentication.__new__(VerIDOIDCAuthentication)
        self.plugin.identifier = "verid_oidc"

    def test_bsn_claim_produces_bsn_form_auth(self):
        form_auth = self.plugin.transform_claims(
            VerIDOptions(),
            {
                "bsn_claim": "111222333",
                "loa_claim": "loa3",
                "additional_claims": {"straat": "Valkenboskade"},
            },
        )
        self.assertEqual(form_auth["attribute"], AuthAttribute.bsn)
        self.assertEqual(form_auth["value"], "111222333")
        self.assertEqual(form_auth["loa"], "loa3")
        self.assertEqual(form_auth["additional_claims"], {"straat": "Valkenboskade"})

    def test_kvk_claim_produces_kvk_form_auth(self):
        form_auth = self.plugin.transform_claims(
            VerIDOptions(),
            {"kvk_claim": "12345678", "loa_claim": "loa2"},
        )
        self.assertEqual(form_auth["attribute"], AuthAttribute.kvk)
        self.assertEqual(form_auth["value"], "12345678")
        self.assertEqual(form_auth["additional_claims"], {})

    def test_missing_identity_uses_pseudo_with_fallback_value(self):
        form_auth = self.plugin.transform_claims(VerIDOptions(), {})
        self.assertEqual(form_auth["attribute"], AuthAttribute.pseudo)
        self.assertEqual(form_auth["value"], "dummy-set-by@openforms")
        self.assertEqual(form_auth["loa"], "unknown")


class AuthInfoToAuthContextTests(SimpleTestCase):
    def setUp(self):
        self.plugin = VerIDOIDCAuthentication.__new__(VerIDOIDCAuthentication)
        self.plugin.identifier = "verid_oidc"

    def _make_auth_info(self, **kwargs) -> AuthInfo:
        defaults = dict(
            plugin="verid_oidc",
            attribute=AuthAttribute.bsn,
            value="111222333",
            loa="loa3",
            additional_claims={"straat": "Valkenboskade"},
        )
        defaults.update(kwargs)
        return AuthInfo(**defaults)

    def test_bsn_context_shape(self):
        ctx = self.plugin.auth_info_to_auth_context(self._make_auth_info())
        self.assertEqual(ctx["source"], "verid")
        self.assertEqual(ctx["authorizee"]["legalSubject"]["identifierType"], "bsn")
        self.assertEqual(ctx["authorizee"]["legalSubject"]["identifier"], "111222333")
        self.assertEqual(
            ctx["authorizee"]["legalSubject"]["additionalInformation"],
            {"straat": "Valkenboskade"},
        )

    def test_kvk_context_shape(self):
        ctx = self.plugin.auth_info_to_auth_context(
            self._make_auth_info(attribute=AuthAttribute.kvk, value="12345678")
        )
        self.assertEqual(
            ctx["authorizee"]["legalSubject"]["identifierType"], "kvkNummer"
        )

    def test_pseudo_context_shape(self):
        ctx = self.plugin.auth_info_to_auth_context(
            self._make_auth_info(
                attribute=AuthAttribute.pseudo, value="pseudo-id", loa="unknown"
            )
        )
        self.assertEqual(
            ctx["authorizee"]["legalSubject"]["identifierType"], "opaque"
        )
        self.assertEqual(ctx["levelOfAssurance"], "unknown")
