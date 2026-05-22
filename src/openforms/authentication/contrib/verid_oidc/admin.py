"""
Admin overrides for Ver.iD OIDCClient rows.

Ver.iD's disclosure flow is a public OIDC client (PKCE-only) — it has no
client_secret. The upstream OIDCClient admin form treats secret as required,
which blocks creating/editing Ver.iD-tagged clients with a real configuration.
This module re-registers the OIDCClient admin so the secret field becomes
optional whenever the row's identifier starts with the Ver.iD prefix.
"""

from __future__ import annotations

from django.contrib import admin
from django.http import HttpRequest

from mozilla_django_oidc_db.admin import OIDCClientAdmin as UpstreamOIDCClientAdmin
from mozilla_django_oidc_db.models import OIDCClient

from .constants import OIDC_CLIENT_IDENTIFIER_PREFIX


class _PKCEAwareOIDCClientAdmin(UpstreamOIDCClientAdmin):
    """Marks ``oidc_rp_client_secret`` as not required for Ver.iD-tagged clients."""

    def get_form(self, request: HttpRequest, obj=None, change=False, **kwargs):
        form_cls = super().get_form(request, obj=obj, change=change, **kwargs)

        is_verid = bool(obj) and (
            obj.identifier or ""
        ).startswith(OIDC_CLIENT_IDENTIFIER_PREFIX)
        if not is_verid:
            return form_cls

        # Make the secret field optional by mutating the base form class
        # in place. We avoid subclassing because that risks dropping the
        # `widget.instance = obj` assignment the upstream admin sets on
        # ``base_fields["options"]`` (django_jsonform requires it).
        if "oidc_rp_client_secret" in form_cls.base_fields:
            form_cls.base_fields["oidc_rp_client_secret"].required = False
            form_cls.base_fields["oidc_rp_client_secret"].help_text = (
                "Leave blank for Ver.iD disclosure flows — they use PKCE "
                "(public clients) and do not authenticate with a secret."
            )

        return form_cls


# Replace the default registration.
try:
    admin.site.unregister(OIDCClient)
except admin.sites.NotRegistered:
    pass
admin.site.register(OIDCClient, _PKCEAwareOIDCClientAdmin)
