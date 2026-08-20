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

## Reporting

Report suspected vulnerabilities privately with the affected version, deployment mode, reproduction steps, impact, and sanitized logs. Never include passwords, session cookies, API keys, service-account files, or raw database dumps.
