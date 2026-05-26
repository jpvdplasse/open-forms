# Ver.iD plugin — code review

After-action review of the `verid_oidc` auth plugin + `verid` prefill plugin as they stand today. Documents what was built, where it's solid, what's still owed, and the production-readiness checklist.

## Scope

Python:
- `src/openforms/authentication/contrib/verid_oidc/` — auth plugin, OIDC plugin, verification, admin override, GraphQL discovery service, REST endpoints
- `src/openforms/prefill/contrib/verid/` — prefill plugin

JS (admin UI):
- `src/openforms/js/components/admin/form_design/authentication/verid/` — VeridOptionsForm + Fields
- `src/openforms/js/components/admin/form_design/authentication/index.js` — registered `verid_oidc` in `BACKEND_OPTIONS_FORMS`
Upstream-source touchpoints (generic — no Ver.iD references):
- `src/openforms/authentication/types.py` — `PluginAuthContext` TypedDict in `AnyAuthContext` union (generic for any `manage_auth_context` plugin)
- `src/openforms/prefill/base.py` — `get_custom_attributes_url()` hook
- `src/openforms/prefill/api/serializers.py` — `customAttributesUrl` field exposed on prefill plugin listing
- `src/openforms/js/components/formio_builder/plugins.js` — generic `customAttributesUrl` handler (forwards auth backend options as query params)
- `src/openforms/translations/api/urls.py` — `i18n/formio/<lang>` stub for SDK 3.5.0 compatibility

Plugin-specific touchpoints:
- `src/openforms/conf/base.py` — two `INSTALLED_APPS` entries
- `src/openforms/authentication/api/urls.py` — URL include for `plugins/verid/`
- `src/openforms/contrib/auth_oidc/tests/factories.py` — `with_verid` factory trait
- `src/openforms/js/components/admin/form_design/authentication/index.js` — `verid_oidc` in `BACKEND_OPTIONS_FORMS`

Other:
- `src/openforms/conf/local_verid_demo.py` — demo settings (PKCE on, iss/aud pinned, CORS open, MFA bypassed). NOT for production.
- `src/openforms/static/img/verid.svg` — logo

Tests:
- 50 tests, all passing. `manage.py check` clean.

## What's solid

- **Signature verification** (`verification.py`) — JWKS fetched & cached for 5min, JWS verified via mozilla-django-oidc-db's `verify_and_decode_token`, `exp`/`nbf` checked with configurable clock skew.
- **iss/aud pinning** enforced by default (opt-out via `OIDC_VERID_REQUIRE_ISS_AUD_PINNING = False` for demos).
- **Public-client PKCE** — `get_token` patch strips `client_secret` for PKCE flows, copies `access_token` → `id_token` so the rest of mozilla-django-oidc can process the Ver.iD-specific token shape.
- **Patches gated by identifier** — both `get_token` and `verify_token` monkey-patches check `self.config.identifier == "oidc-verid"` and pass through to the upstream code otherwise. Other OIDC clients in the same install (DigiD-OIDC, eHerkenning-OIDC, Yivi, etc.) are untouched.
- **Single tenant OIDCClient** + per-form `client_id`/`client_secret` carried on the form options. No more dynamic OIDCClient registration; no admin restart needed when adding new disclosure flows.
- **Optional GraphQL discovery** via `graphql_api.py` — when `OIDCClient.options.verid_settings.graphql_client_id`/`graphql_client_secret` are set, the form-builder Auth options modal shows a dropdown of live disclosure flows and the prefill attribute picker shows the selected flow's claim names. Falls back to text inputs (and `503` API responses) when GraphQL isn't configured.
- **Form-builder UX** — `VeridOptionsForm` registered in `BACKEND_OPTIONS_FORMS`; saved values are pre-selected on re-open.
- **JSON shape adaptation** — Ver.iD's `mapping.<name>.value` structure is flattened into top-level claims so the prefill plugin can address claims by simple name (`straat`, `postcode`, etc.).
- **Test coverage** — 50 tests including JWT tamper/expiry/iss/aud, PKCE token-request behaviour, admin form override, prefill identifier-role gating.

## Known defects / gaps

### ~~D1 — JS `getPrefillAttributes` is hard-coded~~ (RESOLVED)

Resolved: prefill plugins can now declare `get_custom_attributes_url()` and the JS handler fetches from that URL, forwarding auth backend options as query params. No per-plugin JS branches needed.

### ~~D2 — `AnyAuthContext` union is closed~~ (RESOLVED)

Resolved: `PluginAuthContext` added to the union in `types.py`. Any plugin with `manage_auth_context = True` can return its own context dict without patching `types.py`.

### D3 — Form-builder reactivity to mid-session flow changes (LOW)

If an admin opens a component edit modal, then in another tab changes the form's disclosure flow, the open modal still shows claims from the original flow. Normal workflow (set flow first, then edit fields) avoids this. Acceptable trade-off — the alternative caused over-fetching.

