# API Reference

Complete API documentation for the Caller-ID Rotation API.

## Base URL

- **Local**: `http://127.0.0.1:8000`
- **Production**: `https://dialer1.rjimmigrad.com`

## Authentication

Protected endpoints require an `Authorization` header:

```
Authorization: Bearer YOUR_ADMIN_TOKEN
```

## Endpoints

### GET /

Root endpoint - API information.

**Response:**
```json
{
  "service": "VICIdial Caller-ID Rotation API",
  "version": "1.0.0",
  "status": "running",
  "endpoints": {
    "health": "/health",
    "next_cid": "/next-cid?to=<number>&campaign=<name>&agent=<name>",
    "add_number": "/add-number (POST, requires auth)",
    "dashboard": "/dashboard (requires auth)",
    "stats": "/api/stats (requires auth)"
  }
}
```

---

### GET /health

Health check endpoint.

**Parameters:** None

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-12-05T10:30:00.000Z",
  "database": "healthy",
  "redis": {
    "status": "healthy",
    "connected_clients": 5,
    "used_memory": "1.2M",
    "uptime_seconds": 86400
  },
  "version": "1.0.0"
}
```

**Status Codes:**
- `200 OK` - All systems healthy
- `503 Service Unavailable` - One or more systems unhealthy

---

### GET /next-cid

Get next available caller-ID for a call. Main endpoint used by VICIdial.

**Parameters:**

| Parameter  | Type   | Required | Description                    |
|------------|--------|----------|--------------------------------|
| to         | string | Yes      | Destination phone number       |
| campaign   | string | Yes      | Campaign name                  |
| agent      | string | Yes      | Agent name/ID                  |

**Example Request:**
```bash
curl "http://127.0.0.1:8000/next-cid?to=5555551234&campaign=sales&agent=agent001"
```

**Success Response (200 OK):**
```json
{
  "success": true,
  "caller_id": "2125551234",
  "area_code": "212",
  "carrier": "AT&T",
  "reserved_for": 300,
  "destination": "5555551234",
  "agent": "agent001",
  "campaign": "sales"
}
```

**Error Responses:**

**400 Bad Request** - Invalid parameters:
```json
{
  "detail": "Invalid destination phone number"
}
```

**429 Too Many Requests** - Rate limit exceeded:
```json
{
  "detail": "Rate limit exceeded for agent agent001"
}
```

**503 Service Unavailable** - No caller-IDs available:
```json
{
  "detail": "No available caller-IDs at this time"
}
```

**Algorithm:**
1. Extract area code from destination number
2. Find caller-IDs matching area code (LRU order)
3. Check Redis for existing reservations
4. Check hourly/daily usage limits
5. Reserve caller-ID in Redis with TTL
6. Update database with reservation and last_used
7. Return caller-ID to requester

---

### POST /add-number

Add a new caller-ID to the system.

**Authentication:** Required

**Parameters:**

| Parameter     | Type    | Required | Description                         |
|---------------|---------|----------|-------------------------------------|
| caller_id     | string  | Yes      | Phone number (10-11 digits)         |
| carrier       | string  | No       | Carrier name                        |
| area_code     | string  | No       | Area code (auto-detected if empty)  |
| hourly_limit  | integer | No       | Hourly usage limit (default: 100)   |
| daily_limit   | integer | No       | Daily usage limit (default: 500)    |

**Example Request:**
```bash
curl -X POST "http://127.0.0.1:8000/add-number?caller_id=2125551234&carrier=AT%26T&area_code=212&hourly_limit=100&daily_limit=500" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

**Success Response (200 OK):**
```json
{
  "success": true,
  "message": "Caller-ID 2125551234 added successfully",
  "data": {
    "id": 123,
    "caller_id": "2125551234",
    "carrier": "AT&T",
    "area_code": "212",
    "hourly_limit": 100,
    "daily_limit": 500,
    "last_used": null,
    "created_at": "2024-12-05T10:30:00.000Z",
    "updated_at": "2024-12-05T10:30:00.000Z",
    "is_active": 1,
    "meta": null
  }
}
```

**Error Responses:**

**400 Bad Request** - Invalid caller-ID format:
```json
{
  "detail": "Invalid caller-ID format"
}
```

**409 Conflict** - Caller-ID already exists:
```json
{
  "detail": "Caller-ID 2125551234 already exists"
}
```

**403 Forbidden** - Invalid admin token:
```json
{
  "detail": "Invalid admin token"
}
```

---

### GET /dashboard

Admin dashboard with real-time statistics and caller-ID management.

**Authentication:** Required

**Response:** HTML page with dashboard

**Example Request:**
```bash
curl "http://127.0.0.1:8000/dashboard" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

Access in browser with Authorization header set via browser extension.

**Dashboard Sections:**
- Overview statistics (total/active caller-IDs, reservations)
- Campaign statistics (last 24 hours)
- Active reservations
- Recent caller-IDs
- API request logs
- Redis health status

---

### GET /api/stats

Get API statistics in JSON format.

**Authentication:** Required

**Example Request:**
```bash
curl "http://127.0.0.1:8000/api/stats" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

