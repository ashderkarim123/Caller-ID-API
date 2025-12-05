# Caller-ID Rotation API - Deployment Guide

Complete deployment guide for Ubuntu 24 with Plesk.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Initial Setup](#initial-setup)
3. [Docker Deployment](#docker-deployment)
4. [Plesk Reverse Proxy Configuration](#plesk-reverse-proxy-configuration)
5. [SSL Certificate Setup](#ssl-certificate-setup)
6. [Bulk Import Caller-IDs](#bulk-import-caller-ids)
7. [Testing the API](#testing-the-api)
8. [VICIdial Integration](#vicidial-integration)
9. [Troubleshooting](#troubleshooting)

---

## Prerequisites

- Ubuntu 24.04 LTS server
- Plesk installed and configured
- Root or sudo access
- Domain name: `dialer1.rjimmigrad.com` (or your domain)
- Basic knowledge of Docker and Plesk

---

## Initial Setup

### 1. Install Docker and Docker Compose

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo apt install docker-compose-plugin -y

# Add current user to docker group (optional, to run without sudo)
sudo usermod -aG docker $USER
newgrp docker

# Verify installation
docker --version
docker compose version
```

### 2. Clone or Upload Project Files

```bash
# Create project directory
sudo mkdir -p /opt/callerid-api
sudo chown $USER:$USER /opt/callerid-api
cd /opt/callerid-api

# Upload all project files to this directory:
# - app/
# - Dockerfile
# - docker-compose.yml
# - requirements.txt
# - .env.example
# - bulk_import.py
# - example_caller_ids.csv
```

### 3. Configure Environment Variables

```bash
# Copy example env file
cp .env.example .env

# Edit .env file with secure values
nano .env
```

**Important:** Change these values in `.env`:

```env
DB_PASSWORD=your_secure_database_password_here
REDIS_PASSWORD=your_secure_redis_password_here
ADMIN_TOKEN=your_secure_admin_token_here
JWT_SECRET_KEY=your_jwt_secret_key_here
```

Generate secure passwords:
```bash
# Generate random passwords
openssl rand -base64 32  # For DB_PASSWORD
openssl rand -base64 32  # For REDIS_PASSWORD
openssl rand -base64 32  # For ADMIN_TOKEN
openssl rand -base64 32  # For JWT_SECRET_KEY
```

---

## Docker Deployment

### 1. Build and Start Containers

```bash
cd /opt/callerid-api

# Build and start all services
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f api
```

### 2. Verify Services

```bash
# Check API health
curl http://127.0.0.1:8000/health

# Expected response:
# {"status":"healthy","redis":"ok","timestamp":"2024-01-01T12:00:00.000000"}

# Check database connection
docker compose exec db psql -U callerid_user -d callerid_db -c "SELECT COUNT(*) FROM caller_ids;"

# Check Redis connection
docker compose exec redis redis-cli -a YOUR_REDIS_PASSWORD ping
# Should return: PONG
```

### 3. Initialize Database Tables

The database tables are automatically created on first API startup. You can verify:

```bash
docker compose exec db psql -U callerid_user -d callerid_db -c "\dt"
```

You should see tables: `caller_ids`, `reservations`, `api_requests`

---

## Plesk Reverse Proxy Configuration

### 1. Create Domain/Subdomain in Plesk

1. Login to Plesk
2. Go to **Domains** → **Add Domain**
3. Domain name: `dialer1.rjimmigrad.com`
4. Complete the domain setup

### 2. Configure Reverse Proxy

1. In Plesk, go to **Domains** → `dialer1.rjimmigrad.com` → **Hosting Settings**
2. Enable **Proxy mode** or use **Apache & nginx Settings**

#### Option A: Using Plesk Apache & nginx Settings

1. Go to **Apache & nginx Settings**
2. Add to **Additional nginx directives**:

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
}
```

3. Add to **Additional Apache directives** (if using Apache):

```apache
ProxyPreserveHost On
ProxyPass / http://127.0.0.1:8000/
ProxyPassReverse / http://127.0.0.1:8000/
```

#### Option B: Using Plesk Reverse Proxy Extension

1. Install **Reverse Proxy** extension in Plesk (if available)
2. Configure:
   - **Backend URL**: `http://127.0.0.1:8000`
   - **Path**: `/`
   - Enable **Preserve Host Header**

### 3. Test Reverse Proxy

```bash
# From server
curl http://127.0.0.1:8000/health

# From external (should work after DNS propagation)
curl https://dialer1.rjimmigrad.com/health
```

---

## SSL Certificate Setup

### Option 1: Let's Encrypt (Recommended)

1. In Plesk, go to **SSL/TLS Certificates**
2. Click **Let's Encrypt**
3. Select domain: `dialer1.rjimmigrad.com`
4. Enter email address
5. Click **Install**
6. Enable **Secure the domain with an SSL/TLS certificate**

### Option 2: Use Existing Certificate

1. Upload your SSL certificate in Plesk
2. Assign it to `dialer1.rjimmigrad.com`
3. Enable **Secure the domain**

### Verify SSL

```bash
curl https://dialer1.rjimmigrad.com/health
```

---

## Bulk Import Caller-IDs

### 1. Prepare CSV File

Use the provided `example_caller_ids.csv` as a template, or create your own:

```csv
caller_id,carrier,area_code,daily_limit,hourly_limit,meta_json
5551234567,Verizon,555,1000,100,"{""state"":""CA"",""type"":""mobile""}"
5551234568,AT&T,555,1000,100,"{""state"":""CA"",""type"":""mobile""}"
```

### 2. Run Import Script

```bash
cd /opt/callerid-api

# Copy CSV file to container or mount volume
docker compose cp your_caller_ids.csv api:/tmp/caller_ids.csv

# Run import script
docker compose exec api python bulk_import.py /tmp/caller_ids.csv

# Or if CSV is on host (mount volume first in docker-compose.yml)
docker compose exec api python bulk_import.py /app/caller_ids.csv
```

### 3. Verify Import

```bash
# Check database
docker compose exec db psql -U callerid_user -d callerid_db -c "SELECT COUNT(*) FROM caller_ids;"

# Or use API dashboard
# Visit: https://dialer1.rjimmigrad.com/dashboard
```

### Alternative: Import via API

```bash
# Add single caller-ID via API
curl -X POST "https://dialer1.rjimmigrad.com/add-number" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "caller_id": "5551234567",
    "carrier": "Verizon",
    "area_code": "555",
    "daily_limit": 1000,
    "hourly_limit": 100,
    "meta": {"state": "CA", "type": "mobile"}
  }'
```

---

## Testing the API

### 1. Health Check

```bash
curl https://dialer1.rjimmigrad.com/health
```

### 2. Get Next Caller-ID

```bash
curl "https://dialer1.rjimmigrad.com/next-cid?to=5559876543&campaign=TEST&agent=AGENT001"
```

Expected response:
```json
{
  "caller_id": "5551234567",
  "carrier": "Verizon",
  "area_code": "555",
  "meta": {}
}
```

### 3. Access Dashboard

1. Open browser: `https://dialer1.rjimmigrad.com/dashboard`
2. When prompted, enter Bearer token: `YOUR_ADMIN_TOKEN`
3. Or use curl:

```bash
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  https://dialer1.rjimmigrad.com/dashboard
```

---

## VICIdial Integration

### Asterisk Dialplan Configuration

Add this to your Asterisk dialplan (typically in `/etc/asterisk/extensions.conf` or VICIdial dialplan):

```ini
[vicidial-auto]
; VICIdial auto-dial context with caller-ID rotation

exten => _X.,1,NoOp(Caller-ID Rotation: ${EXTEN} Campaign: ${VICIDIAL_campaign} Agent: ${AGENT})
exten => _X.,n,Set(CID_API_URL=https://dialer1.rjimmigrad.com/next-cid?to=${EXTEN}&campaign=${VICIDIAL_campaign}&agent=${AGENT})
exten => _X.,n,Set(CID_RESPONSE=${CURL(${CID_API_URL})})
exten => _X.,n,NoOp(API Response: ${CID_RESPONSE})
exten => _X.,n,Set(CID_JSON=${CID_RESPONSE})
exten => _X.,n,Set(CID_NUMBER=${FILTER(0-9,${JSON_DECODE(${CID_JSON},caller_id)})})
exten => _X.,n,GotoIf($["${CID_NUMBER}" = ""]?cid_error)
exten => _X.,n,Set(CALLERID(num)=${CID_NUMBER})
exten => _X.,n,Set(CALLERID(name)=${CID_NUMBER})
exten => _X.,n,NoOp(Using Caller-ID: ${CALLERID(num)})
exten => _X.,n,Goto(vicidial-auto,${EXTEN},dial)
exten => _X.,n(cid_error),NoOp(ERROR: Failed to get caller-ID from API)
exten => _X.,n,Set(CALLERID(num)=${VICIDIAL_callerid})
exten => _X.,n,Goto(vicidial-auto,${EXTEN},dial)
exten => _X.,n(dial),Dial(${TRUNK}/${EXTEN},,tTo)
exten => _X.,n,Hangup()
```

### Alternative: Using AGI Script

Create `/usr/share/asterisk/agi-bin/get_callerid.py`:

```python
#!/usr/bin/env python3
import sys
import urllib.request
import json

# Read AGI variables
agi_vars = {}
for line in sys.stdin:
    if line.strip() == '':
        break
    key, value = line.split(':', 1)
    agi_vars[key.strip()] = value.strip()

# Get parameters
exten = agi_vars.get('agi_extension', '')
campaign = agi_vars.get('agi_arg_1', '')
agent = agi_vars.get('agi_arg_2', '')

# Call API
api_url = f"https://dialer1.rjimmigrad.com/next-cid?to={exten}&campaign={campaign}&agent={agent}"

try:
    with urllib.request.urlopen(api_url, timeout=5) as response:
        data = json.loads(response.read().decode())
        caller_id = data.get('caller_id', '')
        print(f"SET VARIABLE CALLERID(num) {caller_id}")
        print(f"VERBOSE \"Using Caller-ID: {caller_id}\" 1")
except Exception as e:
    print(f"VERBOSE \"Error getting caller-ID: {e}\" 1")
    sys.exit(1)
```

Make executable:
```bash
chmod +x /usr/share/asterisk/agi-bin/get_callerid.py
```

Use in dialplan:
```ini
exten => _X.,1,AGI(get_callerid.py,${VICIDIAL_campaign},${AGENT})
exten => _X.,n,Dial(${TRUNK}/${EXTEN},,tTo)
```

### Testing Dialplan

```bash
# Test in Asterisk CLI
asterisk -rvvv

# In CLI:
dialplan reload
dialplan show vicidial-auto

# Test call
channel originate Local/5551234567@vicidial-auto application Wait 1
```

---

## Troubleshooting

### API Not Accessible

1. **Check Docker containers:**
   ```bash
   docker compose ps
   docker compose logs api
   ```

2. **Check API is listening:**
   ```bash
   netstat -tlnp | grep 8000
   curl http://127.0.0.1:8000/health
   ```

3. **Check Plesk reverse proxy:**
   - Verify nginx/Apache configuration
   - Check Plesk error logs
   - Test from server: `curl http://127.0.0.1:8000/health`

### Database Connection Issues

```bash
# Check database container
docker compose logs db

# Test database connection
docker compose exec db psql -U callerid_user -d callerid_db

# Check environment variables
docker compose exec api env | grep DB_
```

### Redis Connection Issues

```bash
# Check Redis container
docker compose logs redis

# Test Redis connection
docker compose exec redis redis-cli -a YOUR_REDIS_PASSWORD ping

# Check Redis from API container
docker compose exec api python -c "import asyncio; from app.redis_client import redis_client; asyncio.run(redis_client.connect()); print('OK')"
```

### No Caller-IDs Available

1. **Check if caller-IDs exist:**
   ```bash
   docker compose exec db psql -U callerid_user -d callerid_db -c "SELECT COUNT(*) FROM caller_ids WHERE is_active=1;"
   ```

2. **Check limits:**
   ```bash
   docker compose exec db psql -U callerid_user -d callerid_db -c "SELECT caller_id, daily_limit, hourly_limit FROM caller_ids LIMIT 5;"
   ```

3. **Check reservations:**
   ```bash
   docker compose exec redis redis-cli -a YOUR_REDIS_PASSWORD KEYS "reservation:*"
   ```

### Performance Issues

1. **Increase workers:**
   Edit `Dockerfile` CMD:
   ```dockerfile
   CMD ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--workers", "8"]
   ```

2. **Check database connections:**
   ```bash
   docker compose exec db psql -U callerid_user -d callerid_db -c "SELECT count(*) FROM pg_stat_activity;"
   ```

3. **Monitor Redis:**
   ```bash
   docker compose exec redis redis-cli -a YOUR_REDIS_PASSWORD INFO stats
   ```

### Logs

```bash
# API logs
docker compose logs -f api

# Database logs
docker compose logs -f db

# Redis logs
docker compose logs -f redis

# All logs
docker compose logs -f
```

---

## Maintenance

### Backup Database

```bash
# Create backup
docker compose exec db pg_dump -U callerid_user callerid_db > backup_$(date +%Y%m%d).sql

# Restore backup
docker compose exec -T db psql -U callerid_user callerid_db < backup_20240101.sql
```

### Backup Redis

```bash
# Redis data is in volume, backup volume
docker run --rm -v callerid-api_redis_data:/data -v $(pwd):/backup alpine tar czf /backup/redis_backup.tar.gz /data
```

### Update Application

```bash
cd /opt/callerid-api
git pull  # If using git
docker compose build api
docker compose up -d api
```

### Restart Services

```bash
# Restart all
docker compose restart

# Restart specific service
docker compose restart api
```

---

## Security Recommendations

1. **Change all default passwords** in `.env`
2. **Restrict API access** - Only allow from VICIdial server IPs
3. **Use firewall** - Only expose ports 80/443, not 8000
4. **Regular backups** - Database and Redis data
5. **Monitor logs** - Set up log rotation
6. **Update regularly** - Keep Docker images updated
7. **Use strong admin token** - Generate with `openssl rand -base64 32`

---

## Support

For issues or questions:
1. Check logs: `docker compose logs -f`
2. Verify configuration: `.env` file
3. Test endpoints individually
4. Check VICIdial/Asterisk logs

---

**Deployment Complete!** 🎉

Your Caller-ID Rotation API should now be running at:
- **API**: `https://dialer1.rjimmigrad.com`
- **Dashboard**: `https://dialer1.rjimmigrad.com/dashboard`
- **Health**: `https://dialer1.rjimmigrad.com/health`
