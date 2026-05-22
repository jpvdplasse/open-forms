"""
Local development settings for the Ver.iD self-hosted demo.

Extends ``ci.py`` and disables MFA for admin to make the first-test loop
fast. Do NOT use in production — anything past a local demo should require
proper MFA setup.
"""

from .ci import *  # noqa: F401,F403
from .ci import AUTHENTICATION_BACKENDS

# Allow any authentication backend to bypass MFA on the admin. This skips
# the OTP setup prompt right after first login.
MAYKIN_2FA_ALLOW_MFA_BYPASS_BACKENDS = list(AUTHENTICATION_BACKENDS)

# Ver.iD's token endpoint advertises `token_endpoint_auth_methods_supported: ["none"]`
# meaning it expects PKCE (S256) instead of a client_secret. Turn it on globally
# for this demo. Note: if you ever add an OIDC provider that does NOT support PKCE
# in the same Open Forms install, this flag will need to become per-client.
OIDC_USE_PKCE = True
OIDC_PKCE_CODE_CHALLENGE_METHOD = "S256"

# Demo default for the production Ver.iD tenant. Override (or set via the
# per-OIDCClient `options.verid_settings`) for non-production tenants.
OIDC_VERID_EXPECTED_ISS = "urn:ver-id:crypto:key@production:oauth/v1"
OIDC_VERID_EXPECTED_AUD = "urn:ver-id:crypto:key@external:*"

# Run Celery tasks synchronously in-process. Without this the demo would
# need a separate Celery worker for submission post-processing — form
# submissions hang on "processing" otherwise.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# allow_redirect_url() explicitly skips the wildcard in ALLOWED_HOSTS, so list
# the local hosts here so the auto-login flow's `next` URL is accepted.
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "*"]
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOWED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]
CSRF_TRUSTED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]
