#!/usr/bin/env sh
set -eu

bootstrap_dir=/run/filament-manager-bootstrap
install -d -m 0700 -o postgres -g postgres "$bootstrap_dir"

for secret_name in filament_manager_db_password spoolman_db_password; do
  install \
    -m 0400 \
    -o postgres \
    -g postgres \
    "/run/secrets/$secret_name" \
    "$bootstrap_dir/$secret_name"
done

exec /usr/local/bin/docker-entrypoint.sh "$@"
