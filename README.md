# Caller-ID Rotation API

FastAPI-based caller-ID rotation platform designed for VICIdial call centers. The stack
ships with PostgreSQL, Redis, Docker, Plesk reverse-proxy guidance, and an admin
dashboard for monitoring usage.

## Features

- Async FastAPI (Python 3.11) with PostgreSQL + SQLAlchemy + asyncpg
- Redis-backed LRU rotation, TTL reservations, and per-agent rate limits
- Admin dashboard with Jinja2 templates and token/IP protection
- Bulk CSV importer for 20k+ caller IDs
- Docker Compose deployment that binds FastAPI to `127.0.0.1:8000` for Plesk proxying
- Health endpoint, structured logging, and VICIdial dialplan snippet

## Project Layout

```
.
├── app/
│   ├── main.py              # FastAPI entrypoint
│   ├── config.py            # Environment-based settings
│   ├── db.py / models.py    # Async SQLAlchemy setup
│   ├── redis_client.py      # Redis helper
│   ├── services/            # Caller-ID allocation logic
│   ├── templates/           # Admin dashboard
│   └── static/              # Dashboard assets
├── scripts/bulk_import.py   # CSV → API importer
├── data/caller_ids_example.csv
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## Getting Started

1. **Copy and edit environment variables**

   ```bash
   cp .env.example .env
   # edit .env with secure passwords and tokens
   ```

2. **Build and run via Docker Compose**

   ```bash
   docker compose build
   docker compose up -d
   docker compose logs -f api
   ```

3. **Verify health**

   ```bash
   curl http://127.0.0.1:8000/health
   ```

## Bulk Importing Caller IDs

```
python scripts/bulk_import.py data/caller_ids_example.csv --token <ADMIN_TOKEN> --api http://127.0.0.1:8000
```

- CSV columns: `caller_id, carrier, area_code, daily_limit, hourly_limit`
- Script defaults to 20 concurrent uploads; tune via `--concurrency`.

## API Endpoints

| Endpoint | Method | Notes |
| --- | --- | --- |
| `/next-cid?to=15551234567&campaign=USA&agent=1001` | GET | Returns JSON containing `caller_id`, `expires_at`, `campaign`, and `agent`. Enforces Redis-backed rate limits. |
| `/add-number` | POST | Admin-only. Body matches `CallerIDCreate` schema. Requires `X-Admin-Token` header and optional IP whitelist. |
| `/dashboard` | GET | Jinja2 dashboard summarizing caller IDs, reservations, campaign usage, and last API requests. Requires admin token/IP. |
| `/health` | GET | Lightweight health probe used by Docker and external monitors. |

All non-dashboard endpoints return JSON. Dashboard assets are served from `/static`.

## Security Checklist

- API container only exposes `127.0.0.1:8000`; publish externally via Plesk reverse proxy.
- Admin endpoints (`/add-number`, `/dashboard`) require `X-Admin-Token`.
- Optional IP whitelist via `ALLOWED_ADMIN_IPS` (comma-separated).
- Redis-enforced per-agent rate limits (`AGENT_RATE_LIMIT_PER_MINUTE`).
- JWT integration can be added later if rotating secrets are required.

## Plesk Reverse Proxy (Ubuntu 24)

1. In Plesk, create the domain `dialer1.rjimmigrad.com`.
2. Go to **Apache & nginx Settings → Additional nginx directives** and add:

   ```
   location / {
       proxy_pass http://127.0.0.1:8000;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       proxy_set_header X-Forwarded-Proto https;
   }
   ```

3. Request/renew a Let’s Encrypt certificate under **SSL/TLS Certificates** (Plesk automates renewal).
4. Confirm `https://dialer1.rjimmigrad.com/health` returns the JSON payload.

## VICIdial / Asterisk Dialplan Snippet

```asterisk
exten => _X.,1,NoOp(Fetching Caller ID from Rotation API)
 same => n,Set(CID_API_URL=https://dialer1.rjimmigrad.com/next-cid?to=${EXTEN}&campaign=${VICIDIAL_campaign}&agent=${AGENT})
 same => n,Set(API_RESPONSE=${CURL(${CID_API_URL})})
 same => n,Set(CALLER_JSON=${JSON_DECODE(API_RESPONSE)})
 same => n,Set(CALLERID(num)=${JSON_GET(CALLER_JSON,caller_id)})
 same => n,Return()
```

- Requires `res_curl` and `res_json` modules. Replace `${AGENT}` with the channel variable you use to track the live agent.

## Maintenance & Operations

- **Logs**: `docker compose logs -f api` shows FastAPI logs; Postgres/Redis logs via their service names.
- **Backups**: volumes `postgres-data`, `redis-data` hold persistent state (`/var/lib/docker/volumes/...`). Snapshot via `docker run --rm -v ...`.
- **Scaling**: Run multiple API containers behind Plesk; each instance reads shared Postgres/Redis state. Keep `ADMIN_API_TOKEN` consistent across replicas.

## Troubleshooting

- 429 responses: Increase `AGENT_RATE_LIMIT_PER_MINUTE` or troubleshoot abusive agents.
- Empty dashboard: Ensure caller IDs are imported and Redis warmed (restart API container).
- SSL errors: Verify Plesk-provided certificate and that proxy headers include `X-Forwarded-Proto`.

## Development Notes

- Run `uvicorn app.main:app --reload` for local development outside Docker.
- Use `scripts/bulk_import.py` against `http://localhost:8000`.
- Linting/tests can be added with your preferred tooling; the service currently focuses on deployment readiness.
