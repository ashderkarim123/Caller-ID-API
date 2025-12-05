# Quick Start Guide

Get the Caller-ID Rotation API up and running in 10 minutes!

## Prerequisites

- Linux server (Ubuntu 24 recommended)
- Docker and Docker Compose installed
- 4GB RAM, 2 CPU cores minimum
- Basic command line knowledge

## Step 1: Get the Code

```bash
# Create project directory
sudo mkdir -p /opt/callerid-api
sudo chown $USER:$USER /opt/callerid-api
cd /opt/callerid-api

# Clone or copy your project files here
# (If you're reading this, you already have them!)
```

## Step 2: Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Generate secure credentials
SECRET_KEY=$(openssl rand -hex 32)
ADMIN_TOKEN=$(openssl rand -hex 32)

# Update .env file
sed -i "s/your_secret_key_here_generate_with_openssl_rand_hex_32/$SECRET_KEY/" .env
sed -i "s/your_admin_token_here_change_this_to_something_secure/$ADMIN_TOKEN/" .env
sed -i "s/your_secure_database_password_here/$(openssl rand -hex 16)/" .env

# Display your admin token (SAVE THIS!)
echo "Your Admin Token: $ADMIN_TOKEN"
echo "Save this token - you'll need it to access the dashboard!"
```

## Step 3: Start Services

```bash
# Build and start all containers
docker-compose up -d

# Check status
docker-compose ps

# Should show 3 running containers:
# - callerid_api
# - callerid_postgres
# - callerid_redis
```

## Step 4: Initialize Database

```bash
# Create database tables
docker exec -it callerid_api python3 scripts/init_db.py

# Add sample data for testing (optional)
docker exec -it callerid_api python3 scripts/init_db.py --sample-data
```

## Step 5: Import Caller-IDs

### Option A: Import Sample Data (Testing)

```bash
# Generate and import 1000 sample caller-IDs
make import-sample

# Or manually:
docker exec -it callerid_api python3 scripts/bulk_import.py \
  --generate-sample /app/data/sample_1000.csv \
  --sample-count 1000

docker exec -it callerid_api python3 scripts/bulk_import.py \
  --csv /app/data/sample_1000.csv \
  --method db
```

### Option B: Import Your Caller-IDs

Create a CSV file (`my_numbers.csv`):
```csv
caller_id,carrier,area_code,hourly_limit,daily_limit
2125551001,AT&T,212,100,500
2125551002,Verizon,212,100,500
3105552001,T-Mobile,310,150,750
```

Import:
```bash
# Copy to container
docker cp my_numbers.csv callerid_api:/app/data/

# Import
docker exec -it callerid_api python3 scripts/bulk_import.py \
  --csv /app/data/my_numbers.csv \
  --method db
```

## Step 6: Test the API

```bash
# Health check
curl http://127.0.0.1:8000/health

# Should return: {"status":"healthy",...}

# Get next caller-ID
curl "http://127.0.0.1:8000/next-cid?to=5555551234&campaign=test&agent=test_agent"

# Should return: {"success":true,"caller_id":"2125551234",...}
```

## Step 7: Access Dashboard

```bash
# Get your admin token
grep ADMIN_TOKEN .env

# Access dashboard in browser
# URL: http://127.0.0.1:8000/dashboard
# Add header: Authorization: Bearer YOUR_ADMIN_TOKEN
```

**Note:** You'll need a browser extension like "ModHeader" to add the Authorization header.

## Step 8: Set Up Reverse Proxy (Production)

### Quick nginx Setup

```bash
# Create nginx config
sudo tee /etc/nginx/conf.d/callerid-api.conf > /dev/null <<'EOF'
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
EOF

# Test and reload
sudo nginx -t
sudo systemctl reload nginx

# Set up SSL with Let's Encrypt
sudo certbot --nginx -d your-domain.com
```

## Step 9: VICIdial Integration

Add to `/etc/asterisk/extensions_custom.conf`:

```asterisk
[callerid-rotation]
exten => _X.,1,NoOp(Caller-ID Rotation for ${EXTEN})
 same => n,Set(API_URL=http://127.0.0.1:8000/next-cid)
 same => n,Set(RESPONSE=${CURL(${API_URL}?to=${EXTEN}&campaign=${VICIDIAL_campaign}&agent=${VICIDIAL_agent})})
 same => n,Set(CID=${SHELL(echo '${RESPONSE}' | grep -oP '(?<="caller_id":")[^"]*')})
 same => n,GotoIf($["${CID}" != ""]?use_cid:use_default)
 same => n(use_cid),Set(CALLERID(num)=${CID})
 same => n(use_default),Dial(${TRUNK}/${EXTEN})
 same => n,Hangup()
```

Reload Asterisk:
```bash
asterisk -rx "dialplan reload"
```

## Step 10: Verify Everything

```bash
# Check containers
docker-compose ps

# Check logs
docker logs callerid_api

# Check database
docker exec -it callerid_postgres psql -U callerid_user -d callerid_db \
  -c "SELECT COUNT(*) FROM caller_ids;"

# Test API
curl http://127.0.0.1:8000/health
```

## Common Commands

```bash
# View logs
docker logs -f callerid_api

# Restart services
docker-compose restart

# Stop services
docker-compose down

# Update code and restart
docker-compose down
docker-compose build
docker-compose up -d

# Backup database
mkdir -p backups
docker exec callerid_postgres pg_dump -U callerid_user callerid_db > backups/backup.sql

# Import more caller-IDs
docker exec -it callerid_api python3 scripts/bulk_import.py \
  --csv /app/data/new_numbers.csv --method db
```

## Troubleshooting

### API not starting?
```bash
docker logs callerid_api
# Check for errors in output
```

### Can't connect to database?
```bash
# Verify database is running
docker logs callerid_postgres

# Test connection
docker exec -it callerid_postgres psql -U callerid_user -d callerid_db
```

### No caller-IDs available?
```bash
# Check count
docker exec -it callerid_postgres psql -U callerid_user -d callerid_db \
  -c "SELECT COUNT(*) FROM caller_ids WHERE is_active = 1;"

# Import more
make import-sample
```

## Next Steps

1. **Production Deployment**: See [DEPLOYMENT.md](docs/DEPLOYMENT.md)
2. **VICIdial Integration**: See [VICIDIAL_INTEGRATION.md](docs/VICIDIAL_INTEGRATION.md)
3. **API Documentation**: See [API_REFERENCE.md](docs/API_REFERENCE.md)
4. **FAQ**: See [FAQ.md](docs/FAQ.md)

## Support

- Check logs: `docker logs callerid_api`
- Health check: `curl http://127.0.0.1:8000/health`
- Review documentation in `docs/` folder

---

**You're all set!** 🎉

The API is now running and ready to allocate caller-IDs for your VICIdial call center.
