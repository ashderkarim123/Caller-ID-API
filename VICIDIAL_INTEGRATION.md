# VICIdial Integration Guide

Complete guide for integrating the Caller-ID Rotation API with VICIdial.

## Overview

This guide shows how to integrate the Caller-ID Rotation API with VICIdial's Asterisk dialplan to automatically rotate caller-IDs for outbound calls.

## Prerequisites

- VICIdial installed and configured
- Asterisk running
- Caller-ID Rotation API deployed and accessible
- API URL: `https://dialer1.rjimmigrad.com` (or your domain)

## Integration Methods

### Method 1: Direct Dialplan Integration (Recommended)

This method uses Asterisk's `CURL()` function to call the API directly from the dialplan.

#### Step 1: Edit VICIdial Dialplan

Edit your VICIdial dialplan file (usually `/etc/asterisk/extensions.conf` or VICIdial's custom dialplan):

```ini
[vicidial-auto]
; VICIdial auto-dial context with caller-ID rotation

exten => _X.,1,NoOp(=== Caller-ID Rotation Start ===)
exten => _X.,n,NoOp(Destination: ${EXTEN} | Campaign: ${VICIDIAL_campaign} | Agent: ${AGENT})
exten => _X.,n,Set(API_URL=https://dialer1.rjimmigrad.com/next-cid?to=${EXTEN}&campaign=${VICIDIAL_campaign}&agent=${AGENT})
exten => _X.,n,Set(API_RESPONSE=${CURL(${API_URL})})
exten => _X.,n,NoOp(API Response: ${API_RESPONSE})
exten => _X.,n,Set(CID_NUMBER=${FILTER(0-9,${JSON_DECODE(${API_RESPONSE},caller_id)})})
exten => _X.,n,GotoIf($["${CID_NUMBER}" = ""]?cid_fallback)
exten => _X.,n,Set(CALLERID(num)=${CID_NUMBER})
exten => _X.,n,Set(CALLERID(name)=${CID_NUMBER})
exten => _X.,n,NoOp(✓ Using Rotated Caller-ID: ${CALLERID(num)})
exten => _X.,n,Goto(cid_success)
exten => _X.,n(cid_fallback),NoOp(⚠ API failed, using default caller-ID)
exten => _X.,n,Set(CALLERID(num)=${VICIDIAL_callerid})
exten => _X.,n,Set(CALLERID(name)=${VICIDIAL_callerid})
exten => _X.,n(cid_success),NoOp(=== Proceeding with Call ===)
exten => _X.,n,Dial(${TRUNK}/${EXTEN},,tTo)
exten => _X.,n,Hangup()
```

#### Step 2: Reload Dialplan

```bash
# SSH to VICIdial server
asterisk -rx "dialplan reload"
```

#### Step 3: Test

Make a test call and check Asterisk CLI:

```bash
asterisk -rvvv
# Watch for "Using Rotated Caller-ID: 5551234567"
```

### Method 2: AGI Script Integration

This method uses an AGI script for more complex logic and error handling.

#### Step 1: Create AGI Script

Create `/usr/share/asterisk/agi-bin/get_callerid.sh`:

```bash
#!/bin/bash
# AGI script to get caller-ID from rotation API

# Read AGI variables
while read line; do
    if [ -z "$line" ]; then
        break
    fi
    key=$(echo "$line" | cut -d: -f1 | tr -d ' ')
    value=$(echo "$line" | cut -d: -f2- | sed 's/^ //')
    export "agi_$key"="$value"
done

# Get parameters from dialplan
EXTEN=${agi_extension}
CAMPAIGN=${1:-${VICIDIAL_campaign}}
AGENT=${2:-${AGENT}}

# Call API
API_URL="https://dialer1.rjimmigrad.com/next-cid?to=${EXTEN}&campaign=${CAMPAIGN}&agent=${AGENT}"

# Get response (with timeout)
RESPONSE=$(curl -s -m 5 "${API_URL}")

# Extract caller-ID using grep/sed (simple JSON parsing)
CALLER_ID=$(echo "$RESPONSE" | grep -o '"caller_id":"[^"]*"' | cut -d'"' -f4)

if [ -n "$CALLER_ID" ]; then
    echo "SET VARIABLE CALLERID(num) ${CALLER_ID}"
    echo "SET VARIABLE CALLERID(name) ${CALLER_ID}"
    echo "VERBOSE \"Using Rotated Caller-ID: ${CALLER_ID}\" 1"
    exit 0
else
    echo "VERBOSE \"Failed to get caller-ID from API, using default\" 1"
    exit 1
fi
```

Make executable:

```bash
chmod +x /usr/share/asterisk/agi-bin/get_callerid.sh
```

#### Step 2: Update Dialplan

```ini
[vicidial-auto]
exten => _X.,1,NoOp(Getting caller-ID from rotation API...)
exten => _X.,n,AGI(get_callerid.sh,${VICIDIAL_campaign},${AGENT})
exten => _X.,n,GotoIf($["${AGISTATUS}" != "0"]?cid_fallback)
exten => _X.,n,NoOp(✓ Caller-ID set: ${CALLERID(num)})
exten => _X.,n,Goto(cid_success)
exten => _X.,n(cid_fallback),Set(CALLERID(num)=${VICIDIAL_callerid})
exten => _X.,n(cid_success),Dial(${TRUNK}/${EXTEN},,tTo)
exten => _X.,n,Hangup()
```

### Method 3: Python AGI Script (Advanced)

For more robust JSON parsing and error handling:

Create `/usr/share/asterisk/agi-bin/get_callerid.py`:

```python
#!/usr/bin/env python3
import sys
import urllib.request
import json
import socket

# Read AGI variables
agi_vars = {}
for line in sys.stdin:
    line = line.strip()
    if not line:
        break
    if ':' in line:
        key, value = line.split(':', 1)
        agi_vars[key.strip()] = value.strip()

# Get parameters
exten = agi_vars.get('agi_extension', '')
campaign = sys.argv[1] if len(sys.argv) > 1 else ''
agent = sys.argv[2] if len(sys.argv) > 2 else ''

# Build API URL
api_url = f"https://dialer1.rjimmigrad.com/next-cid?to={exten}&campaign={campaign}&agent={agent}"

try:
    # Call API with timeout
    request = urllib.request.Request(api_url)
    with urllib.request.urlopen(request, timeout=5) as response:
        data = json.loads(response.read().decode('utf-8'))
        caller_id = data.get('caller_id', '')
        
        if caller_id:
            print(f"SET VARIABLE CALLERID(num) {caller_id}")
            print(f"SET VARIABLE CALLERID(name) {caller_id}")
            print(f"VERBOSE \"Using Rotated Caller-ID: {caller_id}\" 1")
            sys.exit(0)
        else:
            print("VERBOSE \"No caller-ID in API response\" 1")
            sys.exit(1)
            
except urllib.error.URLError as e:
    print(f"VERBOSE \"API Error: {e}\" 1")
    sys.exit(1)
except json.JSONDecodeError as e:
    print(f"VERBOSE \"JSON Parse Error: {e}\" 1")
    sys.exit(1)
except Exception as e:
    print(f"VERBOSE \"Unexpected Error: {e}\" 1")
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

## VICIdial Campaign Configuration

### Step 1: Configure Campaign

1. Login to VICIdial web interface
2. Go to **Campaigns** → Select your campaign
3. Ensure **Caller ID** field is set (used as fallback)
4. **Dial Method**: Set to "MANUAL" or "AUTO" as needed

### Step 2: Test Campaign

1. Start a test campaign
2. Make a test call
3. Check Asterisk logs for caller-ID rotation
4. Verify in API dashboard: `https://dialer1.rjimmigrad.com/dashboard`

## Monitoring and Debugging

### Check API Calls

```bash
# View API logs
docker compose logs -f api

# Check recent requests in database
docker compose exec db psql -U callerid_user -d callerid_db \
  -c "SELECT * FROM api_requests ORDER BY created_at DESC LIMIT 10;"
```

### Asterisk Debugging

```bash
# Enable verbose logging
asterisk -rvvv

# Watch for caller-ID rotation messages
# Look for: "Using Rotated Caller-ID: 5551234567"

# Check dialplan
asterisk -rx "dialplan show vicidial-auto"
```

### Test API Manually

```bash
# Test API endpoint
curl "https://dialer1.rjimmigrad.com/next-cid?to=5559876543&campaign=TEST&agent=AGENT001"

# Expected response:
# {"caller_id":"5551234567","carrier":"Verizon","area_code":"555","meta":{}}
```

## Error Handling

### API Unavailable

If the API is unavailable, the dialplan falls back to VICIdial's default caller-ID (`${VICIDIAL_callerid}`). This ensures calls still go through.

### No Available Caller-IDs

If no caller-IDs are available (all at limits or reserved), the API returns:
```json
{"detail": "No available caller-ID found"}
```

The dialplan should handle this and use the fallback caller-ID.

### Timeout Handling

Add timeout to API calls:

```ini
exten => _X.,n,Set(API_RESPONSE=${CURL(${API_URL},5)})
```

Or in AGI script, use `curl -m 5` for 5-second timeout.

## Performance Optimization

### Caching (Optional)

For high-volume campaigns, consider caching caller-IDs per campaign/agent:

```ini
exten => _X.,1,Set(CACHE_KEY=CID_${VICIDIAL_campaign}_${AGENT})
exten => _X.,n,GotoIf($["${CACHE_KEY}" != ""]?check_cache)
exten => _X.,n(check_cache),NoOp(Check cache...)
exten => _X.,n,Set(CID_NUMBER=${CURL(...)})
exten => _X.,n,Set(${CACHE_KEY}=${CID_NUMBER})
```

### Connection Pooling

The API uses connection pooling for database and Redis. For very high volume:
- Increase `pool_size` in `app/db.py`
- Increase Redis `max_connections` in `app/redis_client.py`
- Use multiple API workers in Dockerfile

## Security Considerations

1. **HTTPS Only**: Always use HTTPS for API calls
2. **IP Whitelisting**: Restrict API access to VICIdial server IPs (optional)
3. **Rate Limiting**: API has built-in rate limiting per agent
4. **Token Security**: Keep admin token secure (not needed for `/next-cid` endpoint)

## Troubleshooting

### Caller-ID Not Rotating

1. Check API is accessible from Asterisk server:
   ```bash
   curl https://dialer1.rjimmigrad.com/health
   ```

2. Check dialplan syntax:
   ```bash
   asterisk -rx "dialplan show vicidial-auto"
   ```

3. Check Asterisk logs for errors

### Wrong Caller-ID Used

1. Verify API response in Asterisk logs
2. Check JSON parsing in dialplan
3. Verify fallback logic

### API Timeouts

1. Check network connectivity
2. Increase timeout in dialplan/AGI script
3. Check API server resources

## Advanced Features

### Area Code Matching

The API automatically matches caller-IDs by area code. To force specific area code:

```ini
exten => _X.,n,Set(AREA_CODE=${EXTEN:0:3})
exten => _X.,n,Set(API_URL=...&area_code=${AREA_CODE})
```

### Campaign-Specific Limits

Configure different limits per campaign by using campaign name in API call. The API tracks usage per campaign.

### Real-Time Monitoring

Use the dashboard to monitor:
- Active reservations
- Caller-ID usage
- Campaign statistics
- Recent API requests

Access: `https://dialer1.rjimmigrad.com/dashboard`

---

## Summary

After integration:

1. ✅ API calls VICIdial for each outbound call
2. ✅ Caller-ID rotates based on LRU and limits
3. ✅ Falls back to default if API unavailable
4. ✅ Tracks usage per campaign and agent
5. ✅ Dashboard shows real-time statistics

**Integration Complete!** 🎉
