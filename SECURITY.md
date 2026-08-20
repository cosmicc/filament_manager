# Security Policy

## Supported version

Security fixes are applied to the current development release shown in `VERSION`.

## Production baseline

- Keep Filament Manager and Spoolman on trusted networks or behind authenticated reverse proxies.
- Use exact allowed origins and hosts; do not expose Spoolman's unauthenticated port to the public internet.
- Use separate SCRAM PostgreSQL roles and unique credentials. Docker currently receives credentials through scoped stack environment variables, so strictly limit Swarm-manager and Portainer access and protect the untracked `.env` file with mode `0600`.
- Restrict PostgreSQL access to approved Swarm nodes and prohibit cross-database grants.
- PostgreSQL TLS is intentionally disabled on the dedicated isolated database network. Credentials and application data travel unencrypted, so never route that network through shared or untrusted infrastructure.
- On an empty database, sign in once with `admin` / `admin` and immediately complete the mandatory password change. The default is an accepted single-user bootstrap risk; never expose the application publicly before changing it.
- Use HTTPS so session cookies can be marked Secure.
- Expose no workstation-agent port. Pair each agent only through the ten-minute single-use code flow over HTTPS, then revoke it from the web interface before decommissioning the workstation.
- Run the agent as the normal Cura desktop user, never root or Windows Administrator. Preserve its private per-user configuration permissions and automatic Cura backups.
- Leave optional Bugsnag reporting disabled unless outbound SaaS monitoring is accepted. When enabled, use only the project SDK API key at runtime, keep the Upload API key and account-access tokens out of the application, and allow outbound HTTPS only to the exact Bugsnag notifier and key-specific performance hosts documented in `INSTALL.md`.

## Optional external monitoring

Bugsnag is an additional outbound trust boundary, not a replacement for Diagnostics or local structured logs. Its browser SDK key is necessarily visible to browser users and identifies the receiving project; it does not authorize account administration. The separate Upload API key remains confined to GitHub Actions source-map uploads. Deployment variables and the GitHub Actions secret must still be protected from casual disclosure and must never contain a personal authentication token.

Before delivery, Filament Manager replaces exception messages with generic class-based summaries, removes private origins and query strings, strips request/response bodies and headers, omits users, sessions, page attributes, hostnames, submitted values, credentials, and external response bodies, and limits metadata to an explicit operational allowlist. Browser routes are normalized, trace propagation is disabled, frequent polling performance spans are dropped, and recurring worker failures are throttled. Keep this sanitization and the default-disabled behavior intact when upgrading any Bugsnag package.

## Reporting

Report suspected vulnerabilities privately with the affected version, deployment mode, reproduction steps, impact, and sanitized logs. Never include passwords, session cookies, API keys, service-account files, or raw database dumps.
