FROM node:22-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build && find dist -type f -name '*.map' -delete

FROM python:3.12-slim-trixie AS python-build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ src/
RUN python -m pip wheel --wheel-dir /wheels .

FROM python:3.12-slim-trixie AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates curl \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl --fail --show-error --silent \
        --output /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
        https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && printf '%s\n' \
        'Types: deb' \
        'URIs: https://apt.postgresql.org/pub/repos/apt' \
        'Suites: trixie-pgdg' \
        'Components: main' \
        'Signed-By: /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc' \
        > /etc/apt/sources.list.d/pgdg.sources \
    && apt-get update \
    && apt-get install --yes --no-install-recommends postgresql-client-18 \
    && apt-get purge --yes --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd --gid 10001 filament-manager && useradd --uid 10001 --gid 10001 --create-home filament-manager
WORKDIR /app
COPY --from=python-build /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/* \
    && python -m pip uninstall --yes pip setuptools wheel \
    && rm -rf /wheels
COPY alembic.ini /app/alembic.ini
COPY migrations/ /app/migrations/
COPY --from=frontend-build /build/frontend/dist /app/static
RUN mkdir -p /data && chown -R filament-manager:filament-manager /data /app
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 CMD ["python", "-m", "filament_manager.healthcheck"]
ENTRYPOINT ["filament-manager-startup"]
CMD ["filament-manager"]
