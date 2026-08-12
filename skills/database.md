# Database and Migration Skill

- PostgreSQL is required for development and tests that exercise persistence. SQLite is not a substitute.
- Use SQLAlchemy 2.x typed mappings and keep API schemas separate from ORM models.
- Use UUID primary keys, `TIMESTAMPTZ`, `NUMERIC`, `JSONB`, explicit foreign keys, and indexes that match query paths.
- Mutable canonical rows carry an integer `record_version`; HTTP updates require an expected version.
- Measurement, usage, audit, and accepted calibration results are append-only.
- Schema changes require an Alembic migration plus upgrade validation against disposable PostgreSQL.
- Physical build-plate identifiers use exact uppercase `P<number>` values, with `P1` through `P5` retained as initial seeds. Printable Side A uses the unsuffixed code and Side B uses lowercase `b`; `P4` and `P4b` belong to one physical P4 plate. Moonraker synchronization preserves physical and side metadata, tracks mesh availability per side, and never deletes a plate or side merely because its mesh is absent.
- Typed material-profile columns hold frequently used Cura values. Only keys in the approved Cura Material Settings catalog may enter `cura_extensions`; brand/type are derived metadata and published versions remain immutable.
- `filament_colors.normalized_name` is the unique NFKC/casefold identity for a color label. Its six-digit sample is canonical; matching `filament_products.color_hex` values are projection mirrors updated transactionally with audit and outbox work.
- `material_templates` are mutable printer/nozzle-scoped identities; `material_template_revisions` are complete immutable settings snapshots after publication. A new product copies a published revision into its own draft profile and records both product and profile provenance.
- Spool `location` is bounded free text. `location_authoritative` distinguishes an uninitialized legacy row from a deliberate canonical value or clear: adopt one non-empty Spoolman location only while false, then keep Filament Manager authoritative.
- Workers claim due outbox jobs with `FOR UPDATE SKIP LOCKED`. Singleton reconciliation and migration tasks use PostgreSQL advisory locks.
- Docker web and worker startup automatically runs `alembic upgrade head` while holding the stable application migration advisory lock. Keep the lock timeout bounded, never log the database URL, and fail closed on upgrade errors.
- Existing calibration sessions receive the dimensional step through migration. Historical published/cancelled sessions keep it as a non-required skipped record; active and ready sessions must complete it before publication.
- Database `filament_user` must never receive access to the `spoolman` database, and Spoolman credentials must never enter this application.
- The current remote-database contract explicitly disables PostgreSQL TLS for both applications because the database runs on a dedicated isolated network. Preserve SCRAM authentication, narrow `pg_hba.conf` rules, firewall isolation, and separate roles; never use this connection mode across an untrusted or shared network.
