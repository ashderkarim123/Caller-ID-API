# Frequently Asked Questions (FAQ)

## General Questions

### What is this API for?

This API provides intelligent caller-ID rotation for VICIdial call centers. It dynamically assigns optimal caller-IDs to outbound calls based on area code matching, usage limits, and availability.

### Why do I need caller-ID rotation?

Caller-ID rotation helps:
- Prevent number blocking by carriers
- Improve answer rates with local area code matching
- Distribute call volume across multiple numbers
- Comply with calling regulations
- Track campaign performance

### Is this compatible with VICIdial?

Yes, this is specifically designed for VICIdial integration via Asterisk dialplan modifications.

## Installation Questions

### What are the system requirements?

- Ubuntu 24.04 LTS (or any Linux with Docker)
- Docker 20.10+
- Docker Compose 2.0+
- Minimum 4GB RAM
- 2+ CPU cores
- 20GB disk space

### Do I need Plesk?

No, Plesk is optional. It's recommended for easy reverse proxy and SSL management, but you can use nginx or Apache directly.

### Can I run this on a different OS?

Yes, as long as Docker is supported. Works on:
- Ubuntu/Debian
- CentOS/RHEL
- macOS (for development)
- Windows with WSL2

## Configuration Questions

### How do I change the admin token?

1. Edit `.env` file
2. Update `ADMIN_TOKEN=your_new_token`
3. Restart: `docker-compose restart api`

### How do I increase rate limits?

Edit `.env`:
```bash
DEFAULT_RATE_LIMIT_PER_AGENT=200  # requests per minute
DEFAULT_HOURLY_LIMIT=150          # per caller-ID
DEFAULT_DAILY_LIMIT=1000          # per caller-ID
```

Restart: `docker-compose restart api`

### Can I use a different database?

Currently only PostgreSQL is supported. MySQL/MariaDB support may be added in future versions.

### How do I change the API port?

Edit `docker-compose.yml`:
```yaml
ports:
  - "127.0.0.1:8080:8000"  # Change 8080 to your desired port
```

Restart: `docker-compose restart api`

## Operation Questions

### How do I add caller-IDs?

Three methods:

1. **Via API:**
```bash
curl -X POST "http://127.0.0.1:8000/add-number?caller_id=2125551234" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

2. **Via CSV import:**
```bash
python3 scripts/bulk_import.py --csv your_file.csv --method db
```

3. **Directly in database:**
```bash
docker exec -it callerid_postgres psql -U callerid_user -d callerid_db
INSERT INTO caller_ids (caller_id, area_code, hourly_limit, daily_limit, is_active)
VALUES ('2125551234', '212', 100, 500, 1);
```

### How long are caller-IDs reserved?

Default: 5 minutes (300 seconds)

Configurable via `DEFAULT_RESERVATION_TTL` in `.env`.

### What happens when a caller-ID hits its limit?

It's automatically skipped in the allocation algorithm until the limit resets (hourly/daily).

### How do I release stuck reservations?

**Via API:**
```bash
curl -X DELETE "http://127.0.0.1:8000/api/reservation/2125551234" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

**Via Redis:**
```bash
docker exec callerid_redis redis-cli DEL "reservation:2125551234"
```

### Can I disable specific caller-IDs?

Yes, update the database:
```sql
UPDATE caller_ids SET is_active = 0 WHERE caller_id = '2125551234';
```

Or directly in PostgreSQL:
```bash
docker exec -it callerid_postgres psql -U callerid_user -d callerid_db \
  -c "UPDATE caller_ids SET is_active = 0 WHERE caller_id = '2125551234';"
```

## VICIdial Integration Questions

### Where do I add the dialplan code?

Add to `/etc/asterisk/extensions_custom.conf` on your VICIdial server.

### Do I need to modify VICIdial code?

No, only Asterisk dialplan modifications are needed.

### What if the API is down?

The dialplan includes fallback logic to use default caller-ID if the API is unavailable.

### Can I test without VICIdial?

Yes, use the `/next-cid` endpoint directly:
```bash
curl "http://127.0.0.1:8000/next-cid?to=5555551234&campaign=test&agent=test"
```

## Performance Questions

### How many concurrent requests can it handle?

Default configuration: 100+ concurrent requests

With scaling: 500+ concurrent requests

### What's the average response time?

- `/next-cid`: < 50ms
- `/health`: < 10ms
- `/add-number`: < 100ms

### How do I scale for more traffic?

Increase API workers in `docker-compose.yml`:
```yaml
command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 8
```

Increase database connections in `.env`:
```bash
POSTGRES_MAX_CONNECTIONS=200
```

### Does it support clustering?

Not currently. Single-instance deployment only. Load balancing support planned for future versions.

## Troubleshooting Questions

### API returns "No available caller-IDs"

**Causes:**
1. No active caller-IDs in database
2. All caller-IDs are reserved
3. All caller-IDs hit usage limits

**Solutions:**
```bash
# Check active caller-IDs
make count-cids

# Check reservations
make active-reservations

# Add more caller-IDs
make import-sample
```

### API is not responding

```bash
# Check container status
docker-compose ps

# View logs
docker logs callerid_api

# Restart
docker-compose restart api
```

