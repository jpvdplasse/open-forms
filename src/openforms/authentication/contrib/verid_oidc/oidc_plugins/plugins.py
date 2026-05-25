from collections.abc import Collection
from typing import override

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponseBase

import structlog
from glom import Path, glom
from mozilla_django_oidc_db.models import OIDCClient
from mozilla_django_oidc_db.plugins import AnonymousUserOIDCPlugin
from mozilla_django_oidc_db.typing import ClaimPath, GetParams, JSONObject
from mozilla_django_oidc_db.utils import obfuscate_claims

from openforms.contrib.auth_oidc.typing import ClaimProcessingInstructions
from openforms.contrib.auth_oidc.utils import process_claims
from openforms.contrib.auth_oidc.views import anon_user_callback_view

from .schemas import VERID_SCHEMA

logger = structlog.stdlib.get_logger(__name__)


class VerIDPlugin(AnonymousUserOIDCPlugin):
    """
    OIDC plugin handling the Ver.iD wallet disclosure flow.

    One instance of this class is registered per Ver.iD ``OIDCClient`` row, with
    the row's ``identifier`` (see :func:`register_verid_oidc_plugins`). Each row
    corresponds to one Ver.iD disclosure flow configured in Ver.iD Studio: the
    row's ``oidc_rp_client_id`` holds the disclosure flow UUID and
    ``oidc_rp_client_secret`` holds its secret.

    The attribute set disclosed by a flow is part of the Ver.iD Studio
    definition, so this plugin does not synthesise per-request scope or claims
    parameters. It just runs the standard OIDC dance and stores the returned
    claims for the prefill plugin to consume.
    """

    @override
    def get_schema(self) -> JSONObject:
        return VERID_SCHEMA

    def get_sensitive_claims(self, claims: JSONObject) -> Collection[ClaimPath]:
        config = self.get_config()
        identity = config.options.get("identity_settings", {})
        identity_paths = [
            identity.get("bsn_claim_path") or [],
            identity.get("kvk_claim_path") or [],
            identity.get("pseudo_claim_path") or [],
        ]
        # Treat every disclosed claim as sensitive — the wallet only releases
        # what the disclosure flow asks for and the user consents to.
        disclosed_paths: list[ClaimPath] = [[key] for key in claims.keys() if key]
        # Drop any empty paths — Path(*[]) raises ValueError in mozilla's
        # obfuscate_claims util.
        return [p for p in [*identity_paths, *disclosed_paths] if p]

    @override
    def get_or_create_user(
        self,
        access_token: str,
        id_token: str,
        payload: JSONObject,
        request: HttpRequest,
    ) -> AnonymousUser:
        assert payload, "Empty claims should have been blocked earlier"

        obfuscated_claims = obfuscate_claims(
            payload, self.get_sensitive_claims(payload)
        )
        logger.debug("oidc_claims_received", claims=obfuscated_claims)

        try:
            processed_claims = self.process_claims(payload)
        except ValueError as exc:
            logger.error(
                "claim_processing_failure", reason="claims_incomplete", exc_info=exc
            )
            raise PermissionDenied("Claims verification failed")

        request.session[self.identifier] = processed_claims

        user = AnonymousUser()
        user.is_active = True  # type: ignore
        return user

    def process_claims(self, claims: JSONObject) -> JSONObject:
        config = self.get_config()
        instructions = self.get_claim_processing_instructions(claims, config)
        # All Ver.iD claims are optional from the framework's perspective —
        # the actual set is determined by the disclosure flow.
        return process_claims(claims, instructions, strict=False)

    @override
    def validate_settings(self) -> None:
        pass

    @override
    def handle_callback(self, request: HttpRequest) -> HttpResponseBase:
        return anon_user_callback_view(request)

    def get_claim_processing_instructions(
        self, claims: JSONObject, config: OIDCClient
    ) -> ClaimProcessingInstructions:
        identity = config.options.get("identity_settings", {})
        loa = config.options.get("loa_settings", {})

        bsn_path = identity.get("bsn_claim_path") or []
        kvk_path = identity.get("kvk_claim_path") or []
        pseudo_path = identity.get("pseudo_claim_path") or []

        has_bsn = bool(bsn_path) and bool(
            glom(claims, Path(*bsn_path), default=False)
        )
        has_kvk = bool(kvk_path) and bool(
            glom(claims, Path(*kvk_path), default=False)
        )

        # Only include identity claims whose configured path is non-empty —
        # glom raises ValueError on empty paths and Ver.iD disclosure flows
        # may not provide bsn/kvk/pseudo at all.
        optional_claims: list = []
        if bsn_path:
            optional_claims.append(
                {"path_in_claim": bsn_path, "processed_path": ["bsn_claim"]}
            )
        if kvk_path:
            optional_claims.append(
                {"path_in_claim": kvk_path, "processed_path": ["kvk_claim"]}
            )
        if pseudo_path:
            optional_claims.append(
                {"path_in_claim": pseudo_path, "processed_path": ["pseudo_claim"]}
            )

        instructions: ClaimProcessingInstructions = {
            "always_required_claims": [],
            "optional_claims": optional_claims,
            "strict_required_claims": [],
            "loa_claims": {
                "default": "",
                "path_in_claim": [],
                "value_mapping": [],
                "processed_path": [],
            },
        }

        match (has_bsn, has_kvk):
            case True, _:
                bsn_loa_path = loa.get("bsn_loa_claim_path") or []
                if bsn_loa_path:
                    instructions["loa_claims"] = {
                        "default": loa.get("bsn_default_loa", ""),
                        "path_in_claim": bsn_loa_path,
                        "value_mapping": loa.get("bsn_loa_value_mapping", []),
                        "processed_path": ["loa_claim"],
                    }
            case False, True:
                kvk_loa_path = loa.get("kvk_loa_claim_path") or []
                if kvk_loa_path:
                    instructions["loa_claims"] = {
                        "default": loa.get("kvk_default_loa", ""),
                        "path_in_claim": kvk_loa_path,
                        "value_mapping": loa.get("kvk_loa_value_mapping", []),
                        "processed_path": ["loa_claim"],
                    }

        # Pass through every other top-level claim into additional_claims so
        # the prefill plugin can surface any of them.
        identity_top_level_keys = {
            bsn_path[0] if bsn_path else None,
            kvk_path[0] if kvk_path else None,
            pseudo_path[0] if pseudo_path else None,
        }
        bsn_loa = loa.get("bsn_loa_claim_path") or []
        kvk_loa = loa.get("kvk_loa_claim_path") or []
        loa_top_level_keys = {
            bsn_loa[0] if bsn_loa else None,
            kvk_loa[0] if kvk_loa else None,
        }
        reserved = identity_top_level_keys | loa_top_level_keys
        instructions["optional_claims"].extend(
            {
                "path_in_claim": [key],
                "processed_path": ["additional_claims", *key.split(".")],
            }
            for key in claims.keys()
            if key not in reserved and key
        )
        return instructions

    @override
    def get_extra_params(
        self, request: HttpRequest, extra_params: GetParams
    ) -> GetParams:
        # Ver.iD requires scope=disclosure (not openid). Override it here so
        # the OIDCClient record doesn't need manual scope configuration.
        extra_params["scope"] = "disclosure"
        return extra_params
