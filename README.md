# Caller-ID Rotation API for VICIdial

A complete, production-ready Caller-ID Rotation API system for VICIdial call centers. This system automatically rotates caller-IDs for outbound calls based on LRU (Least Recently Used) algorithm, rate limits, and area code matching.

## Features

- ✅ **Automatic Caller-ID Rotation** - LRU-based rotation with concurrency-safe reservations
- ✅ **Rate Limiting** - Per caller-ID daily and hourly limits
- ✅ **Area Code Matching** - Automatically matches caller-IDs to destination area codes
- ✅ **Real-Time Dashboard** - Admin dashboard with live statistics
- ✅ **High Performance** - Async PostgreSQL and Redis for hundreds of concurrent agents
- ✅ **Dockerized** - Complete Docker Compose setup for easy deployment
- ✅ **Secure** - JWT authentication, admin tokens, and secure defaults
- ✅ **VICIdial Integration** - Ready-to-use Asterisk dialplan snippets
- ✅ **Bulk Import** - Import thousands of caller-IDs via CSV
- ✅ **Production Ready** - Error handling, logging, health checks

## Quick Start

### 1. Clone and Configure

```bash
git clone <repository-url>
cd callerid-api
cp .env.example .env
nano .env  # Edit with secure passwords
```

### 2. Deploy with Docker

```bash
docker compose up -d
```

### 3. Verify

```bash
curl http://127.0.0.1:8000/health
```

### 4. Import Caller-IDs

```bash
docker compose exec api python bulk_import.py /app/example_caller_ids.csv
```

### 5. Access Dashboard

Visit: `https://your-domain.com/dashboard` (after configuring Plesk reverse proxy)

## Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration management
│   ├── db.py                # Database connection
│   ├── models.py            # SQLAlchemy models
│   ├── redis_client.py      # Redis client and reservations
│   ├── utils.py             # Caller-ID rotation logic
│   ├── auth.py              # Authentication utilities
│   └── templates/
│       └── dashboard.html   # Admin dashboard template
├── Dockerfile               # API container definition
├── docker-compose.yml       # Multi-container setup
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variables template
├── bulk_import.py           # CSV import script
├── example_caller_ids.csv   # Example caller-ID data
├── DEPLOYMENT.md            # Complete deployment guide
├── VICIDIAL_INTEGRATION.md  # VICIdial integration guide
└── README.md                # This file
```

## API Endpoints

### `GET /next-cid`
Get the next available caller-ID for a call.

**Parameters:**
- `to` (required): Destination phone number
- `campaign` (required): Campaign name
- `agent` (required): Agent name/ID

**Example:**
```bash
curl "https://dialer1.rjimmigrad.com/next-cid?to=5559876543&campaign=TEST&agent=AGENT001"
```

**Response:**
```json
{
  "caller_id": "5551234567",
  "carrier": "Verizon",
  "area_code": "555",
  "meta": {}
}
```

### `POST /add-number`
Add a new caller-ID to the system (requires admin token).

**Headers:**
```
Authorization: Bearer YOUR_ADMIN_TOKEN
Content-Type: application/json
```

**Body:**
```json
{
  "caller_id": "5551234567",
  "carrier": "Verizon",
  "area_code": "555",
  "daily_limit": 1000,
  "hourly_limit": 100,
  "meta": {"state": "CA", "type": "mobile"}
}
```

### `GET /dashboard`
Admin dashboard (requires admin token).

**Headers:**
```
Authorization: Bearer YOUR_ADMIN_TOKEN
```

### `GET /health`
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "redis": "ok",
  "timestamp": "2024-01-01T12:00:00.000000"
}
```

## Configuration

All configuration is done via environment variables in `.env`:

```env
# Database
DB_USER=callerid_user
DB_PASSWORD=your_secure_password
DB_NAME=callerid_db

# Redis
REDIS_PASSWORD=your_redis_password

# Security
ADMIN_TOKEN=your_admin_token
JWT_SECRET_KEY=your_jwt_secret

# API Settings
DEBUG=false
LOG_LEVEL=INFO
RESERVATION_TTL_SECONDS=300
DEFAULT_DAILY_LIMIT=1000
DEFAULT_HOURLY_LIMIT=100
```

