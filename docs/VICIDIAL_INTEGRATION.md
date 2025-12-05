# VICIdial Integration Guide

This guide explains how to integrate the Caller-ID Rotation API with your VICIdial call center.

## Overview

The API provides dynamic caller-ID rotation for outbound calls, ensuring:
- Optimal caller-ID selection based on area code
- Rate limiting per caller-ID
- Concurrency-safe allocation
- Real-time reservation management

## Architecture

```
VICIdial → Asterisk Dialplan → HTTP Request → Caller-ID API → Redis/PostgreSQL
                ↓
         Set CallerID(num)
                ↓
           Place Call
```

## Asterisk Dialplan Integration

### Method 1: Using CURL (Recommended)

Add this to your Asterisk dialplan (e.g., `/etc/asterisk/extensions_custom.conf`):

```asterisk
[callerid-rotation]
exten => _X.,1,NoOp(Caller-ID Rotation for ${EXTEN})
 same => n,Set(CAMPAIGN=${VICIDIAL_campaign})
 same => n,Set(AGENT=${VICIDIAL_agent})
 same => n,Set(DESTINATION=${EXTEN})
 same => n,Set(API_URL=http://127.0.0.1:8000/next-cid)
 same => n,Set(API_RESPONSE=${CURL(${API_URL}?to=${DESTINATION}&campaign=${CAMPAIGN}&agent=${AGENT})})
 same => n,NoOp(API Response: ${API_RESPONSE})
 same => n,Set(NEW_CID=${SHELL(echo '${API_RESPONSE}' | grep -oP '(?<="caller_id":")[^"]*')})
 same => n,GotoIf($["${NEW_CID}" != ""]?set_cid:error)
 same => n(set_cid),Set(CALLERID(num)=${NEW_CID})
 same => n,NoOp(Set CallerID to: ${NEW_CID})
 same => n,Dial(${TRUNK}/${EXTEN},${TIMEOUT},${OPTIONS})
 same => n,Hangup()
 same => n(error),NoOp(Failed to get caller-ID, using default)
 same => n,Dial(${TRUNK}/${EXTEN},${TIMEOUT},${OPTIONS})
 same => n,Hangup()
```

### Method 2: Using Python AGI Script

Create `/var/lib/asterisk/agi-bin/callerid_rotation.py`:

```python
#!/usr/bin/env python3
import sys
import requests
import json

# Read AGI environment
env = {}
while True:
    line = sys.stdin.readline().strip()
    if not line:
        break
    key, value = line.split(':', 1)
    env[key.strip()] = value.strip()

# Get parameters
destination = env.get('agi_extension', '')
campaign = env.get('agi_arg_1', 'default')
agent = env.get('agi_arg_2', 'unknown')

# Call API
try:
    response = requests.get(
        'http://127.0.0.1:8000/next-cid',
        params={
            'to': destination,
            'campaign': campaign,
            'agent': agent
        },
        timeout=5
    )
    
    if response.status_code == 200:
        data = response.json()
        caller_id = data.get('caller_id', '')
        
        if caller_id:
            # Set caller-ID
            print(f'SET VARIABLE CALLERID(num) "{caller_id}"')
            sys.stdout.flush()
            sys.stdin.readline()
            
            # Log success
            print(f'VERBOSE "Set CallerID to: {caller_id}" 1')
            sys.stdout.flush()
            sys.stdin.readline()
        else:
            print('VERBOSE "No caller-ID returned" 1')
            sys.stdout.flush()
            sys.stdin.readline()
    else:
        print(f'VERBOSE "API error: {response.status_code}" 1')
        sys.stdout.flush()
        sys.stdin.readline()

except Exception as e:
    print(f'VERBOSE "Error: {str(e)}" 1')
    sys.stdout.flush()
    sys.stdin.readline()

print('EXIT')
sys.stdout.flush()
```

Make it executable:
```bash
chmod +x /var/lib/asterisk/agi-bin/callerid_rotation.py
```

