#!/bin/bash
# Check if the API is ready for E2E testing

API_URL="${API_URL:?API_URL is required}"

# Check if API is reachable
HEALTH_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/health" 2>/dev/null)

if [ "$HEALTH_RESPONSE" != "200" ]; then
  echo "❌ API is not reachable at $API_URL"
  echo "   Health endpoint returned HTTP $HEALTH_RESPONSE"
  exit 1
fi

# Get health data
HEALTH_DATA=$(curl -s "$API_URL/health" 2>/dev/null)

# Parse environment
ENVIRONMENT=$(echo "$HEALTH_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin).get('environment', 'unknown'))" 2>/dev/null)

if [ "$ENVIRONMENT" != "e2e" ]; then
  echo "❌ API is NOT in E2E mode"
  echo "   Current environment: $ENVIRONMENT"
  echo "   Expected: e2e"
  echo ""
  echo "   The API may be:"
  echo "   - Running in development/production mode"
  echo "   - Running other tests"
  echo "   - Not properly configured"
  echo ""
  echo "   Please ensure the API is started in E2E mode before running tests."
  exit 1
fi

echo "✅ API is ready for E2E testing"
echo "   Environment: $ENVIRONMENT"
echo "   URL: $API_URL"
exit 0
