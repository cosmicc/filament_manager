# Deployment and Operations Skill

- The default production deployment uses root `docker-stack.yml` for Spoolman, Filament Manager web, and the worker. It assumes remote PostgreSQL and creates its overlay network and application data volumes.
- The independent `docker/spoolman-stack.yml` and `docker/filament-manager-stack.yml` files remain supported when separate application lifecycle boundaries are required.
- In either deployment, use distinct PostgreSQL databases, roles, credentials, migrations, and backups. A combined application stack never authorizes cross-database access.
- Docker deployments do not mount an application configuration file. All deployer-supplied addresses, one-printer Moonraker settings, integration settings, operational tuning, and credentials come from stack environment variables; fixed invariants remain application defaults.
- Docker credentials currently use ordinary stack environment variables rather than Docker secrets. Keep populated `.env` files untracked and `0600`, restrict Swarm-manager and Portainer access, and document that service specifications expose environment values to authorized operators.
- Long-running Filament Manager services receive only the canonical database URL, Google credential, and Moonraker API key variables. Only the one-shot bootstrap command receives the bootstrap password. Filament Manager must not receive the Spoolman database password or PostgreSQL administrator credential.
- Moonraker uses the stable LAN Spoolman endpoint, never Swarm-only DNS.
- The current Docker variable contract supports one Moonraker printer. `MOONRAKER_WEBSOCKET_URL` may be empty so the application derives `/websocket` from `MOONRAKER_BASE_URL`.
- Pin tested image tags or digests. Spoolman uses one replica and stop-first updates. Filament Manager uses one replica until session and worker concurrency have been validated for scale-out.
- After CI passes for `main`, `publish-swarm-image.yml` publishes AMD64 and ARM64 Filament Manager images with `latest` plus an immutable `sha-<commit>` tag. Use `latest` only for testing and pin the SHA tag or digest for production. Package publication remains separate from Git tagging and GitHub Releases.
- Run migrations as a distinct one-shot job before application rollout. Do not auto-migrate from every web replica.
- Local Compose passes separate database-role variables only to PostgreSQL initialization and the service that owns each role. Never reuse the PostgreSQL administrator password for an application role.
- Back up `filament_manager` and `spoolman` independently and perform isolated restore tests.
- Verify `/health/live`, `/health/ready`, `/metrics`, outbox depth, reconciliation lag, and publication lag after deployment.
- Apply the workstation-agent schema migration before enrollment. Install the agent per user on Arch Linux with the hardened systemd user unit or on Windows 11 with the limited per-user logon task.
- Verify agent last contact, Cura version/setting-version discovery, machine/nozzle matching, closed-Cura deferral, one successful deployment, manifest checksums, and rollback before relying on automated workstation updates.
