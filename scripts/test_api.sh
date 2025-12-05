#!/bin/bash
# Test script for Caller-ID Rotation API

set -e

API_URL="${API_URL:-http://127.0.0.1:8000}"
ADMIN_TOKEN="${ADMIN_TOKEN:-}"

echo "=========================================="
echo "Caller-ID Rotation API Test Script"
echo "=========================================="
echo ""
echo "API URL: $API_URL"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test function
test_endpoint() {
    local name="$1"
    local method="$2"
    local endpoint="$3"
    local expected_status="$4"
    local extra_args="${5:-}"
    
    echo -n "Testing $name... "
    
    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" $extra_args "$API_URL$endpoint")
    else
        response=$(curl -s -w "\n%{http_code}" -X $method $extra_args "$API_URL$endpoint")
    fi
    
    status=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)
    
    if [ "$status" = "$expected_status" ]; then
        echo -e "${GREEN}✓ PASS${NC} (Status: $status)"
        if [ -n "$body" ]; then
            echo "  Response: $body" | head -c 200
            echo ""
        fi
    else
        echo -e "${RED}✗ FAIL${NC} (Expected: $expected_status, Got: $status)"
        if [ -n "$body" ]; then
            echo "  Response: $body"
        fi
    fi
    echo ""
}

# 1. Test root endpoint
test_endpoint "Root endpoint" "GET" "/" "200"

# 2. Test health check
test_endpoint "Health check" "GET" "/health" "200"

# 3. Test next-cid without parameters (should fail)
test_endpoint "next-cid without params (should fail)" "GET" "/next-cid" "422"

# 4. Test next-cid with valid parameters
test_endpoint "next-cid with valid params" "GET" "/next-cid?to=5555551234&campaign=test&agent=test_agent" "200"

# 5. Test add-number without auth (should fail)
test_endpoint "add-number without auth (should fail)" "POST" "/add-number?caller_id=2125551234" "403"

# 6. Test add-number with auth (if token provided)
if [ -n "$ADMIN_TOKEN" ]; then
    test_endpoint "add-number with auth" "POST" "/add-number?caller_id=2125559999&carrier=Test&area_code=212" "200" "-H 'Authorization: Bearer $ADMIN_TOKEN'"
    
    test_endpoint "stats endpoint" "GET" "/api/stats" "200" "-H 'Authorization: Bearer $ADMIN_TOKEN'"
else
    echo -e "${YELLOW}⚠ Skipping authenticated tests (ADMIN_TOKEN not set)${NC}"
    echo ""
fi

# 7. Test invalid endpoint (should 404)
test_endpoint "Invalid endpoint (should 404)" "GET" "/invalid-endpoint" "404"

echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo ""
echo "API URL: $API_URL"
echo "Tests completed!"
echo ""
echo "To run with authentication:"
echo "  ADMIN_TOKEN=your_token ./scripts/test_api.sh"
echo ""
