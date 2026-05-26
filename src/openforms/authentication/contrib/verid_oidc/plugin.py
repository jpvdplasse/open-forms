from collections.abc import MutableMapping
from typing import Literal, TypedDict, assert_never

from django.http import HttpRequest, HttpResponseBadRequest, HttpResponseRedirect
from django.templatetags.static import static
from django.utils.translation import gettext_lazy as _

from mozilla_django_oidc_db.views import OIDCAuthenticationRequestInitView

from openforms.contrib.auth_oidc.plugin import OIDCAuthentication
from openforms.contrib.auth_oidc.typing import OIDCErrors
from openforms.forms.models import Form
from openforms.typing import AnyRequest, JSONValue
from openforms.utils.urls import reverse_plus

from ...base import LoginLogo
from ...constants import (
    CO_SIGN_PARAMETER,
    FORM_AUTH_SESSION_KEY,
    AuthAttribute,
    LogoAppearance,
)
from ...models import AuthInfo
from ...registry import register
from ...types import PluginAuthContext
from ...typing import FormAuth
from .config import VerIDOptions, VerIDOptionsSerializer
from .constants import (
    LOGIN_CANCELLED,
    OIDC_CLIENT_IDENTIFIER,
    PLUGIN_ID,
    SESSION_FORM_CLIENT_ID_KEY,
    SESSION_FORM_CLIENT_SECRET_KEY,
    VERID_MESSAGE_PARAMETER,
)


class VerIDClaims(TypedDict, total=False):
    """Processed Ver.iD claims (output of the OIDC plugin's claim processing)."""

    bsn_claim: str
    kvk_claim: str
    pseudo_claim: str
    loa_claim: str | int | float
    additional_claims: MutableMapping[str, JSONValue]


