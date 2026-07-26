#!/bin/sh
# Container entrypoint: materialize GCP creds -> migrate -> serve.
set -e

# Railway has no file mounts: the service-account key arrives as an env var
# (GOOGLE_APPLICATION_CREDENTIALS_JSON) and is written to tmpfs for ADC.
# Never bake this into the image or the repo.
if [ -n "$GOOGLE_APPLICATION_CREDENTIALS_JSON" ] && [ -z "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
  printf '%s' "$GOOGLE_APPLICATION_CREDENTIALS_JSON" > /tmp/gcp-sa.json
  export GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcp-sa.json
fi

# Idempotent; safe on every boot. Single instance only (see HANDOFF: the
# token-store cache is not multi-instance coherent yet).
python -m alembic upgrade head

# --proxy-headers: Railway terminates TLS at its proxy; without this every
# request's client IP is the proxy's, which would make the /auth/imap
# per-IP brute-force throttle effectively global. Only the proxy can reach
# the container, so trusting forwarded headers from any peer is safe here.
exec uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 \
  --proxy-headers --forwarded-allow-ips '*'