## How It Works

1. **Request Flow:**
   - VICIdial/Asterisk calls `/next-cid` with destination number, campaign, and agent
   - API filters caller-IDs by area code, active status, and limits
   - Checks Redis for active reservations (concurrency safety)
   - Selects caller-ID using LRU algorithm
   - Reserves caller-ID in Redis with TTL
   - Updates database and returns caller-ID

2. **Reservation System:**
   - Each caller-ID is reserved for 5 minutes (configurable)
   - Prevents concurrent use of same caller-ID
   - Automatic expiration via Redis TTL

3. **Rate Limiting:**
   - Tracks daily and hourly usage per caller-ID
   - Uses Redis counters with automatic expiration
   - Prevents exceeding limits

4. **LRU Rotation:**
   - Tracks last-used timestamp in Redis sorted sets
   - Prefers least recently used caller-IDs
   - Ensures even distribution

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for complete deployment instructions including:
- Docker setup
- Plesk reverse proxy configuration
- SSL certificate setup
- Bulk import procedures
- Troubleshooting

## VICIdial Integration

See [VICIDIAL_INTEGRATION.md](VICIDIAL_INTEGRATION.md) for:
- Asterisk dialplan configuration
- AGI script examples
- Testing procedures
- Error handling

## Bulk Import

Import caller-IDs from CSV:

```bash
# Format: caller_id,carrier,area_code,daily_limit,hourly_limit,meta_json
docker compose exec api python bulk_import.py /app/your_caller_ids.csv
```

See `example_caller_ids.csv` for format.

## Monitoring

### Dashboard
Access the admin dashboard at `/dashboard` to view:
- All caller-IDs and their status
- Usage statistics (daily/hourly)
- Active reservations
- Campaign statistics
- Recent API requests

### Logs
```bash
# API logs
docker compose logs -f api

# Database logs
docker compose logs -f db

# Redis logs
docker compose logs -f redis
```

### Health Check
```bash
curl https://your-domain.com/health
```

## Security

- API binds to `127.0.0.1` (localhost only)
- Accessible only via Plesk reverse proxy
- Admin token required for management endpoints
- Rate limiting per agent and IP
- Secure password requirements
- HTTPS recommended for production

## Performance

- **Concurrency**: Supports hundreds of simultaneous agents
- **Database**: Async PostgreSQL with connection pooling
- **Cache**: Redis for fast reservations and usage tracking
- **Workers**: 4 uvicorn workers (configurable)

## Requirements

- Docker & Docker Compose
- Ubuntu 24.04 LTS (or compatible)
- Plesk (for reverse proxy)
- PostgreSQL 15+ (via Docker)
- Redis 7+ (via Docker)
- Python 3.11+ (in container)

## Troubleshooting

### API Not Responding
1. Check containers: `docker compose ps`
2. Check logs: `docker compose logs api`
3. Verify health: `curl http://127.0.0.1:8000/health`

### No Caller-IDs Available
1. Verify caller-IDs exist: Check database
2. Check limits: Review daily/hourly usage
3. Check reservations: `docker compose exec redis redis-cli KEYS "reservation:*"`

### Database Connection Issues
1. Check database container: `docker compose logs db`
2. Verify credentials in `.env`
3. Test connection: `docker compose exec db psql -U callerid_user -d callerid_db`

See [DEPLOYMENT.md](DEPLOYMENT.md) for more troubleshooting.

## License

This project is provided as-is for use with VICIdial call centers.

## Support

For issues:
1. Check logs: `docker compose logs -f`
2. Review documentation: `DEPLOYMENT.md` and `VICIDIAL_INTEGRATION.md`
3. Verify configuration: `.env` file
4. Test endpoints individually

---

**Ready to deploy!** Follow [DEPLOYMENT.md](DEPLOYMENT.md) for step-by-step instructions.
