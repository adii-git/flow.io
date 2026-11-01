# Deploying Flow.io

Tested by the author: the backend suite and the frontend build. Not tested by the author: the Docker images, Postgres migrations, the Celery worker, Caddy TLS. The CI file runs a Postgres migration check for you.

## Single server (any VM with Docker)
0. Needs Docker Compose 2.24 or newer (the prod file uses `!reset`).
1. Point a DNS A record for your domain at the server.
2. `cp .env.example .env`, then set `SECRET_KEY`, `FERNET_KEY`, `POSTGRES_PASSWORD`, `DOMAIN`, `COOKIE_SECURE=true`, `ALLOWED_ORIGINS=https://<domain>`, `ADMIN_EMAILS=<you>`.
3. `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`
4. Caddy obtains the TLS certificate automatically. Open `https://<domain>`.
5. Keep `EXECUTION_MODE=demo` until you have checked the flow, then set `live`, restart, and save provider keys in Tools.

## Before going live
- Back up `dbdata` (Postgres) and `uploads`. Keep `FERNET_KEY` safe: losing it makes saved provider keys unreadable. Rotating it needs a re-encryption step that is not built.
- Check `context_window` and model ids in `backend/app/registry/tools.json` against provider docs.
- The Python sandbox is not built, so code is delivered without being run.
- Rate limiting uses Redis; if Redis is down it falls back to per-process counting.
- Uploads live on a local volume; move to object storage before running more than one backend host.