### Database connection errors

```bash
# Check database container
docker logs callerid_postgres

# Test connection
docker exec -it callerid_postgres psql -U callerid_user -d callerid_db

# Verify credentials in .env
cat .env | grep POSTGRES
```

### Redis connection errors

```bash
# Check Redis container
docker logs callerid_redis

# Test connection
docker exec -it callerid_redis redis-cli PING

# Should return: PONG
```

### Dashboard shows 403 Forbidden

Your admin token is incorrect. Check:
```bash
grep ADMIN_TOKEN .env
```

Use correct token in Authorization header:
```
Authorization: Bearer YOUR_ADMIN_TOKEN
```

### Caller-IDs not rotating (same number used repeatedly)

Check if you have multiple active caller-IDs:
```bash
make count-cids
```

The LRU algorithm requires multiple available caller-IDs to rotate effectively.

## Security Questions

### Is the API secure?

Yes, when properly configured:
- Bound to localhost (127.0.0.1)
- HTTPS via reverse proxy
- Token authentication for admin endpoints
- Input sanitization
- Rate limiting

### Should I expose port 8000 publicly?

**No!** Always use a reverse proxy (Plesk/nginx) with HTTPS. Port 8000 should only be accessible via localhost.

### How do I rotate the admin token?

1. Generate new token: `openssl rand -hex 32`
2. Update `.env` file
3. Restart: `docker-compose restart api`
4. Update any scripts/integrations using the old token

### Is the database encrypted?

Data at rest is not encrypted by default. For sensitive deployments:
1. Use encrypted volumes
2. Enable PostgreSQL SSL
3. Configure Redis with TLS

## Backup & Recovery Questions

### How do I backup my data?

```bash
# Automated backup
make backup

# Manual backup
docker exec callerid_postgres pg_dump -U callerid_user callerid_db > backup.sql
docker exec callerid_redis redis-cli SAVE
docker cp callerid_redis:/data/dump.rdb redis_backup.rdb
```

### How often should I backup?

Recommended:
- **Production**: Daily automated backups
- **High volume**: Multiple times per day
- **Development**: Weekly or as needed

### How do I restore from backup?

```bash
# Restore PostgreSQL
cat backup.sql | docker exec -i callerid_postgres psql -U callerid_user -d callerid_db

# Restore Redis
docker cp redis_backup.rdb callerid_redis:/data/dump.rdb
docker-compose restart redis
```

### Can I migrate to a new server?

Yes:
1. Backup database and Redis on old server
2. Install Docker on new server
3. Copy project files and `.env`
4. Restore database and Redis
5. Start services: `docker-compose up -d`

## Monitoring Questions

### How do I monitor API performance?

1. **Dashboard**: `https://dialer1.rjimmigrad.com/dashboard`
2. **Stats endpoint**: `curl http://127.0.0.1:8000/api/stats -H "Authorization: Bearer TOKEN"`
3. **Container stats**: `docker stats`
4. **Logs**: `docker logs -f callerid_api`

### What metrics should I track?

Important metrics:
- Response time (avg < 50ms)
- Active reservations
- Rate limit hits
- Caller-ID availability
- Database connections
- Redis memory usage

### How do I set up alerts?

Currently no built-in alerting. You can:
1. Monitor `/health` endpoint externally
2. Use Docker health checks
3. Set up custom monitoring (Prometheus, Grafana)
4. Parse logs with external tools

## Cost Questions

### Is this free?

Yes, the API is provided as-is. You only pay for:
- Server hosting
- Domain/SSL certificate (optional if using Let's Encrypt)

### What are the infrastructure costs?

Typical costs:
- **VPS/Server**: $10-50/month
- **Domain**: $10-15/year
- **SSL**: Free (Let's Encrypt) or $10-50/year

### Does it require a license?

Check the LICENSE file for usage terms.

## Development Questions

### Can I modify the code?

Yes, the code is modular and well-documented. Key files:
- `app/main.py` - API endpoints
- `app/models.py` - Database models
- `app/redis_client.py` - Redis operations
- `app/config.py` - Configuration

### How do I add new features?

1. Modify code in `app/` directory
2. Update requirements if needed
3. Rebuild: `docker-compose build`
4. Test: `docker-compose up -d`

### Is there a test suite?

Basic testing included. Expand as needed in `tests/` directory.

### Can I contribute?

Yes, contributions are welcome! Please follow:
1. Fork repository
2. Create feature branch
3. Test thoroughly
4. Submit pull request

## Support Questions

### Where can I get help?

1. Check documentation in `docs/`
2. Review logs: `docker logs callerid_api`
3. Test health endpoint: `/health`
4. Check dashboard for diagnostics

### How do I report bugs?

1. Check if issue is already known
2. Gather error logs
3. Document steps to reproduce
4. Submit issue with details

### Is commercial support available?

Check with the project maintainer for commercial support options.

---

**Don't see your question?** Check the full documentation:
- [README.md](../README.md)
- [DEPLOYMENT.md](DEPLOYMENT.md)
- [VICIDIAL_INTEGRATION.md](VICIDIAL_INTEGRATION.md)
- [API_REFERENCE.md](API_REFERENCE.md)
