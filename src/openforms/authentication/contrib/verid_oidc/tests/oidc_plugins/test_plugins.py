"""
Tests for the mozilla-django-oidc-db ``VerIDPlugin`` implementation.

Focused on the claim-processing machinery that's bespoke to Ver.iD:

- empty configured identity paths are tolerated (Ver.iD disclosure flows
  often have no BSN/KvK/pseudo)
- top-level non-identity claims flow into ``additional_claims``
- ``get_sensitive_claims`` never returns an empty path (would break
  ``obfuscate_claims``)
- ``get_extra_params`` is a no-op (Ver.iD encodes attributes in the flow,
  not in the request)
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from openforms.authentication.contrib.verid_oidc.oidc_plugins.plugins import (
    VerIDPlugin,
)


def _config(*, identity=None, loa=None) -> SimpleNamespace:
    return SimpleNamespace(
        options={
            "identity_settings": identity
            or {"bsn_claim_path": [], "kvk_claim_path": [], "pseudo_claim_path": []},
            "loa_settings": loa or {
                "bsn_loa_claim_path": [],
                "kvk_loa_claim_path": [],
                "bsn_default_loa": "",
                "kvk_default_loa": "",
                "bsn_loa_value_mapping": [],
                "kvk_loa_value_mapping": [],
            },
        }
    )


def _plugin(config) -> VerIDPlugin:
    plugin = VerIDPlugin(identifier="oidc-verid-test")
    plugin.get_config = mock.Mock(return_value=config)  # type: ignore[method-assign]
    return plugin


class GetClaimProcessingInstructionsTests(SimpleTestCase):
    def test_empty_identity_paths_produce_no_identity_claims(self):
        config = _config()
        plugin = _plugin(config)
        claims = {"straat": "Valkenboskade"}

        instructions = plugin.get_claim_processing_instructions(claims, config)

        # No bsn/kvk/pseudo entries — paths were empty
        processed_paths = [
            entry["processed_path"] for entry in instructions["optional_claims"]
        ]
        self.assertNotIn(["bsn_claim"], processed_paths)
        self.assertNotIn(["kvk_claim"], processed_paths)
        self.assertNotIn(["pseudo_claim"], processed_paths)

    def test_top_level_claims_flow_into_additional_claims(self):
        plugin = _plugin(_config())
        claims = {"straat": "Valkenboskade", "huisnummer": "636"}

        instructions = plugin.get_claim_processing_instructions(claims, _config())

        processed_paths = [
            entry["processed_path"] for entry in instructions["optional_claims"]
        ]
        self.assertIn(["additional_claims", "straat"], processed_paths)
        self.assertIn(["additional_claims", "huisnummer"], processed_paths)

    def test_identity_claim_paths_are_reserved_from_additional_claims(self):
        config = _config(
            identity={
                "bsn_claim_path": ["bsn"],
                "kvk_claim_path": ["kvk"],
                "pseudo_claim_path": ["sub"],
            }
        )
        plugin = _plugin(config)
        # `bsn` is present in claims but should be processed as identity, not
        # duplicated into additional_claims.
        claims = {"bsn": "111222333", "straat": "Valkenboskade"}

        instructions = plugin.get_claim_processing_instructions(claims, config)

        path_pairs = [
            (tuple(e["path_in_claim"]), tuple(e["processed_path"]))
            for e in instructions["optional_claims"]
        ]
        self.assertIn((("bsn",), ("bsn_claim",)), path_pairs)
        self.assertNotIn(
            (("bsn",), ("additional_claims", "bsn")),
            path_pairs,
            "BSN should not be duplicated into additional_claims",
        )

    def test_no_loa_assigned_when_neither_bsn_nor_kvk(self):
        plugin = _plugin(_config())
        claims = {"straat": "Valkenboskade"}

        instructions = plugin.get_claim_processing_instructions(claims, _config())

        # The default empty LoA structure stays, _process_loa will short-circuit.
        self.assertEqual(instructions["loa_claims"]["path_in_claim"], [])
        self.assertEqual(instructions["loa_claims"]["processed_path"], [])


class GetSensitiveClaimsTests(SimpleTestCase):
    def test_empty_paths_are_filtered_out(self):
        # If any returned path is [], obfuscate_claims will explode.
        plugin = _plugin(_config())
        claims = {"straat": "Valkenboskade", "postcode": "2563JP"}

        sensitive = plugin.get_sensitive_claims(claims)

        for path in sensitive:
            self.assertGreater(len(path), 0, f"empty path returned: {path!r}")

    def test_disclosed_claim_keys_are_marked_sensitive(self):
        plugin = _plugin(_config())
        claims = {"straat": "Valkenboskade", "postcode": "2563JP"}

        sensitive = plugin.get_sensitive_claims(claims)

        self.assertIn(["straat"], sensitive)
        self.assertIn(["postcode"], sensitive)


class GetExtraParamsTests(SimpleTestCase):
    def test_no_op(self):
        # Ver.iD encodes disclosure scope in the flow definition; the plugin
        # must NOT add any per-request scope/claims params.
        plugin = _plugin(_config())
        initial = {"prompt": "login", "ui_locales": "nl"}

        out = plugin.get_extra_params(request=None, extra_params=initial)

        self.assertEqual(out, initial)
