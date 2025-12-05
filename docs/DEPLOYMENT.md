# Deployment Guide - Caller-ID Rotation API

Complete step-by-step deployment guide for Ubuntu 24 with Plesk.

## Prerequisites

- Ubuntu 24.04 LTS server
- Plesk installed and configured
- Domain name: `dialer1.rjimmigrad.com` pointing to server
- Root or sudo access
- Minimum 4GB RAM, 2 CPU cores
- 20GB available disk space

## Step 1: Install Docker & Docker Compose

### Install Docker

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y apt-transport-https ca-certificates curl software-properties-common

# Add Docker's official GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Add Docker repository
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io

# Start and enable Docker
sudo systemctl start docker
sudo systemctl enable docker

# Verify installation
docker --version
```

### Install Docker Compose

```bash
# Download Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose

# Make it executable
sudo chmod +x /usr/local/bin/docker-compose

# Verify installation
docker-compose --version
```

### Add Current User to Docker Group

```bash
sudo usermod -aG docker $USER
newgrp docker

# Verify
docker ps
```

## Step 2: Deploy Application

### Clone or Upload Project Files

```bash
# Create project directory
sudo mkdir -p /opt/callerid-api
sudo chown $USER:$USER /opt/callerid-api
cd /opt/callerid-api

# Upload your project files here
# If using git:
# git clone <your-repo-url> .

# Or manually copy all files from the project to /opt/callerid-api/
```

### Configure Environment

```bash
# Copy example env file
cp .env.example .env

# Generate secure secret key
SECRET_KEY=$(openssl rand -hex 32)
ADMIN_TOKEN=$(openssl rand -hex 32)

# Edit .env file
nano .env
```

Update the following values in `.env`:

```bash
# Security (IMPORTANT: Change these!)
SECRET_KEY=<paste-your-generated-secret-key>
ADMIN_TOKEN=<paste-your-generated-admin-token>

# Database
POSTGRES_PASSWORD=<generate-strong-password>

# Optional: Redis password
REDIS_PASSWORD=<generate-strong-password>
```

**Save the ADMIN_TOKEN** - you'll need it to access the dashboard!

### Build and Start Containers

```bash
# Build the Docker images
docker-compose build

# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f api
```

Expected output:
```
callerid_postgres   running
callerid_redis      running
callerid_api        running
```

### Verify API is Running

```bash
# Health check
curl http://127.0.0.1:8000/health

# Should return:
# {"status":"healthy","timestamp":"...","database":"healthy","redis":{"status":"healthy",...},"version":"1.0.0"}
```

## Step 3: Initialize Database

### Create Tables and Add Sample Data

```bash
# Initialize database (creates tables)
docker exec -it callerid_api python3 scripts/init_db.py

# Optionally add sample data for testing
docker exec -it callerid_api python3 scripts/init_db.py --sample-data
```

### Verify Database

```bash
# Connect to PostgreSQL
docker exec -it callerid_postgres psql -U callerid_user -d callerid_db

# Check tables
\dt

# Check sample data
SELECT * FROM caller_ids LIMIT 5;

# Exit
\q
```

## Step 4: Configure Plesk Reverse Proxy

### Option A: Via Plesk GUI (Recommended)

1. **Log in to Plesk**
   - Navigate to `https://your-server-ip:8443`

2. **Add/Select Domain**
   - Go to **Domains** → Select or Add `dialer1.rjimmigrad.com`

3. **Configure Reverse Proxy**
   - Go to **Apache & nginx Settings**
   - Find **Additional nginx directives** section
   - Add the following:

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    # WebSocket support (if needed)
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    
    # Timeouts
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
}
```

4. **Click "OK" to apply**

### Option B: Via Command Line

```bash
# Create nginx configuration
sudo tee /etc/nginx/conf.d/callerid-api.conf > /dev/null <<EOF
upstream callerid_api {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name dialer1.rjimmigrad.com;
    
    # Redirect to HTTPS
    return 301 https://\$server_name\$request_uri;
}

