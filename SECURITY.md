# Security Policy

## Supported version

Security fixes are applied to the current development release shown in `VERSION`.

## Production baseline

- Keep Filament Manager and Spoolman on trusted networks or behind authenticated reverse proxies.
- Use exact allowed origins and hosts; do not expose Spoolman's unauthenticated port to the public internet.
- Store credentials in Docker secrets and use separate SCRAM PostgreSQL roles.
- Restrict PostgreSQL access to approved Swarm nodes and prohibit cross-database grants.
- Bootstrap the first administrator with a secret file, then remove that secret after verification.
- Use HTTPS so session cookies can be marked Secure.
- Expose no workstation-agent port. Pair each agent only through the ten-minute single-use code flow over HTTPS, then revoke it from the web interface before decommissioning the workstation.
- Run the agent as the normal Cura desktop user, never root or Windows Administrator. Preserve its private per-user configuration permissions and automatic Cura backups.

## Reporting

Report suspected vulnerabilities privately with the affected version, deployment mode, reproduction steps, impact, and sanitized logs. Never include passwords, session cookies, API keys, service-account files, or raw database dumps.
