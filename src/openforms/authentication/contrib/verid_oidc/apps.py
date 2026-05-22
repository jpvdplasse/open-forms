from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

import structlog

logger = structlog.stdlib.get_logger(__name__)


class VerIDOIDCApp(AppConfig):
    name = "openforms.authentication.contrib.verid_oidc"
    label = "verid_oidc"
    verbose_name = _("Ver.iD via OpenID Connect")

    def ready(self):
        from . import admin as _admin  # noqa: register the OIDCClient admin override
        from . import plugin  # noqa: register the Open Forms auth plugin
        from .oidc_plugins import plugins  # noqa: register VerIDPlugin class

        self._register_default_client()
        self._patch_oidc_token_handling()

    @staticmethod
    def _register_default_client() -> None:
        """Register the OIDC plugin for the single Ver.iD tenant identifier.

        Earlier versions of this plugin scanned the OIDCClient table at startup
        to register additional identifiers per disclosure flow. Per-form
        ``client_id`` is now carried on the form options instead, so a single
        tenant identifier is sufficient and we avoid the
        "Accessing the database during app initialization" anti-pattern.
        """
        from mozilla_django_oidc_db.registry import register as oidc_register

        from .constants import OIDC_CLIENT_IDENTIFIER
        from .oidc_plugins.plugins import VerIDPlugin

        if OIDC_CLIENT_IDENTIFIER not in oidc_register._registry:
            oidc_register(OIDC_CLIENT_IDENTIFIER)(VerIDPlugin)

    @staticmethod
    def _patch_oidc_token_handling() -> None:
        """
        Adapt mozilla-django-oidc for Ver.iD's non-standard OIDC profile.

        1. Public-client token request: Ver.iD advertises
           ``token_endpoint_auth_methods_supported: ["none"]`` for the
           disclosure flow. When PKCE is in use and no per-form client_secret
           was configured, drop ``client_secret`` from the token request body.
        2. Per-form ``client_id`` (and optional ``client_secret``) live on the
           form options and were stashed in session at start_login. Inject
           them into the token-exchange payload here so the request matches
           the disclosure flow the user actually authorized against.
        3. Disclosure responses contain only ``access_token``; the disclosed
           claims live inside that token. Copy ``access_token`` to
           ``id_token`` so the rest of the OIDC pipeline can process it.
        4. The token's ``iss`` is a Ver.iD URN and ``aud`` is a Ver.iD URN
           too — neither matches an OIDC Provider issuer URL. Replace the
           upstream JWS verifier with one that fetches the JWKS, verifies
           the signature, and checks ``iss``/``aud`` against pinned values.
        5. Flatten Ver.iD's ``mapping.<name>.value`` structure into top-level
           claims so the prefill plugin can address them by simple name.

        All patches are gated by the OIDCClient identifier so non-Ver.iD
        providers in the same install keep their normal behaviour.
        """
        from mozilla_django_oidc import auth as _mdo_auth

        from .constants import (
            OIDC_CLIENT_IDENTIFIER,
            SESSION_FORM_CLIENT_ID_KEY,
            SESSION_FORM_CLIENT_SECRET_KEY,
        )

        if getattr(_mdo_auth, "_verid_token_patch_applied", False):
            return

        original_get_token = _mdo_auth.OIDCAuthenticationBackend.get_token
        original_verify_token = _mdo_auth.OIDCAuthenticationBackend.verify_token

        def _is_verid_client(backend) -> bool:
            config = getattr(backend, "config", None)
            identifier = (getattr(config, "identifier", "") or "")
            return identifier == OIDC_CLIENT_IDENTIFIER

        def _get_token(self, payload):
            if not _is_verid_client(self):
                return original_get_token(self, payload)

            if isinstance(payload, dict):
                payload = dict(payload)

                # Inject the form-selected disclosure flow credentials,
                # overriding the OIDCClient's placeholder values.
                request = getattr(self, "request", None)
                session = getattr(request, "session", None) if request else None
                form_client_id = (session or {}).get(SESSION_FORM_CLIENT_ID_KEY)
                form_client_secret = (session or {}).get(SESSION_FORM_CLIENT_SECRET_KEY)

                if form_client_id:
                    payload["client_id"] = form_client_id
                if form_client_secret:
                    payload["client_secret"] = form_client_secret
                elif "code_verifier" in payload:
                    # Public PKCE client → drop client_secret entirely.
                    payload.pop("client_secret", None)

            result = original_get_token(self, payload)
            if (
                isinstance(result, dict)
                and not result.get("id_token")
                and result.get("access_token")
            ):
                result = {**result, "id_token": result["access_token"]}
            return result

        def _verify_token(self, token, **kwargs):
            from .verification import VerIDNonToken, verify_verid_token

            if not _is_verid_client(self):
                return original_verify_token(self, token, **kwargs)

            if isinstance(token, bytes):
                token = token.decode()

            try:
                claims = verify_verid_token(token, config=self.config)
            except VerIDNonToken:
                return original_verify_token(self, token, **kwargs)

            mapping = claims.get("mapping") or {}
            for name, descriptor in mapping.items():
                if isinstance(descriptor, dict) and "value" in descriptor:
                    claims.setdefault(name, descriptor["value"])
            return claims

        _mdo_auth.OIDCAuthenticationBackend.get_token = _get_token
        _mdo_auth.OIDCAuthenticationBackend.verify_token = _verify_token
        _mdo_auth._verid_token_patch_applied = True  # type: ignore[attr-defined]
