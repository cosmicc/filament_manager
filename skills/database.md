# Database and Migration Skill

- PostgreSQL is required for development and tests that exercise persistence. SQLite is not a substitute.
- Use SQLAlchemy 2.x typed mappings and keep API schemas separate from ORM models.
- Use UUID primary keys, `TIMESTAMPTZ`, `NUMERIC`, `JSONB`, explicit foreign keys, and indexes that match query paths.
- Mutable canonical rows carry an integer `record_version`; HTTP updates require an expected version.
- Measurement, usage, audit, and accepted calibration results are append-only.
- Schema changes require an Alembic migration plus upgrade validation against disposable PostgreSQL.
- Workers claim due outbox jobs with `FOR UPDATE SKIP LOCKED`. Singleton reconciliation and migration tasks use PostgreSQL advisory locks.
- Database `filament_user` must never receive access to the `spoolman` database, and Spoolman credentials must never enter this application.
- The current remote-database contract explicitly disables PostgreSQL TLS for both applications because the database runs on a dedicated isolated network. Preserve SCRAM authentication, narrow `pg_hba.conf` rules, firewall isolation, and separate roles; never use this connection mode across an untrusted or shared network.
