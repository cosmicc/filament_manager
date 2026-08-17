# 20 - Operations Runbook

## Routine checks

### Spoolman service

```bash
docker stack services filament-manager
docker service ps filament-manager_spoolman
docker service logs --since 30m filament-manager_spoolman
```

Check:

- API health
- central PostgreSQL connectivity
- published port `7912`
- Moonraker connection status
- disk/log volume availability
- image version and pending upstream release review

### Filament Manager services

```bash
docker stack services filament-manager
docker service ps filament-manager_web
docker service logs --since 30m filament-manager_web
docker service logs --since 30m filament-manager_worker
```

Check:

- canonical database connectivity
- Spoolman reconciliation lag
- outbox queue depth
- Google publication status
- Moonraker reachability

Use the application **Diagnostics** page as the consolidated status surface for running/latest version, connections, synchronization freshness, worker heartbeats, projection queues, bounded recent errors, recovery validation, and safe projection rebuilding. **Download log** saves the same current bounded overview as a non-cacheable sanitized text file; it is an operational summary, not raw application or database output. The version lookup uses the fixed public GitHub releases API, includes non-draft testing releases, is cached for 15 minutes, and never returns an upstream response body. Integrations remains a configuration/ownership guide rather than a duplicate live-status dashboard.

Canonical mutations normally begin Spoolman projection within one worker polling cycle. The default one-minute full sweep imports usage before repairing every canonical vendor, filament, and spool. Normalize remote remaining weight to canonical three-decimal gram precision before comparing or recording usage so additional source precision cannot generate a duplicate event. The 15-second Moonraker state job treats the initialized macro's last completed physical boundary as authority, turns valid direct non-null selections in safe selection phases into guarded Fluidd targets, restores the physical active ID until confirmation, refreshes the bounded Cura/manual-load spool catalog, and aligns plate state; the 5-minute printer-information job refreshes sanitized discovered fields. A failed live print capture must reload transaction-expired printer state before continuing supported history reconciliation. Confirm the Diagnostics Spoolman check reports both API and managed-field readiness, and confirm recent `spoolman.reconcile.full`, `moonraker.state.reconcile`, and `moonraker.printer_info.reconcile` jobs complete. Structured web and worker logs include safe request, scheduler, job, and synchronization diagnostics with correlation IDs but never credentials or external response bodies.

### Physical spool workflow

- Keep `integrations/klipper/filament-manager-macros.cfg` included last and Fluidd's independent print-start spool selector disabled.
- `FILAMENT_MANAGER_SPOOL_STATE` must report the physically loaded ID or no spool. Do not manually invoke internal underscore-prefixed commit helpers.
- `unloading` retains the old ID; after physical unload the state becomes no spool. `inserting` and `loading` retain no spool; only a completed load sets the new ID.
- A ten-minute insertion timeout turns off the nozzle and preserves the last completed physical boundary. Use `FILAMENT_MANAGER_ABORT` to reset a workflow after a macro error without changing loaded-spool identity.
- Missing Cura print candidates require a current product material, an eligible projected spool, and a current exact printer/nozzle profile. A missing manual-load choice instead requires a projected non-empty spool and a safe temperature from its newest non-archived exact profile or linked in-scope template; manual loading does not require an exact print profile.

## Upgrade Spoolman

1. Review upstream release notes and migration warnings.
2. Confirm backup coverage of the `spoolman` database.
3. Pin the new tested Spoolman image in the exported stack variables.
4. Redeploy `docker-stack.yml` without changing the Filament Manager image.
5. Verify API health and Moonraker/Fluidd behavior.
6. Verify Filament Manager WebSocket reconnection and reconciliation.
7. Roll back the image and restore the database only if the upstream migration is not backward compatible.

## Upgrade Filament Manager

1. Back up `filament_manager`.
2. Run or verify migrations.
3. Redeploy `docker-stack.yml` with the new Filament Manager image and the existing Spoolman image.
4. Confirm Spoolman remained available throughout.
5. Check outbox and reconciliation backlog.

## Outage procedures

### Filament Manager unavailable

- Leave Spoolman and Moonraker running.
- Continue printing and collecting usage in Spoolman.
- Restore Filament Manager, then run inbound reconciliation.

### Spoolman unavailable

- Do not directly update its database.
- Restore the Spoolman service or database connectivity.
- Allow Filament Manager projection jobs to remain queued.
- Confirm Moonraker reconnects and reconcile missed usage.

### Stack overlay missing

```bash
docker stack deploy -c docker-stack.yml filament-manager
```

The combined stack recreates its missing overlay. Verify internal DNS and API health after its services reattach. For the optional independent-stack layout, recreate the external overlay and redeploy both stacks.

### Central PostgreSQL unavailable

Treat each database independently during diagnosis. Do not broaden grants or reuse the other application's credentials as a shortcut.

## Backup checks

- both databases included in backup sets
- last successful backup and WAL archive time
- periodic isolated restore
- configuration and private stack-variable inventory current
- Google Sheet not counted as backup

Run read-only application recovery validation from Diagnostics or with:

```bash
filament-manager-cli verify
```

After an isolated restore or external projection loss, queue complete reconstructable projection work from Diagnostics or with:

```bash
filament-manager-cli rebuild-projections --confirm
```

This command does not restore PostgreSQL and does not rewrite canonical business records.

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
