# The Ver.iD OIDC plugin keeps no application-owned models. All persistent
# state lives in `mozilla_django_oidc_db.OIDCClient` rows (one per Ver.iD
# disclosure flow); per-form configuration lives on the form authentication
# backend options.
