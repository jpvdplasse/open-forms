"""
Form-builder API endpoints for the optional Ver.iD GraphQL discovery feature.

Both endpoints return ``503 Service Unavailable`` when GraphQL credentials
are not configured on the tenant OIDCClient — the form-builder can then
fall back to its plain text inputs.
"""

from __future__ import annotations

from django.http import Http404

from mozilla_django_oidc_db.models import OIDCClient
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..constants import OIDC_CLIENT_IDENTIFIER
from ..graphql_api import (
    GraphQLError,
    GraphQLNotConfigured,
    get_disclosure_claims,
    list_disclosures,
    load_config_from_oidc_client,
)


def _resolve_graphql_config():
    try:
        client = OIDCClient.objects.get(identifier=OIDC_CLIENT_IDENTIFIER)
    except OIDCClient.DoesNotExist as exc:
        raise GraphQLNotConfigured("Ver.iD OIDCClient row is missing") from exc
    config = load_config_from_oidc_client(client)
    if config is None:
        raise GraphQLNotConfigured(
            "GraphQL credentials not configured on OIDCClient.options.verid_settings"
        )
    return client, config


class _BaseAdminView(APIView):
    """Only authenticated staff can call these — they reveal disclosure flow
    metadata that should not be public."""

    permission_classes = [permissions.IsAdminUser]


class DisclosuresListView(_BaseAdminView):
    def get(self, request, *args, **kwargs):
        try:
            _client, config = _resolve_graphql_config()
        except GraphQLNotConfigured as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        try:
            disclosures = list_disclosures(config)
        except GraphQLError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY
            )
        visible = [d for d in disclosures if d.get("state") == "ACTIVE"]
        return Response(visible)


class DisclosureClaimsListView(_BaseAdminView):
    def get(self, request, uuid, *args, **kwargs):
        try:
            _client, config = _resolve_graphql_config()
        except GraphQLNotConfigured as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        try:
            disclosures = list_disclosures(config)
        except GraphQLError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY
            )
        match = next((d for d in disclosures if d["uuid"] == str(uuid)), None)
        if match is None or not match.get("mapping_verification_uuid"):
            raise Http404("Disclosure not found or has no mapping")

        try:
            claims = get_disclosure_claims(config, match["mapping_verification_uuid"])
        except GraphQLError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY
            )
        return Response(claims)


class FlowClaimsView(_BaseAdminView):
    """Return ``[{id, label}]`` claims for a disclosure flow identified by
    ``clientId`` query parameter.

    Used by the generic ``customAttributesUrl`` prefill mechanism — the form
    builder forwards the auth backend options as query params so this endpoint
    can scope the claim list to the selected flow.
    """

    def get(self, request, *args, **kwargs):
        client_id = (
            request.query_params.get("clientId")
            or request.query_params.get("client_id")
            or ""
        )
        if not client_id:
            return Response([])

        try:
            _client, config = _resolve_graphql_config()
        except GraphQLNotConfigured as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        try:
            disclosures = list_disclosures(config)
        except GraphQLError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY
            )

        match = next(
            (d for d in disclosures if d["uuid"] == client_id), None
        )
        if match is None or not match.get("mapping_verification_uuid"):
            return Response([])

        try:
            claims = get_disclosure_claims(config, match["mapping_verification_uuid"])
        except GraphQLError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY
            )

        return Response(
            [{"id": c["claim"], "label": c.get("name") or c["claim"]} for c in claims]
        )
