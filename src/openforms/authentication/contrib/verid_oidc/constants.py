PLUGIN_ID = "verid_oidc"
VERID_MESSAGE_PARAMETER = "_verid-message"
LOGIN_CANCELLED = "login-cancelled"

# The single OIDCClient row holding the Ver.iD tenant connection (issuer
# endpoints, JWKS, iss/aud pinning). Per-form client_id/secret are stored on
# the form options, not on additional OIDCClient rows.
OIDC_CLIENT_IDENTIFIER = "oidc-verid"

# Backwards-compat alias kept for any code that still imports the old name.
OIDC_CLIENT_IDENTIFIER_PREFIX = OIDC_CLIENT_IDENTIFIER

# Session keys used to thread per-form values across the OIDC dance
# (start_login → token exchange → callback → handle_return).
SESSION_FORM_CLIENT_ID_KEY = "verid_oidc_form_client_id"
SESSION_FORM_CLIENT_SECRET_KEY = "verid_oidc_form_client_secret"
SESSION_OIDC_CLIENT_IDENTIFIER_KEY = "verid_oidc_active_client_identifier"
