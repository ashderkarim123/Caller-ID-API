# Caller-ID Rotation API

Async Caller-ID rotation service for VICIdial clusters. The stack uses FastAPI, async SQLAlchemy, PostgreSQL, Redis LRU caching, and Docker to provide secure, concurrency-safe caller ID allocation with admin tooling and deployment guidance for Ubuntu 24 + Plesk.

## Key Features
- LRU Caller-ID rotation backed by Redis with TTL reservations and per-agent rate limiting.
- Async PostgreSQL models for persistent caller ID metadata, reservations history, and dashboard stats.
- FastAPI endpoints (`/next-cid`, `/add-number`, `/dashboard`, `/health`) plus HTML admin dashboard (Jinja2).
- Dockerized stack (api/db/redis) listening only on `127.0.0.1`; expose externally through Plesk reverse proxy + SSL.
- Bulk CSV import script (API or direct DB) tested for 20k+ caller IDs.
- VICIdial/Asterisk dialplan snippet for direct integration.

## Project Layout
```
app/
  config.py        # Environment & settings
  main.py          # FastAPI entrypoint
  models.py        # SQLAlchemy ORM tables
  schemas.py       # Pydantic request/response models
  db.py            # Async engine + session helpers
  redis_client.py  # Shared aioredis connection
  services/        # Caller ID allocation logic
  templates/       # Dashboard (Jinja2)
  static/          # Dashboard assets
scripts/
  bulk_import.py   # CSV → API or DB importer
data/
  caller_ids_example.csv
Dockerfile
docker-compose.yml
.env.example
requirements.txt
```

## Prerequisites
- Ubuntu 24.04 LTS server with Plesk Obsidian installed
- Docker Engine + Docker Compose v2 (`apt install docker.io docker-compose-plugin`)
- Domain `dialer1.rjimmigrad.com` pointing to server IP

## Setup & Deployment
1. **Clone + configure**
   ```bash
   git clone <repo> caller-id-api && cd caller-id-api
   cp .env.example .env  # set strong secrets, database creds, IP whitelist
   ```
2. **Deploy stack**
   ```bash
   docker compose pull  # first-time base images
   docker compose up -d --build
   ```
   - API listens on `127.0.0.1:8000` inside Docker; Postgres on `127.0.0.1:5433`; Redis on `127.0.0.1:6380`.
   - Persistent volumes `postgres_data` + `redis_data` keep state across restarts.
3. **Health check**
   ```bash
   curl http://127.0.0.1:8000/health
   ```
   Expect `{ "status": "ok", ... }`.

## Plesk Reverse Proxy & SSL
1. In **Plesk → Domains → dialer1.rjimmigrad.com → Apache & nginx Settings**:
   - Enable *Proxy mode*.
   - Add custom nginx directives:
     ```nginx
     location / {
         proxy_pass http://127.0.0.1:8000/;
         proxy_set_header Host $host;
         proxy_set_header X-Real-IP $remote_addr;
         proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
         proxy_set_header X-Forwarded-Proto https;
     }
     ```
2. **SSL**: Use Plesk Let's Encrypt extension to issue a certificate for `dialer1.rjimmigrad.com`. Plesk automatically terminates HTTPS and forwards traffic to the Dockerized API over localhost.

## Environment Variables (see `.env.example`)
- `DATABASE_URL`, `POSTGRES_*`: Postgres creds (asyncpg format).
- `REDIS_URL`, `REDIS_PASSWORD`: Redis with password + AOF persistence.
- `ADMIN_TOKEN` and/or `JWT_SECRET`: Token for `/dashboard` + `/add-number`.
- `IP_WHITELIST`: Optional comma-separated IPs allowed for admin endpoints.
- `AGENT_RATE_LIMIT_PER_MIN`, `RESERVATION_TTL_SECONDS`, `CALLER_ID_COOLDOWN_SECONDS` tune allocation behavior.
- `ALLOWED_ORIGINS`: Comma-separated CORS domains.

## API Endpoints
| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/next-cid?to=<number>&campaign=<name>&agent=<id>` | Returns JSON with caller ID, TTL, limits, agent rate-limit remainder. Rate limited per agent and respects caller ID daily/hourly limits. |
| POST | `/add-number` (admin token) | Adds caller ID with optional carrier, area code, limits. |
| GET | `/dashboard` (admin token) | Renders HTML dashboard with pool stats, active reservations, campaign insights, recent API requests. |
| GET | `/health` | Reports Redis/DB status for monitoring.

All JSON endpoints respond with structured error payloads and log requests to Redis for dashboard display.

## Bulk Import (20k+ IDs)
Example CSV located at `data/caller_ids_example.csv` (`caller_id,carrier,area_code,daily_limit,hourly_limit`).

```bash
# Via API (preferred for validation)
python scripts/bulk_import.py --csv data/caller_ids_example.csv \
    --api-url http://127.0.0.1:8000 --admin-token $ADMIN_TOKEN --concurrency 50

# Direct DB (bypasses API, useful for seeding large sets)
python scripts/bulk_import.py --csv your.csv --mode db --batch 2000
```

## VICIdial / Asterisk Dialplan Snippet
Add to your carrier dialplan (replace token + domain as needed):

```
exten => _X.,1,NoOp(Fetching caller ID from rotation API)
 same => n,Set(URL=https://dialer1.rjimmigrad.com/next-cid?to=${EXTEN}&campaign=${VICIDIAL_campaign}&agent=${AGENT})
 same => n,Set(JSON={CURL(${URL})})
 same => n,GotoIf($["${JSON}" = ""]?backup)
 same => n,Set(CALLERID(num)=${CUT(JSON,",",1):15})  ; parse caller_id from JSON response
 same => n,Goto(continue)
 same => n(backup),Set(CALLERID(num)=18005550100)
 same => n(continue),Dial(SIP/${EXTEN}@yourgateway)
```
> Tip: use an AGI/AMI script to parse JSON cleanly (e.g., Perl/Python) and fall back gracefully if the API returns 404.

## Security Checklist
- API container bound to `127.0.0.1`; only exposed through Plesk HTTPS proxy.
- Admin endpoints require header `X-Admin-Token: <secret>` or JWT Bearer token.
- Optional IP whitelist for dashboard + management routes.
- Rate limiting per agent and per-caller ID (daily/hourly counters) backed by Redis TTL keys.
- Redis reservations stored with TTL to prevent double allocation; history persisted in Postgres.

## Maintenance & Operations
- **Logs**: Docker `api` container logs application output; `logs/` volume can be mounted to ship logs to Loki/ELK.
- **Database migrations**: Initial tables auto-created; integrate Alembic if future schema changes are required.
- **Health monitoring**: Hit `/health` via cron or monitoring service. Use `docker compose ps` for service states.
- **Backups**: Snapshot `postgres_data` and `redis_data` volumes or use managed backup jobs in Plesk/Docker.

## Testing
Run the API locally without Docker:
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # adjust to local DB/Redis
uvicorn app.main:app --reload
```

## Next Steps
- Connect VICIdial dialplan and verify `/next-cid` allocations under load (hundreds of agents supported via async Redis locks).
- Extend dashboard with per-carrier charts or integrate authentication with your SSO provider if desired.
