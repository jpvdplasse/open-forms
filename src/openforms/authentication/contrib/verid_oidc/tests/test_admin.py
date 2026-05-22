"""
Tests for the OIDCClient admin override.

The override re-registers the OIDCClient admin so the secret field becomes
optional for any row whose ``identifier`` matches the Ver.iD prefix. This
mirrors Ver.iD's public-client (PKCE-only) auth model and avoids forcing
admins to enter dummy secrets.
"""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from mozilla_django_oidc_db.models import OIDCClient

from openforms.authentication.contrib.verid_oidc.admin import (
    _PKCEAwareOIDCClientAdmin,
)


class PKCEAwareAdminFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # The default oidc-verid row is loaded by fixture; use a unique
        # identifier per test class to avoid collisions.
        cls.verid_client, _ = OIDCClient.objects.update_or_create(
            identifier="oidc-verid-admin-test",
            defaults=dict(
                enabled=False,
                oidc_rp_client_id="some-flow-uuid",
                oidc_rp_client_secret="",
                oidc_rp_sign_algo="ES384",
            ),
        )
        cls.other_client, _ = OIDCClient.objects.update_or_create(
            identifier="oidc-other-admin-test",
            defaults=dict(
                enabled=False,
                oidc_rp_client_id="x",
                oidc_rp_client_secret="real-secret",
            ),
        )

    def setUp(self):
        self.admin_instance = _PKCEAwareOIDCClientAdmin(OIDCClient, admin.site)
        self.request = RequestFactory().get("/")
        # The admin's get_form path checks request.user for inline permission
        # decisions; attach a superuser so we don't trip those.
        UserModel = get_user_model()
        self.request.user = UserModel(
            username="t", is_staff=True, is_superuser=True
        )

    def test_secret_optional_for_verid_client(self):
        form_cls = self.admin_instance.get_form(
            self.request, obj=self.verid_client, change=True
        )
        form = form_cls(instance=self.verid_client)
        self.assertFalse(form.fields["oidc_rp_client_secret"].required)
        self.assertIn(
            "Ver.iD",
            str(form.fields["oidc_rp_client_secret"].help_text),
        )

    def test_secret_unchanged_for_non_verid_client(self):
        form_cls = self.admin_instance.get_form(
            self.request, obj=self.other_client, change=True
        )
        form = form_cls(instance=self.other_client)
        # Inherits upstream required default.
        self.assertTrue(form.fields["oidc_rp_client_secret"].required)

    def test_add_form_uses_default(self):
        # No obj yet (creating a new client) — fall through to upstream form.
        form_cls = self.admin_instance.get_form(self.request, obj=None, change=False)
        # The patched form override is only injected when obj is a Ver.iD row.
        # For add forms we accept the upstream behaviour.
        form = form_cls()
        self.assertTrue(form.fields["oidc_rp_client_secret"].required)
