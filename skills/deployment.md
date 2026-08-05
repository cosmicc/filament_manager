# Deployment and Operations Skill

- Production uses stack `spoolman` and stack `filament-manager`; combined Compose is local development only.
- Both stacks join the pre-created external overlay `filament-services` and use distinct PostgreSQL databases, roles, secrets, migrations, backups, and lifecycles.
- Long-running Filament Manager services receive only `filament_manager_database_url`, Google, and Moonraker secrets. Only the one-shot bootstrap command receives the bootstrap password. Filament Manager must not mount `spoolman_db_password` or the PostgreSQL administrator credential.
- Moonraker uses the stable LAN Spoolman endpoint, never Swarm-only DNS.
- Pin tested image tags or digests. Spoolman uses one replica and stop-first updates. Filament Manager uses one replica until session and worker concurrency have been validated for scale-out.
- Run migrations as a distinct command before application rollout. Do not auto-migrate from every web replica.
- Local PostgreSQL bootstrap secrets remain `0600` on the host; the Compose entrypoint copies only database-role secrets into an ephemeral PostgreSQL-owned runtime directory before dropping privileges.
- Back up `filament_manager` and `spoolman` independently and perform isolated restore tests.
- Verify `/health/live`, `/health/ready`, `/metrics`, outbox depth, reconciliation lag, and publication lag after deployment.
- Apply the workstation-agent schema migration before enrollment. Install the agent per user on Arch Linux with the hardened systemd user unit or on Windows 11 with the limited per-user logon task.
- Verify agent last contact, Cura version/setting-version discovery, machine/nozzle matching, closed-Cura deferral, one successful deployment, manifest checksums, and rollback before relying on automated workstation updates.
