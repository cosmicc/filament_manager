# Security and Authentication Skill

- Filament Manager uses local accounts with `administrator`, `operator`, and `viewer` roles.
- Store passwords with Argon2id. Never log passwords, session tokens, CSRF tokens, database URLs, API keys, or service-account documents.
- Browser authentication uses random server-side sessions in HttpOnly cookies. State-changing requests require a matching CSRF header.
- Session cookies are `Secure` in production, `SameSite=Strict`, path `/`, and have bounded absolute and idle expiration.
- Administrator: user management, settings, overrides, retries, and all operator actions.
- Operator: inventory, measurement, labels, active spool/plate, profiles, and calibration workflows.
- Viewer: authenticated read-only access.
- Validate proxy headers only when trusted-proxy mode is explicitly configured.
- Use exact allowed origins and hosts; wildcard production CORS is prohibited.
- Constrain outbound integration URLs to configured endpoints to reduce SSRF risk.
- Rate-limit login and future device-event endpoints. Audit denied administrative actions without sensitive request bodies.
- QR codes contain stable application URLs/identifiers only. NFC UIDs never grant access.
- Production images run as a non-root user and omit package-manager and build tooling from the runtime layer.
- Cura agents are outbound-only and run as the desktop user. Pairing codes are high-entropy, expire after ten minutes, work once, and are stored only as hashes.
- Store agent bearer tokens only as server-side hashes and private per-user workstation config. Never return them after pairing, accept them on browser routes, or include them in logs/audit metadata.
- Require HTTPS for non-loopback pairing and polling, do not follow redirects, and keep credentials scoped to heartbeat, claim, and completion routes.
- Cura writes require a detected root, symlink/root-escape checks, a closed Cura process, an exact machine/nozzle match, backup, checksum manifest, atomic replacement, and rollback. Never replace inherited unknown start G-code to automate pressure advance.
