"""
Tests for the optional Ver.iD GraphQL discovery service.

External HTTP is mocked — these are pure unit tests asserting our query
shapes, caching behaviour, and graceful failure modes.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase

from openforms.authentication.contrib.verid_oidc.graphql_api import (
    GraphQLConfig,
    GraphQLError,
    get_disclosure_claims,
    list_disclosures,
    load_config_from_oidc_client,
)


def _config(**overrides) -> GraphQLConfig:
    return GraphQLConfig(
        client_id="cid",
        client_secret="csec",
        token_endpoint="https://api.example.test/token",
        graphql_endpoint="https://gql.example.test",
        **overrides,
    )


def _mock_responses(token_body=None, gql_responses=None):
    """Build a fake `requests.post` that dispatches based on URL."""
    if token_body is None:
        token_body = {"access_token": "fake-token", "expires_in": 86400}
    gql_responses = list(gql_responses or [])

    def _post(url, **kwargs):
        if "token" in url:
            return SimpleNamespace(
                status_code=200,
                json=lambda: token_body,
                raise_for_status=lambda: None,
            )
        if "gql" in url or "graphql" in url:
            assert gql_responses, "unexpected extra GraphQL call"
            body = gql_responses.pop(0)
            return SimpleNamespace(
                status_code=200,
                json=lambda: body,
                raise_for_status=lambda: None,
            )
        raise AssertionError(f"unexpected URL {url!r}")

    return _post


class LoadConfigFromOIDCClientTests(SimpleTestCase):
    def test_returns_none_when_missing(self):
        client = SimpleNamespace(options={"verid_settings": {}})
        self.assertIsNone(load_config_from_oidc_client(client))

    def test_returns_none_when_no_verid_settings_at_all(self):
        client = SimpleNamespace(options={})
        self.assertIsNone(load_config_from_oidc_client(client))

    def test_returns_config_when_credentials_present(self):
        client = SimpleNamespace(
            options={
                "verid_settings": {
                    "graphql_client_id": "id",
                    "graphql_client_secret": "secret",
                }
            }
        )
        cfg = load_config_from_oidc_client(client)
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.client_id, "id")
        self.assertEqual(cfg.client_secret, "secret")
        # default endpoints
        self.assertTrue(cfg.token_endpoint.endswith("/token/grant"))
        self.assertTrue(cfg.graphql_endpoint.endswith("ver.id"))

    def test_endpoint_overrides_are_respected(self):
        client = SimpleNamespace(
            options={
                "verid_settings": {
                    "graphql_client_id": "id",
                    "graphql_client_secret": "secret",
                    "graphql_token_endpoint": "https://other.test/token",
                    "graphql_endpoint": "https://other.test/graphql",
                }
            }
        )
        cfg = load_config_from_oidc_client(client)
        self.assertEqual(cfg.token_endpoint, "https://other.test/token")
        self.assertEqual(cfg.graphql_endpoint, "https://other.test/graphql")


class ListDisclosuresTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_returns_uuid_name_and_mapping_uuid(self):
        gql_body = {
            "data": {
                "findManyDisclosures": {
                    "edges": [
                        {
                            "node": {
                                "uuid": "uuid-1",
                                "name": "flow-1",
                                "state": "ACTIVE",
                                "disclosureMappings": {
                                    "edges": [
                                        {
                                            "node": {
                                                "mappingVerification": {
                                                    "uuid": "mv-1",
                                                    "name": "mv-1",
                                                }
                                            }
                                        }
                                    ]
                                },
                            }
                        }
                    ]
                }
            }
        }
        with mock.patch(
            "openforms.authentication.contrib.verid_oidc.graphql_api.requests.post",
            side_effect=_mock_responses(gql_responses=[gql_body]),
        ):
            result = list_disclosures(_config())

        self.assertEqual(
            result,
            [
                {
                    "uuid": "uuid-1",
                    "name": "flow-1",
                    "state": "ACTIVE",
                    "mapping_verification_uuid": "mv-1",
                }
            ],
        )

    def test_caches_within_ttl(self):
        gql_body = {
            "data": {
                "findManyDisclosures": {
                    "edges": [
                        {
                            "node": {
                                "uuid": "uuid-1",
                                "name": "flow-1",
                                "state": "ACTIVE",
                                "disclosureMappings": {"edges": []},
                            }
                        }
                    ]
                }
            }
        }
        with mock.patch(
            "openforms.authentication.contrib.verid_oidc.graphql_api.requests.post",
            side_effect=_mock_responses(gql_responses=[gql_body]),
        ) as mocked:
            first = list_disclosures(_config())
            second = list_disclosures(_config())

        self.assertEqual(first, second)
        # 1 token + 1 graphql = 2 calls only (second call is cached)
        self.assertEqual(mocked.call_count, 2)

    def test_graphql_errors_propagate(self):
        gql_body = {"errors": [{"message": "boom"}]}
        with mock.patch(
            "openforms.authentication.contrib.verid_oidc.graphql_api.requests.post",
            side_effect=_mock_responses(gql_responses=[gql_body]),
        ):
            with self.assertRaises(GraphQLError):
                list_disclosures(_config())


class GetDisclosureClaimsTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_returns_name_and_claim_pairs(self):
        gql_body = {
            "data": {
                "findMappingVerification": {
                    "name": "mv-1",
                    "mappingVerificationClaims": {
                        "edges": [
                            {"node": {"uuid": "c1", "name": "straat", "claim": "straat"}},
                            {"node": {"uuid": "c2", "name": "stad", "claim": "stad"}},
                        ]
                    },
                }
            }
        }
        with mock.patch(
            "openforms.authentication.contrib.verid_oidc.graphql_api.requests.post",
            side_effect=_mock_responses(gql_responses=[gql_body]),
        ):
            result = get_disclosure_claims(_config(), "mv-1")

        self.assertEqual(
            result,
            [
                {"name": "straat", "claim": "straat"},
                {"name": "stad", "claim": "stad"},
            ],
        )

    def test_missing_mapping_returns_empty_list(self):
        gql_body = {"data": {"findMappingVerification": None}}
        with mock.patch(
            "openforms.authentication.contrib.verid_oidc.graphql_api.requests.post",
            side_effect=_mock_responses(gql_responses=[gql_body]),
        ):
            result = get_disclosure_claims(_config(), "no-such-mv")
        self.assertEqual(result, [])