@register(PLUGIN_ID)
class VerIDOIDCAuthentication(OIDCAuthentication[VerIDClaims, VerIDOptions]):
    verbose_name = _("Ver.iD wallet")
    provides_multiple_auth_attributes = True
    provides_auth = (AuthAttribute.bsn, AuthAttribute.kvk, AuthAttribute.pseudo)
    # Single tenant OIDCClient row for all Ver.iD flows. Per-form client_id
    # and client_secret are stored on the form options and threaded through
    # the OIDC dance via session state — see :func:`_patch_oidc_token_handling`.
    oidc_plugin_identifier = OIDC_CLIENT_IDENTIFIER
    configuration_options = VerIDOptionsSerializer
    manage_auth_context = True

    def get_error_codes(self) -> OIDCErrors:
        return {"access_denied": (VERID_MESSAGE_PARAMETER, LOGIN_CANCELLED)}

    def start_login(
        self,
        request: HttpRequest,
        form: Form,
        form_url: str,
        options: VerIDOptions,
    ) -> HttpResponseRedirect:
        # Stash the form-selected disclosure flow credentials on the session
        # so the token-exchange step (in :func:`_patch_oidc_token_handling`)
        # can read them out without a new DB lookup.
        client_id = options.get("client_id") or ""
        client_secret = options.get("client_secret") or ""
        request.session[SESSION_FORM_CLIENT_ID_KEY] = client_id
        request.session[SESSION_FORM_CLIENT_SECRET_KEY] = client_secret

        return_url_query = {"next": form_url}
        if co_sign_param := request.GET.get(CO_SIGN_PARAMETER):
            return_url_query[CO_SIGN_PARAMETER] = co_sign_param

        return_url = reverse_plus(
            "authentication:return",
            kwargs={"slug": form.slug, "plugin_id": self.identifier},
            request=request,
            query=return_url_query,
        )

        init_view = OIDCAuthenticationRequestInitView.as_view(
            identifier=self.oidc_plugin_identifier,
            allow_next_from_query=False,
        )
        response = init_view(request, return_url=return_url)
        assert isinstance(response, HttpResponseRedirect)
        # The init view built the authorize URL from the OIDCClient's stored
        # client_id (the placeholder tenant value). Rewrite that one query
        # param to the form-selected disclosure flow's client_id so the user
        # lands on the correct flow on Ver.iD's side.
        if client_id:
            response = self._rewrite_client_id(response, client_id)
        return response

    @staticmethod
    def _rewrite_client_id(
        response: HttpResponseRedirect, client_id: str
    ) -> HttpResponseRedirect:
        import urllib.parse

        location = response["Location"]
        parsed = urllib.parse.urlparse(location)
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        rewritten = [
            (k, client_id) if k == "client_id" else (k, v) for k, v in query
        ]
        new_url = urllib.parse.urlunparse(
            parsed._replace(query=urllib.parse.urlencode(rewritten))
        )
        return HttpResponseRedirect(new_url)

    def handle_return(
        self, request: HttpRequest, form: Form, options: VerIDOptions
    ) -> HttpResponseRedirect | HttpResponseBadRequest:
        form_url = request.GET.get("next")
        if not form_url:
            return HttpResponseBadRequest("missing 'next' parameter")

        normalized_claims: VerIDClaims | None = request.session.get(
            self.oidc_plugin_identifier
        )
        if normalized_claims and CO_SIGN_PARAMETER not in request.GET:
            form_auth = self.transform_claims(options, normalized_claims)
            request.session[FORM_AUTH_SESSION_KEY] = form_auth
        return HttpResponseRedirect(form_url)

    def logout(self, request: HttpRequest):
        for key in (
            SESSION_FORM_CLIENT_ID_KEY,
            SESSION_FORM_CLIENT_SECRET_KEY,
            self.oidc_plugin_identifier,
        ):
            if key in request.session:
                del request.session[key]
        super().logout(request)

    @staticmethod
    def _get_auth_attribute(claims: VerIDClaims) -> AuthAttribute:
        """Decide which identity attribute the wallet disclosed.

        BSN takes precedence (if a citizen disclosed both, identity-as-citizen
        wins); then KvK; otherwise pseudo.
        """
        if claims.get("bsn_claim"):
            return AuthAttribute.bsn
        if claims.get("kvk_claim"):
            return AuthAttribute.kvk
        return AuthAttribute.pseudo

    def transform_claims(
        self, options: VerIDOptions, normalized_claims: VerIDClaims
    ) -> FormAuth:
        auth_attribute = self._get_auth_attribute(normalized_claims)

        def _build_form_auth(value: str, loa: str) -> FormAuth:
            return {
                "attribute": auth_attribute,
                "plugin": self.identifier,
                "value": value,
                "loa": loa,
                "additional_claims": normalized_claims.get("additional_claims") or {},
            }

        match auth_attribute:
            case AuthAttribute.bsn:
                assert "bsn_claim" in normalized_claims
                return _build_form_auth(
                    normalized_claims["bsn_claim"],
                    str(normalized_claims.get("loa_claim", "")),
                )
            case AuthAttribute.kvk:
                assert "kvk_claim" in normalized_claims
                return _build_form_auth(
                    normalized_claims["kvk_claim"],
                    str(normalized_claims.get("loa_claim", "")),
                )
            case AuthAttribute.pseudo:
                value = (
                    normalized_claims.get("pseudo_claim", "")
                    or "dummy-set-by@openforms"
                )
                return _build_form_auth(value, "unknown")
            case _:  # pragma: no cover
                assert_never(auth_attribute)

    def auth_info_to_auth_context(self, auth_info: AuthInfo) -> PluginAuthContext:
        auth_attribute = AuthAttribute(auth_info.attribute)
        match auth_attribute:
            case AuthAttribute.bsn:
                identifier_type: Literal["bsn", "kvkNummer", "opaque"] = "bsn"
            case AuthAttribute.kvk:
                identifier_type = "kvkNummer"
            case AuthAttribute.pseudo:
                identifier_type = "opaque"
            case _:
                raise NotImplementedError(
                    f"Auth attribute '{auth_attribute}' is not supported"
                )

        extra_claims = auth_info.additional_claims
        assert isinstance(extra_claims, dict)

        return {
            "source": "verid",
            "authorizee": {
                "legalSubject": {
                    "identifierType": identifier_type,
                    "identifier": auth_info.value,
                    "additionalInformation": extra_claims,
                }
            },
            "levelOfAssurance": auth_info.loa,
        }

    def get_label(self) -> str:
        # The SDK renders the citizen-facing CTA as "Inloggen met {label}",
        # but a Ver.iD disclosure flow is conceptually data-sharing, not
        # authentication. Until the SDK supports a per-plugin CTA template
        # (see REVIEW.md option 3), we steer the label so the button reads
        # "Inloggen met Ver.iD (gegevens delen)" — slightly awkward but
        # communicates intent better than "Inloggen met Ver.iD" alone.
        return str(_("Ver.iD (gegevens delen)"))

    def get_logo(self, request: HttpRequest) -> LoginLogo:
        return LoginLogo(
            title=self.get_label(),
            image_src=request.build_absolute_uri(static("img/verid.svg")),
            href="https://ver.id/",
            appearance=LogoAppearance.dark,
        )

    def check_requirements(self, request: AnyRequest, options: VerIDOptions) -> bool:
        # No LoA-based requirements gating here — Ver.iD disclosure flows
        # encode their own assurance level inside the flow definition. The
        # discrete decisions a form might want to make based on LoA can be
        # added later via form logic rules.
        return True
