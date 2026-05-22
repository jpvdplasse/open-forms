"""
Plugin for Ver.iD wallet authentication and attribute disclosure.

Website: https://ver.id/
Docs: https://docs.ver.id/
Studio: https://spas.nebula.ver.id/

Ver.iD is a decentralized identity / EUDI-wallet provider that exposes flows
as OAuth 2.1 clients. Each flow (authentication or disclosure) is registered
in Ver.iD Studio and acts as its own OIDC client. The attributes a flow returns
are part of the flow definition, not a runtime parameter — see the per-form
flow selection in this plugin's options.
"""