server {
    listen 443 ssl http2;
    server_name dialer1.rjimmigrad.com;
    
    # SSL certificates (managed by Plesk)
    ssl_certificate /opt/psa/var/certificates/cert-XXXXX.pem;
    ssl_certificate_key /opt/psa/var/certificates/cert-XXXXX.pem;
    
    # Reverse proxy to API
    location / {
        proxy_pass http://callerid_api;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
}
EOF

# Test configuration
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx
```

## Step 5: Configure SSL Certificate

### Via Plesk (Recommended)

1. In Plesk, go to **Domains** → `dialer1.rjimmigrad.com`
2. Click **SSL/TLS Certificates**
3. Choose:
   - **Let's Encrypt** (free, automatic renewal) - RECOMMENDED
   - Or upload your own certificate
4. Click **Install** or **Get it Free** (for Let's Encrypt)
5. Enable **Secure the domain**
6. Enable **Redirect from HTTP to HTTPS**

### Via Command Line (Let's Encrypt)

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d dialer1.rjimmigrad.com

# Follow prompts to complete setup

# Verify auto-renewal
sudo certbot renew --dry-run
```

## Step 6: Test the Deployment

### Test API Endpoints

```bash
# Health check
curl https://dialer1.rjimmigrad.com/health

# Test caller-ID allocation
curl "https://dialer1.rjimmigrad.com/next-cid?to=5555551234&campaign=test&agent=test_agent"

# Access dashboard (replace YOUR_ADMIN_TOKEN with actual token)
curl https://dialer1.rjimmigrad.com/dashboard \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Access Dashboard in Browser

1. Open: `https://dialer1.rjimmigrad.com/dashboard`
2. You'll be prompted for authentication
3. Use: **Bearer YOUR_ADMIN_TOKEN** in Authorization header
4. Or use a browser extension like "ModHeader" to add the header

## Step 7: Bulk Import Caller-IDs

### Generate Sample Data

```bash
cd /opt/callerid-api

# Generate sample CSV with 1000 caller-IDs
docker exec -it callerid_api python3 scripts/bulk_import.py \
  --generate-sample /app/data/sample_1000.csv \
  --sample-count 1000

# Create data directory on host
mkdir -p data

# Copy sample CSV from container
docker cp callerid_api:/app/data/sample_1000.csv ./data/
```

### Import Real Caller-IDs

Create your CSV file (`data/my_caller_ids.csv`):
```csv
caller_id,carrier,area_code,hourly_limit,daily_limit
2125551001,AT&T,212,100,500
2125551002,Verizon,212,100,500
...
```

Import:
```bash
# Copy CSV to container
docker cp data/my_caller_ids.csv callerid_api:/app/data/

# Import to database (fast, for large datasets)
docker exec -it callerid_api python3 scripts/bulk_import.py \
  --csv /app/data/my_caller_ids.csv \
  --method db \
  --batch-size 1000

# Or import via API (slower, but safer for production)
docker exec -it callerid_api python3 scripts/bulk_import.py \
  --csv /app/data/my_caller_ids.csv \
  --method api \
  --api-url http://127.0.0.1:8000 \
  --admin-token YOUR_ADMIN_TOKEN
```

## Step 8: Configure System Services

### Create Systemd Service (Optional)

For auto-start on boot:

```bash
sudo tee /etc/systemd/system/callerid-api.service > /dev/null <<EOF
[Unit]
Description=Caller-ID Rotation API
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/callerid-api
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

# Enable service
sudo systemctl enable callerid-api.service

# Start service
sudo systemctl start callerid-api.service

# Check status
sudo systemctl status callerid-api.service
```

### Configure Logrotate

```bash
sudo tee /etc/logrotate.d/callerid-api > /dev/null <<EOF
/opt/callerid-api/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 root root
    sharedscripts
    postrotate
        docker-compose -f /opt/callerid-api/docker-compose.yml restart api > /dev/null 2>&1 || true
    endscript
}
EOF
```

## Step 9: Firewall Configuration

### Configure UFW

```bash
# Enable UFW if not already enabled
sudo ufw enable

# Allow SSH
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS (for Plesk and API)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Allow Plesk admin
sudo ufw allow 8443/tcp

# Block direct access to Docker ports (security)
# API, PostgreSQL, and Redis are already bound to 127.0.0.1

# Check status
sudo ufw status verbose
```

## Step 10: Monitoring and Maintenance

### View Logs

```bash
# API logs
docker logs -f callerid_api

# Database logs
docker logs -f callerid_postgres

# Redis logs
docker logs -f callerid_redis

# All logs
docker-compose logs -f
```

### Monitor Performance

```bash
# Container stats
docker stats

# API statistics
curl https://dialer1.rjimmigrad.com/api/stats \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"

# Database connections
docker exec callerid_postgres psql -U callerid_user -d callerid_db \
  -c "SELECT count(*) as connections FROM pg_stat_activity;"

# Redis info
docker exec callerid_redis redis-cli INFO
```

### Backup Database

```bash
# Create backup directory
mkdir -p /opt/callerid-api/backups

# Backup PostgreSQL
docker exec callerid_postgres pg_dump -U callerid_user callerid_db > \
  /opt/callerid-api/backups/callerid_db_$(date +%Y%m%d_%H%M%S).sql

# Backup Redis
docker exec callerid_redis redis-cli SAVE
docker cp callerid_redis:/data/dump.rdb \
  /opt/callerid-api/backups/redis_$(date +%Y%m%d_%H%M%S).rdb
```

### Restore Database

```bash
# Restore PostgreSQL
cat /opt/callerid-api/backups/callerid_db_YYYYMMDD_HHMMSS.sql | \
  docker exec -i callerid_postgres psql -U callerid_user -d callerid_db

# Restore Redis
docker cp /opt/callerid-api/backups/redis_YYYYMMDD_HHMMSS.rdb \
  callerid_redis:/data/dump.rdb
docker-compose restart redis
```

### Update Application

```bash
cd /opt/callerid-api

# Pull latest changes (if using git)
git pull

# Rebuild and restart
docker-compose down
docker-compose build
docker-compose up -d

# Verify
curl https://dialer1.rjimmigrad.com/health
```

## Troubleshooting

### API Not Starting

```bash
# Check logs
docker logs callerid_api

# Check if port is in use
sudo netstat -tulpn | grep 8000

# Restart services
docker-compose restart
```

### Database Connection Failed

```bash
# Check PostgreSQL logs
docker logs callerid_postgres

# Verify credentials in .env
cat .env | grep POSTGRES

# Test connection
docker exec -it callerid_postgres psql -U callerid_user -d callerid_db
```

### Cannot Access Dashboard

```bash
# Verify nginx configuration
sudo nginx -t

# Check reverse proxy
curl -I http://127.0.0.1:8000/health
curl -I https://dialer1.rjimmigrad.com/health

# Verify admin token
grep ADMIN_TOKEN /opt/callerid-api/.env
```

### High Memory Usage

```bash
# Check container resource usage
docker stats

# Increase Redis maxmemory in docker-compose.yml:
# command: redis-server --maxmemory 1gb

# Restart
docker-compose restart redis
```

## Security Best Practices

1. **Change default passwords** in `.env`
2. **Use strong admin token** (32+ characters, random)
3. **Keep Docker images updated**: `docker-compose pull && docker-compose up -d`
4. **Enable firewall** (UFW)
5. **Regular backups** (automate with cron)
6. **Monitor logs** for suspicious activity
7. **Use HTTPS only** (enforce in Plesk)
8. **Limit SSH access** (use SSH keys)

## Next Steps

1. [Integrate with VICIdial](VICIDIAL_INTEGRATION.md)
2. Import your caller-IDs
3. Configure monitoring alerts
4. Set up automated backups
5. Review and adjust rate limits based on your needs

## Support

For issues:
1. Check logs: `docker logs callerid_api`
2. Verify configuration: `cat .env`
3. Test health: `curl http://127.0.0.1:8000/health`
4. Review documentation
