FROM node:22-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS python-build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ src/
RUN python -m pip wheel --wheel-dir /wheels .

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
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