Dialplan usage:
```asterisk
[callerid-rotation-agi]
exten => _X.,1,NoOp(Caller-ID Rotation via AGI for ${EXTEN})
 same => n,AGI(callerid_rotation.py,${VICIDIAL_campaign},${VICIDIAL_agent})
 same => n,Dial(${TRUNK}/${EXTEN},${TIMEOUT},${OPTIONS})
 same => n,Hangup()
```

### Method 3: Using Asterisk FUNC_CURL

More efficient, requires `func_curl` module:

```asterisk
[callerid-rotation-func]
exten => _X.,1,NoOp(Caller-ID Rotation for ${EXTEN})
 same => n,Set(API_URL=http://127.0.0.1:8000/next-cid?to=${EXTEN}&campaign=${VICIDIAL_campaign}&agent=${VICIDIAL_agent})
 same => n,Set(CURLOPT(httptimeout)=5)
 same => n,Set(API_RESPONSE=${CURL(${API_URL})})
 same => n,Set(ARRAY(success,caller_id)=${FIELDQTY(API_RESPONSE,",")})
 same => n,Set(NEW_CID=${FILTER(0-9,${API_RESPONSE})})
 same => n,GotoIf($["${NEW_CID}" != ""]?set_cid:use_default)
 same => n(set_cid),Set(CALLERID(num)=${NEW_CID})
 same => n,NoOp(Using rotated CallerID: ${NEW_CID})
 same => n,Goto(dial)
 same => n(use_default),NoOp(Using default CallerID)
 same => n(dial),Dial(${TRUNK}/${EXTEN},${TIMEOUT},${OPTIONS})
 same => n,Hangup()
```

## VICIdial Campaign Configuration

### 1. Configure Campaign

In VICIdial Admin:

1. Go to **Admin → Campaigns**
2. Select your campaign
3. Scroll to **Dialplan Options**
4. Set **Dial Prefix**: (leave blank or use your normal prefix)
5. Set **Campaign CID**: `CAMPAIGN` (this will be overridden by API)

### 2. Modify Outbound Dialplan

Edit your campaign's outbound context to use the caller-ID rotation context:

```asterisk
[vicidial-campaign-outbound]
exten => _X.,1,Goto(callerid-rotation,${EXTEN},1)
```

### 3. Test the Integration

Make a test call:

```asterisk
*CLI> originate Local/5555551234@callerid-rotation extension 8600@default
```

Check the logs:
```bash
tail -f /var/log/asterisk/full | grep "Caller-ID"
```

## API Endpoints Reference

### GET /next-cid

Get next available caller-ID for a call.

**Parameters:**
- `to` (required): Destination phone number
- `campaign` (required): Campaign name
- `agent` (required): Agent name/ID

**Response:**
```json
{
  "success": true,
  "caller_id": "2125551234",
  "area_code": "212",
  "carrier": "AT&T",
  "reserved_for": 300,
  "destination": "3105559876",
  "agent": "agent001",
  "campaign": "sales_campaign"
}
```

**cURL Example:**
```bash
curl "http://127.0.0.1:8000/next-cid?to=3105559876&campaign=sales&agent=agent001"
```

### POST /add-number

Add a new caller-ID (requires admin token).

**Parameters:**
- `caller_id` (required): Phone number
- `carrier` (optional): Carrier name
- `area_code` (optional): Area code (auto-detected if not provided)
- `hourly_limit` (optional): Hourly usage limit (default: 100)
- `daily_limit` (optional): Daily usage limit (default: 500)

**Headers:**
- `Authorization: Bearer YOUR_ADMIN_TOKEN`

**cURL Example:**
```bash
curl -X POST "http://127.0.0.1:8000/add-number?caller_id=2125551234&carrier=AT%26T&area_code=212" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

## Bulk Import Caller-IDs

### From CSV File

Create a CSV file (`caller_ids.csv`):
```csv
caller_id,carrier,area_code,hourly_limit,daily_limit
2125551001,AT&T,212,100,500
2125551002,Verizon,212,100,500
3105552001,T-Mobile,310,150,750
```

Import:
```bash
python3 scripts/bulk_import.py --csv caller_ids.csv --method db
```

### Via API

```bash
python3 scripts/bulk_import.py \
  --csv caller_ids.csv \
  --method api \
  --api-url http://localhost:8000 \
  --admin-token YOUR_ADMIN_TOKEN
