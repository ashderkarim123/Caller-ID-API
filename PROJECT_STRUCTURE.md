# Project Structure

Complete file structure of the Caller-ID Rotation API project.

```
callerid-api/
├── app/                          # Main application directory
│   ├── __init__.py              # Package initialization
│   ├── main.py                  # FastAPI application and endpoints
│   ├── config.py                # Configuration management (Pydantic Settings)
│   ├── db.py                    # Database connection and session management
│   ├── models.py                # SQLAlchemy database models
│   ├── redis_client.py          # Redis client and reservation logic
│   ├── utils.py                 # Caller-ID rotation utility functions
│   ├── auth.py                  # Authentication and authorization
│   └── templates/
│       └── dashboard.html       # Admin dashboard Jinja2 template
│
├── scripts/                      # Helper scripts
│   └── import_csv.sh           # CSV import helper script
│
├── Dockerfile                   # API container definition
├── docker-compose.yml           # Multi-container Docker Compose setup
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment variables template
├── .gitignore                   # Git ignore rules
│
├── bulk_import.py               # Bulk CSV import script
├── example_caller_ids.csv       # Example caller-ID data file
│
└── Documentation/
    ├── README.md                # Project overview and quick start
    ├── DEPLOYMENT.md            # Complete deployment guide
    ├── VICIDIAL_INTEGRATION.md  # VICIdial/Asterisk integration guide
    ├── QUICK_REFERENCE.md       # Quick reference for common commands
    └── PROJECT_STRUCTURE.md     # This file
```

## Key Files Explained

### Application Core (`app/`)

- **main.py**: FastAPI application with all endpoints (`/next-cid`, `/add-number`, `/dashboard`, `/health`)
- **config.py**: Centralized configuration using Pydantic Settings, loads from `.env`
- **db.py**: Async SQLAlchemy engine and session management
- **models.py**: Database models (`CallerID`, `Reservation`, `APIRequest`)
- **redis_client.py**: Redis operations for reservations and usage tracking
- **utils.py**: Core caller-ID rotation logic (LRU, limits, area code matching)
- **auth.py**: Admin token verification and IP extraction utilities
- **templates/dashboard.html**: Admin dashboard with real-time statistics

### Docker & Deployment

- **Dockerfile**: Python 3.11 slim image, installs dependencies, runs uvicorn with 4 workers
- **docker-compose.yml**: Defines 3 services (api, db, redis) with health checks and volumes
- **requirements.txt**: All Python dependencies (FastAPI, SQLAlchemy, asyncpg, aioredis, etc.)

### Scripts & Utilities

- **bulk_import.py**: Async script to import caller-IDs from CSV into database
- **scripts/import_csv.sh**: Helper script to easily import CSV files
- **example_caller_ids.csv**: Sample CSV with 20 caller-IDs for testing

### Configuration

- **.env.example**: Template with all required environment variables
- **.gitignore**: Excludes sensitive files (.env, __pycache__, logs, etc.)

### Documentation

- **README.md**: Project overview, features, quick start, API documentation
- **DEPLOYMENT.md**: Step-by-step deployment guide (Docker, Plesk, SSL, troubleshooting)
- **VICIDIAL_INTEGRATION.md**: Complete VICIdial/Asterisk integration guide with dialplan examples
- **QUICK_REFERENCE.md**: Cheat sheet for common commands and operations

## Docker Services

### api
- **Image**: Built from Dockerfile
- **Port**: 127.0.0.1:8000
- **Dependencies**: db, redis
- **Volumes**: app/, bulk_import.py, example_caller_ids.csv

### db
- **Image**: postgres:15-alpine
- **Port**: 127.0.0.1:5432
- **Volume**: postgres_data (persistent)
- **Database**: callerid_db

### redis
- **Image**: redis:7-alpine
- **Port**: 127.0.0.1:6379
- **Volume**: redis_data (persistent)
- **Features**: AOF persistence, password protection

## Database Schema

### caller_ids
- Primary key: `caller_id` (string)
- Fields: carrier, area_code, daily_limit, hourly_limit, daily_used, hourly_used, last_used, total_uses, is_active, meta (JSONB)
- Indexes: area_code, last_used, composite indexes

### reservations
- Primary key: `id` (auto-increment)
- Fields: caller_id, agent, campaign, reserved_at, reserved_until, to_number
- Indexes: caller_id, agent, campaign, reserved_until

### api_requests
- Primary key: `id` (auto-increment)
- Fields: endpoint, method, agent, campaign, caller_id, ip_address, status_code, response_time_ms, created_at
- Indexes: endpoint, agent, campaign, created_at

## Redis Keys

- `reservation:{caller_id}` - Active reservations (TTL-based)
- `usage:hourly:{caller_id}:{YYYYMMDDHH}` - Hourly usage counters
- `usage:daily:{caller_id}:{YYYYMMDD}` - Daily usage counters
- `lru:area:{area_code}` - LRU tracking sorted sets
- `lru:all` - Global LRU tracking

## API Endpoints

- `GET /next-cid` - Get next available caller-ID (main endpoint)
- `POST /add-number` - Add new caller-ID (admin)
- `GET /dashboard` - Admin dashboard (admin)
- `GET /api/stats` - API statistics JSON (admin)
- `GET /health` - Health check

## Environment Variables

Required in `.env`:
- `DB_USER`, `DB_PASSWORD`, `DB_NAME`
- `REDIS_PASSWORD`
- `ADMIN_TOKEN`, `JWT_SECRET_KEY`
- `DEBUG`, `LOG_LEVEL`

Optional:
- `RESERVATION_TTL_SECONDS`
- `DEFAULT_DAILY_LIMIT`, `DEFAULT_HOURLY_LIMIT`
- `RATE_LIMIT_PER_AGENT`, `RATE_LIMIT_PER_IP`

## Deployment Flow

1. Clone/upload project files
2. Copy `.env.example` to `.env` and configure
3. Run `docker compose up -d`
4. Verify with `curl http://127.0.0.1:8000/health`
5. Configure Plesk reverse proxy
6. Set up SSL certificate
7. Import caller-IDs via bulk_import.py
8. Configure VICIdial dialplan
9. Test and monitor via dashboard

---

For detailed information, see the respective documentation files.
