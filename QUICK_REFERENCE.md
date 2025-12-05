# Quick Reference Guide

## Common Commands

### Docker Management

```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# View logs
docker compose logs -f api
docker compose logs -f db
docker compose logs -f redis

# Restart a service
docker compose restart api

# Rebuild after code changes
docker compose build api
docker compose up -d api
```

### Database Operations

```bash
# Connect to database
docker compose exec db psql -U callerid_user -d callerid_db

# Count caller-IDs
docker compose exec db psql -U callerid_user -d callerid_db -c "SELECT COUNT(*) FROM caller_ids;"

# List all caller-IDs
docker compose exec db psql -U callerid_user -d callerid_db -c "SELECT caller_id, carrier, area_code, is_active FROM caller_ids LIMIT 10;"

# Backup database
docker compose exec db pg_dump -U callerid_user callerid_db > backup_$(date +%Y%m%d).sql

# Restore database
docker compose exec -T db psql -U callerid_user callerid_db < backup_20240101.sql
```

### Redis Operations

```bash
# Connect to Redis
docker compose exec redis redis-cli -a YOUR_REDIS_PASSWORD

# List all reservations
docker compose exec redis redis-cli -a YOUR_REDIS_PASSWORD KEYS "reservation:*"

# Clear all reservations (emergency)
docker compose exec redis redis-cli -a YOUR_REDIS_PASSWORD FLUSHDB

# Check Redis info
docker compose exec redis redis-cli -a YOUR_REDIS_PASSWORD INFO stats
```

### Import Caller-IDs

```bash
# Using helper script
./scripts/import_csv.sh /path/to/caller_ids.csv

# Direct method
docker compose cp caller_ids.csv api:/tmp/caller_ids.csv
docker compose exec api python bulk_import.py /tmp/caller_ids.csv

# Via API (single)
curl -X POST "https://dialer1.rjimmigrad.com/add-number" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"caller_id":"5551234567","carrier":"Verizon","area_code":"555","daily_limit":1000,"hourly_limit":100}'
```

### API Testing

```bash
# Health check
curl http://127.0.0.1:8000/health
curl https://dialer1.rjimmigrad.com/health

# Get next caller-ID
curl "https://dialer1.rjimmigrad.com/next-cid?to=5559876543&campaign=TEST&agent=AGENT001"

# Add caller-ID
curl -X POST "https://dialer1.rjimmigrad.com/add-number" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"caller_id":"5551234567","carrier":"Verizon","area_code":"555"}'

# Access dashboard
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  https://dialer1.rjimmigrad.com/dashboard

# Get API stats (JSON)
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  https://dialer1.rjimmigrad.com/api/stats
```

### Troubleshooting

```bash
# Check container status
docker compose ps

# Check if API is listening
netstat -tlnp | grep 8000
curl http://127.0.0.1:8000/health

# Check recent API requests
docker compose exec db psql -U callerid_user -d callerid_db \
  -c "SELECT * FROM api_requests ORDER BY created_at DESC LIMIT 10;"

# Check for errors in logs
docker compose logs api | grep -i error

# Restart everything
docker compose down
docker compose up -d
```

## Environment Variables

Key variables in `.env`:

- `DB_PASSWORD` - PostgreSQL password
- `REDIS_PASSWORD` - Redis password
- `ADMIN_TOKEN` - Admin authentication token
- `JWT_SECRET_KEY` - JWT signing key
- `RESERVATION_TTL_SECONDS` - Reservation timeout (default: 300)
- `DEFAULT_DAILY_LIMIT` - Default daily limit (default: 1000)
- `DEFAULT_HOURLY_LIMIT` - Default hourly limit (default: 100)

## File Locations

- Configuration: `/opt/callerid-api/.env`
- Logs: `docker compose logs`
- Database data: Docker volume `callerid-api_postgres_data`
- Redis data: Docker volume `callerid-api_redis_data`
- Application code: `/opt/callerid-api/app/`

## Ports

- API: `127.0.0.1:8000` (internal only)
- PostgreSQL: `127.0.0.1:5432` (internal only)
- Redis: `127.0.0.1:6379` (internal only)
- External: `https://dialer1.rjimmigrad.com` (via Plesk reverse proxy)

## URLs

- API Base: `https://dialer1.rjimmigrad.com`
- Health Check: `https://dialer1.rjimmigrad.com/health`
- Dashboard: `https://dialer1.rjimmigrad.com/dashboard`
- Next CID: `https://dialer1.rjimmigrad.com/next-cid?to=...&campaign=...&agent=...`

## VICIdial Dialplan Snippet

```ini
exten => _X.,1,Set(API_URL=https://dialer1.rjimmigrad.com/next-cid?to=${EXTEN}&campaign=${VICIDIAL_campaign}&agent=${AGENT})
exten => _X.,n,Set(API_RESPONSE=${CURL(${API_URL})})
exten => _X.,n,Set(CID_NUMBER=${FILTER(0-9,${JSON_DECODE(${API_RESPONSE},caller_id)})})
exten => _X.,n,GotoIf($["${CID_NUMBER}" = ""]?cid_fallback)
exten => _X.,n,Set(CALLERID(num)=${CID_NUMBER})
exten => _X.,n(cid_fallback),Set(CALLERID(num)=${VICIDIAL_callerid})
exten => _X.,n,Dial(${TRUNK}/${EXTEN},,tTo)
```

## Emergency Procedures

### API Not Responding

```bash
docker compose restart api
docker compose logs -f api
```

### Database Issues

```bash
docker compose restart db
docker compose logs -f db
docker compose exec db psql -U callerid_user -d callerid_db -c "SELECT 1;"
```

### Redis Issues

```bash
docker compose restart redis
docker compose logs -f redis
docker compose exec redis redis-cli -a YOUR_REDIS_PASSWORD ping
```

### Clear All Reservations

```bash
docker compose exec redis redis-cli -a YOUR_REDIS_PASSWORD FLUSHDB
```

### Reset Everything

```bash
docker compose down -v  # WARNING: Deletes all data!
docker compose up -d
```

---

For detailed information, see:
- [README.md](README.md) - Project overview
- [DEPLOYMENT.md](DEPLOYMENT.md) - Complete deployment guide
- [VICIDIAL_INTEGRATION.md](VICIDIAL_INTEGRATION.md) - VICIdial integration
