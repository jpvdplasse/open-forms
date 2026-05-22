"""
Tests for the form-builder REST endpoints:

- GET /api/v2/authentication/plugins/verid/disclosures
- GET /api/v2/authentication/plugins/verid/disclosures/<uuid>/claims

The endpoints proxy the Ver.iD GraphQL admin API. They return 503 when
GraphQL isn't configured, so the form-builder can fall back to text inputs.
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework.test import APITestCase

from mozilla_django_oidc_db.models import OIDCClient

from openforms.authentication.contrib.verid_oidc.constants import OIDC_CLIENT_IDENTIFIER


SAMPLE_DISCLOSURES = [
    {
        "uuid": "11111111-1111-1111-1111-111111111111",
        "name": "Sample flow",
        "state": "ACTIVE",
        "mapping_verification_uuid": "22222222-2222-2222-2222-222222222222",
    },
    {
        "uuid": "33333333-3333-3333-3333-333333333333",
        "name": "Inactive flow",
        "state": "DISABLED",
        "mapping_verification_uuid": "44444444-4444-4444-4444-444444444444",
    },
]

SAMPLE_CLAIMS = [{"name": "straat", "claim": "straat"}]


class DisclosuresListViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        UserModel = get_user_model()
        cls.admin = UserModel.objects.create_superuser(
            username="adm", email="a@b.test", password="x"
        )
        cls.client_obj, _ = OIDCClient.objects.update_or_create(
            identifier=OIDC_CLIENT_IDENTIFIER,
            defaults={"oidc_rp_client_id": "tenant", "options": {}},
        )

    def setUp(self):
        self.url = "/api/v2/authentication/plugins/verid/disclosures"
        self.client.force_authenticate(self.admin)

    def test_unauthenticated_is_forbidden(self):
        self.client.logout()
        self.client.force_authenticate(None)
        resp = self.client.get(self.url)
        self.assertIn(resp.status_code, (401, 403))

    def test_503_when_graphql_credentials_missing(self):
        self.client_obj.options = {}
        self.client_obj.save(update_fields=["options"])
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 503)

    def test_active_only_disclosures_returned(self):
        self.client_obj.options = {
            "verid_settings": {
                "graphql_client_id": "gid",
                "graphql_client_secret": "gsec",
            }
        }
        self.client_obj.save(update_fields=["options"])

        with mock.patch(
            "openforms.authentication.contrib.verid_oidc.api.views.list_disclosures",
            return_value=SAMPLE_DISCLOSURES,
        ):
            resp = self.client.get(self.url)

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # Disabled flow filtered out
        self.assertEqual(len(data), 1)
        self.assertEqual(
            data[0]["uuid"], "11111111-1111-1111-1111-111111111111"
        )


class DisclosureClaimsListViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        UserModel = get_user_model()
        cls.admin = UserModel.objects.create_superuser(
            username="adm2", email="a2@b.test", password="x"
        )
        cls.client_obj, _ = OIDCClient.objects.update_or_create(
            identifier=OIDC_CLIENT_IDENTIFIER,
            defaults={
                "oidc_rp_client_id": "tenant",
                "options": {
                    "verid_settings": {
                        "graphql_client_id": "gid",
                        "graphql_client_secret": "gsec",
                    }
                },
            },
        )

    def setUp(self):
        self.client.force_authenticate(self.admin)
        self.disclosure_uuid = "11111111-1111-1111-1111-111111111111"
        self.url = (
            f"/api/v2/authentication/plugins/verid/disclosures/{self.disclosure_uuid}/claims"
        )

    def test_returns_claims_for_known_disclosure(self):
        with mock.patch(
            "openforms.authentication.contrib.verid_oidc.api.views.list_disclosures",
            return_value=SAMPLE_DISCLOSURES,
        ), mock.patch(
            "openforms.authentication.contrib.verid_oidc.api.views.get_disclosure_claims",
            return_value=SAMPLE_CLAIMS,
        ):
            resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), SAMPLE_CLAIMS)

    def test_404_for_unknown_disclosure(self):
        with mock.patch(
            "openforms.authentication.contrib.verid_oidc.api.views.list_disclosures",
            return_value=SAMPLE_DISCLOSURES,
        ):
            resp = self.client.get(
                "/api/v2/authentication/plugins/verid/disclosures/"
                "99999999-9999-9999-9999-999999999999/claims"
            )
        self.assertEqual(resp.status_code, 404)