### D4 — `i18n/formio/<lang>` stub returns empty (LOW)

Added to `translations/api/urls.py` so SDK 3.5.0 doesn't 404. Returns `{}` — works but degrades any customised Formio translations. Replace with a real implementation if/when the upstream Open Forms ships one.

### D5 — Test coverage gaps (LOW)

- No end-to-end HTTP test of `/auth/<slug>/verid_oidc/start` → callback → `FormAuth` set on session.
- GraphQL service is not unit-tested (would need VCR cassettes or mock responses).
- New admin REST endpoints (`/disclosures`, `/disclosures/<uuid>/claims`) have no tests.

### D6 — CTA template is "Inloggen met X" for all plugins (MEDIUM — UX)

The SDK builds the citizen-facing login button from a global i18n string
`"Inloggen met {service}"`. For Ver.iD disclosure flows that's semantically
wrong — the user is sharing data, not authenticating. Other plugin types
(signature, issuance) would have similar mismatches.

**Today's workaround**: we cheat by setting `get_label()` to
`"Ver.iD (gegevens delen)"` so the button reads
`"Inloggen met Ver.iD (gegevens delen)"`. Mildly awkward Dutch but
communicates intent. Touches only `plugin.py`.

**Wanted long-term direction** (upstream SDK + Open Forms backend change):
allow each auth plugin to declare its own CTA template, e.g.

```python
class VerIDOIDCAuthentication(OIDCAuthentication[...]):
    # Existing
    verbose_name = _("Ver.iD wallet")
    # New: SDK message id for the citizen-facing button. Falls back to
    # "Inloggen met {service}" when not set, so existing plugins are
    # unaffected.
    cta_message_id = "verid.ctaShareData"  # or e.g. an enum value
```

The Open Forms API's `/api/v2/forms/<slug>/` response would surface this
on each `loginOption`, and the SDK would pick the template per-button.
This generalizes to a broader idea: distinguish *kind* of identity flow
(authentication / disclosure / signature) as a first-class concept,
matching Ver.iD's own categorization. Signature flows could similarly
read `"Onderteken met X"`, issuance could read `"Voeg X toe aan uw
wallet"`.

This is the proper fix and should land alongside any upstream PR.

### D7 — `wait_for_event` style JWK rotation (LOW)

If Ver.iD rotates keys mid-flight, the 5-minute JWKS cache will serve stale data and tokens with the new `kid` will fail until the cache expires. Add a cache-miss → refresh-once pattern.

### ~~D7 — Patches in `node_modules/@open-formulieren/formio-builder`~~ (RESOLVED)

Resolved: the earlier patch was removed and `patch-package` has been dropped from `package.json`.

## Production-readiness checklist

Before flipping the switch on a real tenant:

- [ ] Replace `CORS_ALLOW_ALL_ORIGINS = True` in `local_verid_demo.py` with explicit allow-list (production settings shouldn't import `local_verid_demo` anyway)
- [ ] Re-enable MFA on admin (drop `MAYKIN_2FA_ALLOW_MFA_BYPASS_BACKENDS` override)
- [ ] Pin `OIDC_VERID_EXPECTED_ISS` and `OIDC_VERID_EXPECTED_AUD` per environment
- [ ] Replace the dev-only `oidc_op_jwks_endpoint` validation behaviour if your provider rotates more aggressively than 5 min
- [ ] Verify the i18n/formio stub is OK to keep returning `{}` (or implement properly for your locale)
- [ ] Land the freeform formio-builder patches upstream OR keep the `patches/` directory under version control
- [ ] Confirm the OIDCClient's `verid_settings.graphql_client_id`/`graphql_client_secret` are environment-specific (per-tenant)
- [ ] Decide whether GraphQL discovery is a per-tenant feature (some orgs may not have API access)
- [ ] Add monitoring/alerting on `verid_token_response` and JWKS fetch failures

## Maintenance posture

- **Versioning**: Pin mozilla-django-oidc-db and add a CI test that imports the patched methods. Monkey-patches are the most likely break-point on library upgrades.
- **Ver.iD protocol drift**: the disclosure JWT shape (`mapping.<name>.value`, the `typ: ver-id/ssi/disclosure/v1+JWT` header) is undocumented in standards. Add a contract test against a captured fixture token that fails loudly when Ver.iD changes shape.
- **GraphQL schema drift**: the GraphQL queries in `graphql_api.py` could break if Ver.iD changes the schema. Add a smoke test that runs introspection on tenant boot.

## Bottom line

End-to-end works against the production Ver.iD tenant: login → consent → disclosure → token verification → claims flatten → form prefill. iss/aud pinning is mandatory by default. The integration is shaped like Yivi's in-tree integration and is a strong candidate to be upstreamed as a first-party Open Forms plugin.
