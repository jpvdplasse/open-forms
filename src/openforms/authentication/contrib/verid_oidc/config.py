from typing import TypedDict

from django.utils.translation import gettext_lazy as _

from rest_framework import serializers

from openforms.utils.mixins import JsonSchemaSerializerMixin


class VerIDOptions(TypedDict, total=False):
    """
    Shape of the Ver.iD authentication plugin options after validation.

    The tenant connection (issuer endpoints, JWKS, iss/aud pins) lives on a
    single ``OIDCClient`` row keyed by ``oidc-verid``. The per-form options
    here carry the values that vary between forms: the disclosure flow's
    ``client_id`` (UUID from Ver.iD Studio) and an optional ``client_secret``
    (only set when Ver.iD Studio configured the flow as a confidential
    client; disclosure flows are public/PKCE by default).
    """

    client_id: str
    client_secret: str


class VerIDOptionsSerializer(JsonSchemaSerializerMixin, serializers.Serializer):
    client_id = serializers.CharField(
        label=_("Ver.iD disclosure flow ID"),
        help_text=_(
            "UUID of the Ver.iD disclosure flow this form should use "
            "(visible in Ver.iD Studio on the flow's configuration page)."
        ),
        required=True,
        allow_blank=False,
    )
    client_secret = serializers.CharField(
        label=_("Ver.iD disclosure flow secret"),
        help_text=_(
            "Optional. Leave blank for public/PKCE disclosure flows (the default). "
            "Only fill in if Ver.iD Studio explicitly configured a client secret "
            "for this flow."
        ),
        required=False,
        allow_blank=True,
        default="",
    )