```

## Monitoring and Dashboard

Access the admin dashboard:
```
https://dialer1.rjimmigrad.com/dashboard
```

**Authentication:**
Add header: `Authorization: Bearer YOUR_ADMIN_TOKEN`

The dashboard shows:
- Total and active caller-IDs
- Active reservations
- Campaign statistics
- API request logs
- Redis health status

## Rate Limiting

The API implements rate limiting:

1. **Per Agent**: Default 100 requests/minute (configurable via `DEFAULT_RATE_LIMIT_PER_AGENT`)
2. **Per Caller-ID Hourly**: Configurable per number (default: 100)
3. **Per Caller-ID Daily**: Configurable per number (default: 500)

## Troubleshooting

### No Caller-IDs Available

**Error:** `503 Service Unavailable: No available caller-IDs`

**Causes:**
1. All caller-IDs are reserved
2. All caller-IDs exceeded usage limits
3. No active caller-IDs in database

**Solutions:**
```bash
# Check Redis reservations
docker exec -it callerid_redis redis-cli KEYS "reservation:*"

# Check database
docker exec -it callerid_postgres psql -U callerid_user -d callerid_db \
  -c "SELECT COUNT(*) FROM caller_ids WHERE is_active = 1;"

# Add more caller-IDs
python3 scripts/bulk_import.py --csv new_caller_ids.csv --method db
```

### Rate Limit Exceeded

**Error:** `429 Too Many Requests`

**Solution:**
Increase rate limits in `.env`:
```bash
DEFAULT_RATE_LIMIT_PER_AGENT=200
```

Restart API:
```bash
docker-compose restart api
```

### API Connection Failed

**Error:** Connection timeout or refused

**Check:**
```bash
# Check if API is running
docker ps | grep callerid_api

# Check logs
docker logs callerid_api

# Test connection
curl http://127.0.0.1:8000/health
```

### Asterisk Can't Reach API

**Solution:**
Ensure Asterisk can reach Docker network:

```bash
# Test from Asterisk server
curl "http://127.0.0.1:8000/next-cid?to=1234567890&campaign=test&agent=test"
```

If using Docker on different host, update `API_URL` in dialplan.

## Performance Optimization

### High Concurrency

For high-volume call centers (100+ simultaneous calls):

1. **Increase Worker Processes**:
   Edit `docker-compose.yml`:
   ```yaml
   command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 8
   ```

2. **Increase Database Pool**:
   Edit `.env`:
   ```bash
   POSTGRES_MAX_CONNECTIONS=200
   ```

3. **Increase Redis Memory**:
   Edit `docker-compose.yml`:
   ```yaml
   command: redis-server --maxmemory 1gb --maxmemory-policy allkeys-lru
   ```

### Monitoring

Monitor API performance:
```bash
# Check response times
curl http://127.0.0.1:8000/api/stats \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"

# Check Redis memory
docker exec callerid_redis redis-cli INFO memory

# Check PostgreSQL connections
docker exec callerid_postgres psql -U callerid_user -d callerid_db \
  -c "SELECT count(*) FROM pg_stat_activity;"
```

## Security Considerations

1. **API Access**: Only bind to `127.0.0.1` (already configured)
2. **Admin Token**: Use strong, random token
3. **Reverse Proxy**: Always use HTTPS via Plesk reverse proxy
4. **Firewall**: Block external access to ports 8000, 5432, 6379
5. **Regular Updates**: Keep Docker images updated

## Support

For issues or questions:
1. Check logs: `docker logs callerid_api`
2. Review dashboard: `https://dialer1.rjimmigrad.com/dashboard`
3. Check health endpoint: `curl http://127.0.0.1:8000/health`
