# 18 - Security Architecture

## Trust boundaries

- browser/user to Filament Manager
- Filament Manager to canonical PostgreSQL
- Filament Manager to the distinct Spoolman API service
- Spoolman to its PostgreSQL database
- Moonraker/Fluidd to Spoolman
- Filament Manager to Google APIs
- Filament Manager browser, API, and worker to optional Bugsnag SaaS endpoints
- outbound-only Cura workstation agents to Filament Manager
- future scale/NFC devices to Filament Manager

## Database isolation

- separate databases and owners
- separate database credentials and scoped service environments
- SCRAM authentication
- `pg_hba.conf` limited to Swarm node addresses
- explicit non-SSL connections limited to the dedicated isolated database network
- no cross-database grants
- no direct Filament Manager queries against Spoolman tables
- distinct connection limits and monitoring labels

## Spoolman exposure

Spoolman has no built-in authentication. Therefore:

- do not expose port `7912` to the public internet
- allow only printer, management, and trusted LAN networks
- use authenticated reverse-proxy access for remote browser use
- set precise `SPOOLMAN_CORS_ORIGIN` values rather than `*`
- do not rely on CORS as authentication

## Service network

`filament-services` is an internal integration network created by the combined stack. It is external only in the optional independent-stack layout. Only services that need Spoolman integration should join it.

## Credentials

- use ordinary Docker stack environment variables during the current testing phase
- never commit credentials
- keep populated `.env` files at mode `0600` and restrict Swarm-manager and Portainer access
- never hardcode passwords directly in stack YAML or print rendered stack/service specifications into logs
- rotate Spoolman and Filament Manager database credentials independently
- prevent secrets from appearing in logs, exceptions, metrics, or Google Sheet output
- keep Bugsnag default-off, accept only its SDK API key at runtime, confine its separate Upload API key to authorized CI, and never place a personal authentication token in either location

Environment variables are intentionally transitional and are visible to authorized Docker/Portainer operators. Move them to an approved secret store when the deployment policy changes.

## External error and performance reporting

Optional Bugsnag reporting preserves a strict minimum-disclosure boundary. A final delivery callback replaces raw exception messages and removes private origins, query strings, request/response bodies and headers, user/session identity, page attributes, hostnames, submitted values, arbitrary metadata, credentials, and external response bodies. Browser routes are normalized, distributed trace propagation is disabled, high-frequency polling spans are discarded, and repeating worker failures are throttled. Only terminal outbox failures are externally reported. Exact Bugsnag delivery hosts enter the browser Content Security Policy only for enabled features; local Diagnostics and structured logs remain canonical.

Hidden browser source maps may leave CI only during an authorized direct push with the `BUGSNAG_UPLOAD_API_KEY` repository secret configured. Pull requests do not upload maps, and runtime images never contain them.

## API safety

- authenticate Filament Manager writes
- support exactly one active local Administrator account
- on an empty database create `admin` / `admin`, store only its Argon2id hash, and restrict it to password replacement/logout until it chooses a normal 10-256 character password
- preserve an existing single account on upgrade, revoke other sessions after identity/password edits, and fail startup instead of silently choosing among multiple legacy accounts
- use request IDs and audit logs
- validate all Spoolman payloads
- preserve unknown Spoolman `extra` fields
- protect against SSRF by allowing only configured Spoolman and Moonraker endpoints
- bound and sanitize every printer-side material GUID, Spoolman ID, prompt label, temperature, and catalog size before embedding it in G-code
- treat requested spools as untrusted future targets; only a completed physical macro boundary may change active Spoolman identity
- fail closed when Cura material identity, eligible inventory, current exact-profile temperature, or persistent physical-spool state is unavailable
- accept managed Cura setting edits only for deterministic known GUIDs and approved bounded keys; derive the idempotency checksum server-side, save the known current settings directly, and reject new Cura-created materials as canonical input
- accept Cura recovery snapshots only from the paired agent for its exact currently reported installation/version; enforce fixed target allowlists, bounded content, semantic checksums, reset detection, and conservative credential/endpoint/path filtering
- expose only recovery metadata to authenticated browser users, require Administrator confirmation to queue a restore, require an exact target Cura-version match, and lease the copied restore payload only to the selected paired target agent

The exact first-install password is intentionally weak at the owner's request for this single-user self-hosted deployment. Mandatory first-login replacement, normal Argon2id storage, login throttling, and no deployment-variable credential exposure limit that accepted bootstrap risk. Do not broaden this exception to replacement passwords or remove the forced-change gate.

## Future device security

- unique device credentials
- signed or authenticated events
- timestamp and replay-window validation
- rate limits
- NFC UIDs treated only as identifiers, never authenticators

## Backup security

Backups of both databases must use the central backup platform's encryption and retention controls. Restore tests must occur in isolated environments with non-production secrets. Sanitized Cura recovery points reside inside the canonical database backup. Workstation-local pre-restore archives contain the local Cura files they replaced and must be protected as private user data; they are never uploaded as recovery snapshots.

## Authoritative implementation references

- Spoolman repository: https://github.com/Donkie/Spoolman
- Spoolman Docker installation: https://github.com/Donkie/Spoolman/wiki/Installation
- Spoolman configuration variables: https://github.com/Donkie/Spoolman/blob/master/.env.example
- Spoolman security guidance: https://github.com/Donkie/Spoolman/wiki/Security
- Spoolman REST API: https://donkie.github.io/Spoolman/
- Moonraker Spoolman configuration: https://moonraker.readthedocs.io/en/stable/configuration/#spoolman
- Fluidd Spoolman support: https://docs.fluidd.xyz/features/spoolman
- Google Sheets API: https://developers.google.com/workspace/sheets/api
- Docker Swarm stack deployment: https://docs.docker.com/engine/swarm/stack-deploy/
- PostgreSQL documentation: https://www.postgresql.org/docs/
