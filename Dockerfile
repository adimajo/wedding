# syntax=docker/dockerfile:1
# Base images are pinned by digest; dependabot proposes updates (see .github/dependabot.yml).
FROM ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 AS uv

FROM python:3.12-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
# --locked: fail instead of re-resolving if uv.lock does not match pyproject.toml
RUN uv sync --locked --no-dev --no-install-project

FROM python:3.12-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=bigday.settings \
    DB_PATH=/data/db.sqlite3 \
    STATIC_ROOT=/app/static_root \
    SITE_CONTENT_DIR=/content
# 568 is the "apps" user of TrueNAS SCALE, so dataset permissions line up out of the box.
RUN groupadd --gid 568 app && useradd --uid 568 --gid 568 --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data /content /app/static_root && chown app:app /data /app/static_root
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --chown=app:app manage.py ./
COPY --chown=app:app bigday ./bigday
COPY --chown=app:app guests ./guests
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod 0555 /entrypoint.sh
USER app
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"
ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "bigday.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", \
     "--access-logfile", "-", "--error-logfile", "-", "--no-control-socket"]
