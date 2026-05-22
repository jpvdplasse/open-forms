# Ver.iD wallet authentication for Open Forms

Drop-in authentication & prefill plugin so Open Forms can consume **Ver.iD** (https://ver.id) digital-wallet disclosure flows over OIDC. Citizens log in with their wallet, consent to share specific attributes, and selected form fields are auto-filled from those attributes.

Sister plugin: `openforms.prefill.contrib.verid` — the prefill source that reads the disclosed claims off the submission.

## Architecture in one paragraph

A single tenant-level `OIDCClient` row holds the Ver.iD tenant connection (issuer URLs, JWKS endpoint, pinned `iss`/`aud`). Each form picks **which Ver.iD disclosure flow** it uses by setting that flow's UUID as `client_id` (and optional `client_secret`) on the form's authentication backend options. At login time, those per-form values are injected into the OIDC token request and the user is sent to Ver.iD; on return, the disclosure JWT is signature-verified against the JWKS, iss/aud are checked, and the `mapping.<name>.value` structure is flattened into top-level claims that the prefill plugin can surface to form fields by claim name.

## Operator setup

Prerequisites:
- Open Forms running locally or on a host reachable from the user's browser
- A Ver.iD Studio account with a configured **disclosure flow** (gives you a flow UUID + optionally a secret)
- The tenant's OIDC issuer URL (typically `https://ssi.oauth.ver.id/`)
- *Optional*: an admin OAuth client for the Ver.iD GraphQL API (for live disclosure/claim auto-discovery in the form-builder)

### 1. Register the apps

In your settings:
```python
INSTALLED_APPS += [
    "openforms.authentication.contrib.verid_oidc.apps.VerIDOIDCApp",
    "openforms.prefill.contrib.verid",
]

# Required by Ver.iD's public-client (PKCE-only) token endpoint:
OIDC_USE_PKCE = True
OIDC_PKCE_CODE_CHALLENGE_METHOD = "S256"

# Pin Ver.iD's URN-based iss/aud values for your tenant
OIDC_VERID_EXPECTED_ISS = "urn:ver-id:crypto:key@production:oauth/v1"
OIDC_VERID_EXPECTED_AUD = "urn:ver-id:crypto:key@external:*"
```

Then `python src/manage.py migrate verid_oidc` (creates an empty initial migration; the only model state we own lives on existing OIDCClient rows).

### 2. Configure the tenant OIDCClient

In Django admin → **OIDC Clients** → **Add OIDC client** (or edit the existing `oidc-verid` row):

| Field | Value |
|---|---|
| `identifier` | `oidc-verid` (must be exactly this for the dynamic registration to find it) |
| `enabled` | ✓ |
| `oidc_rp_sign_algo` | **`ES384`** (Ver.iD signs with ECDSA-P384) |
| `oidc_rp_idp_sign_key` | leave blank (auto-fetched from JWKS) |
| `oidc_rp_client_id` | placeholder (the *real* client_id is per-form) |
| `oidc_rp_client_secret` | leave blank — the admin form makes it optional for `oidc-verid` |
| `oidc_op_discovery_endpoint` | `https://ssi.oauth.ver.id/` |
| `oidc_op_*_endpoint` | leave blank (auto-derived from discovery) |
| `options.identity_settings.bsn_claim_path` | `[]` for pure disclosure flows, or `["bsn"]` if a flow includes BSN identity |
| `options.identity_settings.kvk_claim_path` | similar, default `[]` |
| `options.identity_settings.pseudo_claim_path` | `[]` (Ver.iD doesn't use OIDC `sub` for disclosure) |
| `options.verid_settings.expected_iss` | (optional) overrides the Django setting |
| `options.verid_settings.expected_aud` | (optional) overrides the Django setting |
| `options.verid_settings.graphql_client_id` | (optional) GraphQL admin OAuth client id, enables flow dropdown in form-builder |
| `options.verid_settings.graphql_client_secret` | (optional) GraphQL admin OAuth client secret |

### 3. Register the redirect URI in Ver.iD Studio

For each disclosure flow that should be usable from your Open Forms install, in **Ver.iD Studio** → flow's **Allowed redirect URIs** → add:

```
https://<your-openforms-host>/auth/oidc/callback/
```

(For local dev: `http://localhost:8000/auth/oidc/callback/`. Use the host the citizen's browser will visit — Ver.iD compares strings exactly.)

### 4. Build a form

In the form-builder:

1. **Authentication** tab → tick **Ver.iD wallet** → click **Configure options**.
2. **Disclosure flow** dropdown — pick the flow this form should use. (If GraphQL credentials are configured on the tenant OIDCClient, you'll see a dropdown of live flows; otherwise it's a text field for the UUID.)
3. **Client secret** — leave blank unless your specific flow in Ver.iD Studio was set up as a confidential client.
4. **Steps and fields** tab → add text fields → in each field's **Prefill** section:
   - Plugin: **Ver.iD wallet**
   - Attribute: pick from the dropdown (e.g. `straat`, `postcode`, `huisnummer`) — or type the claim name if no GraphQL.
5. Save the form.

### 5. Test

Open the form's public URL. The citizen sees a Ver.iD login button → bounces to Ver.iD's gateway page → consents to share the requested attributes → returns to the form → fields prefilled.

## Optional: GraphQL discovery

If you provide `graphql_client_id` + `graphql_client_secret` on the tenant OIDCClient (Ver.iD Studio → API → create an OAuth client with admin scope), the form-builder:

- Lists all your org's active disclosure flows in the per-form **Disclosure flow** dropdown
- Lists each flow's actual claim names in the **Plugin attribute** picker

Backed by two admin-only REST endpoints:

| URL | Returns |
|---|---|
| `GET /api/v2/authentication/plugins/verid/disclosures` | `[{uuid, name, state, mapping_verification_uuid}]` |
| `GET /api/v2/authentication/plugins/verid/disclosures/<uuid>/claims` | `[{name, claim}]` |

Both return `503` if GraphQL credentials are absent (form-builder gracefully degrades to text inputs). 5-minute cache for both responses; 20-hour cache for the GraphQL access token.

## Settings reference

| Setting | Default | Purpose |
|---|---|---|
| `OIDC_USE_PKCE` | `False` | Must be `True` — Ver.iD's token endpoint is PKCE-only |
| `OIDC_PKCE_CODE_CHALLENGE_METHOD` | `"S256"` | The only method Ver.iD supports |
| `OIDC_VERID_EXPECTED_ISS` | `None` | Pin Ver.iD's URN issuer; required unless opted out |
| `OIDC_VERID_EXPECTED_AUD` | `None` | Pin expected `aud`; required unless opted out |
| `OIDC_VERID_REQUIRE_ISS_AUD_PINNING` | `True` | Set to `False` only for local demos |
| `OIDC_VERID_CLOCK_SKEW_SECONDS` | `60` | Clock-skew tolerance for `exp`/`nbf` checks |

## Settings opt-out for demos

If you genuinely need to skip iss/aud pinning during development:

```python
OIDC_VERID_REQUIRE_ISS_AUD_PINNING = False
```

Don't ship this to production — without pinning, any JWT signed by Ver.iD's JWKS keys is accepted.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `redirect_uri ... is not registered for the client` from Ver.iD | The flow's allowed redirect URIs in Ver.iD Studio don't include exactly `http(s)://<host>/auth/oidc/callback/` |
| `unauthorized_client` from Ver.iD's token endpoint | Plugin is sending a `client_secret` to a public PKCE flow. Confirm `OIDC_USE_PKCE = True` |
| `Compact JWS serialization should comprise of exactly 3 dot-separated components` | The response had no `id_token` — the `get_token` patch isn't applied (check `apps.ready()` ran) |
| `Ver.iD token verification requires a pinned expected_iss` | iss/aud pinning is mandatory by default. Set `OIDC_VERID_EXPECTED_ISS`/`_AUD` or opt out |
| Form-builder shows text input instead of disclosure dropdown | GraphQL credentials not set on `OIDCClient.options.verid_settings`. Either add them or leave as text input |
| Prefill attribute dropdown empty | The form's saved disclosure flow has no claims in Ver.iD Studio, OR the form needs to be saved after picking the flow |

See [REVIEW.md](./REVIEW.md) for a full code review including known defects and production-readiness checklist.