**Success Response (200 OK):**
```json
{
  "total_caller_ids": 5000,
  "active_caller_ids": 4800,
  "active_reservations": 45,
  "requests_last_hour": 2340,
  "avg_response_time_ms": 42.5,
  "timestamp": "2024-12-05T10:30:00.000Z"
}
```

---

### DELETE /api/reservation/{caller_id}

Manually release a caller-ID reservation.

**Authentication:** Required

**Parameters:**

| Parameter  | Type   | Required | Description                    |
|------------|--------|----------|--------------------------------|
| caller_id  | string | Yes      | Caller-ID to release (in path) |

**Example Request:**
```bash
curl -X DELETE "http://127.0.0.1:8000/api/reservation/2125551234" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

**Success Response (200 OK):**
```json
{
  "success": true,
  "message": "Reservation released for 2125551234",
  "released_from_redis": true
}
```

---

## Error Codes

| Code | Description                                  |
|------|----------------------------------------------|
| 200  | Success                                      |
| 400  | Bad Request - Invalid parameters             |
| 401  | Unauthorized - Missing authentication        |
| 403  | Forbidden - Invalid authentication token     |
| 404  | Not Found - Resource doesn't exist           |
| 409  | Conflict - Resource already exists           |
| 429  | Too Many Requests - Rate limit exceeded      |
| 500  | Internal Server Error                        |
| 503  | Service Unavailable - No caller-IDs available|

## Rate Limiting

### Per-Agent Rate Limit

Default: 100 requests per minute per agent

Configurable via `DEFAULT_RATE_LIMIT_PER_AGENT` environment variable.

When exceeded, endpoint returns `429 Too Many Requests`.

### Per Caller-ID Limits

Each caller-ID has configurable hourly and daily limits:
- **Hourly Limit**: Default 100 calls/hour
- **Daily Limit**: Default 500 calls/day

When exceeded, the caller-ID is skipped in allocation.

## Response Times

Average response times:
- `/health`: < 10ms
- `/next-cid`: < 50ms (depends on database load)
- `/add-number`: < 100ms
- `/dashboard`: < 200ms
- `/api/stats`: < 100ms

## Pagination

Currently not implemented. All list endpoints return full datasets.

Future versions may include pagination for:
- API logs
- Reservations
- Caller-IDs list

## Versioning

Current API version: **1.0.0**

Version is included in health check response.

Future versions will maintain backward compatibility or use URL versioning (e.g., `/api/v2/`).

## Examples

### Python

```python
import requests

# Get next caller-ID
response = requests.get(
    'http://127.0.0.1:8000/next-cid',
    params={
        'to': '5555551234',
        'campaign': 'sales',
        'agent': 'agent001'
    }
)

if response.status_code == 200:
    data = response.json()
    caller_id = data['caller_id']
    print(f"Use caller-ID: {caller_id}")
else:
    print(f"Error: {response.status_code} - {response.text}")

# Add new caller-ID
response = requests.post(
    'http://127.0.0.1:8000/add-number',
    params={
        'caller_id': '2125551234',
        'carrier': 'AT&T',
        'area_code': '212'
    },
    headers={'Authorization': 'Bearer YOUR_ADMIN_TOKEN'}
)

print(response.json())
```

### JavaScript

```javascript
// Get next caller-ID
fetch('http://127.0.0.1:8000/next-cid?to=5555551234&campaign=sales&agent=agent001')
  .then(response => response.json())
  .then(data => {
    console.log('Use caller-ID:', data.caller_id);
  })
  .catch(error => console.error('Error:', error));

// Add new caller-ID
fetch('http://127.0.0.1:8000/add-number?caller_id=2125551234&carrier=AT%26T&area_code=212', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer YOUR_ADMIN_TOKEN'
  }
})
  .then(response => response.json())
  .then(data => console.log(data))
  .catch(error => console.error('Error:', error));
```

### cURL

```bash
# Health check
curl http://127.0.0.1:8000/health

# Get next caller-ID
curl "http://127.0.0.1:8000/next-cid?to=5555551234&campaign=sales&agent=agent001"

# Add caller-ID
curl -X POST "http://127.0.0.1:8000/add-number?caller_id=2125551234" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"

# Get stats
curl "http://127.0.0.1:8000/api/stats" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"

# Release reservation
curl -X DELETE "http://127.0.0.1:8000/api/reservation/2125551234" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

## Webhooks

Not currently supported.

Future versions may include webhook support for:
- Low caller-ID availability alerts
- Rate limit threshold warnings
- Reservation errors

## Support

For API support:
1. Check logs: `docker logs callerid_api`
2. Test health: `/health` endpoint
3. Review documentation
4. Check dashboard for diagnostics
