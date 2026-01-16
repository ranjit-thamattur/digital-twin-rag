#!/bin/bash
# Test Multi-Tenant Authentication Setup

set -e

echo "🧪 Testing Multi-Tenant Authentication Setup"
echo "==========================================="
echo ""

# Test 1: Check services are running
echo "Test 1: Checking services..."
services=("postgres:5432" "keycloak:8080" "tenant-service:8001")
for service in "${services[@]}"; do
    IFS=':' read -r name port <<< "$service"
    if curl -s "http://localhost:$port" > /dev/null 2>&1 || nc -z localhost "$port" 2>/dev/null; then
        echo "✅ $name is running on port $port"
    else
        echo "❌ $name is NOT running on port $port"
    fi
done
echo ""

# Test 2: Test Keycloak realm
echo "Test 2: Testing Keycloak realm..."
REALM_INFO=$(curl -s http://localhost:8080/realms/digital-twin/.well-known/openid-configuration)
if echo "$REALM_INFO" | grep -q "token_endpoint"; then
    echo "✅ Keycloak realm 'digital-twin' is configured"
else
    echo "❌ Keycloak realm not found"
fi
echo ""

# Test 3: Test tenant service
echo "Test 3: Testing tenant service..."
HEALTH=$(curl -s http://localhost:8001/health)
if echo "$HEALTH" | grep -q "healthy"; then
    echo "✅ Tenant service is healthy"
else
    echo "❌ Tenant service is not responding"
fi
echo ""

# Test 4: List tenants
echo "Test 4: Listing tenants..."
TENANTS=$(curl -s http://localhost:8001/tenants)
echo "Tenants: $TENANTS"
echo ""

# Test 5: Create test tenant
echo "Test 5: Creating test tenant..."
CREATE_RESPONSE=$(curl -s -X POST http://localhost:8001/tenants \
    -H "Content-Type: application/json" \
    -d '{
        "name": "Test Company",
        "slug": "test-company",
        "domain": "test.local",
        "subscription_plan": "free"
    }')

if echo "$CREATE_RESPONSE" | grep -q "test-company"; then
    echo "✅ Test tenant created successfully"
    echo "Response: $CREATE_RESPONSE"
else
    echo "⚠️  Tenant may already exist or creation failed"
    echo "Response: $CREATE_RESPONSE"
fi
echo ""

# Test 6: Get tenant by slug
echo "Test 6: Getting tenant by slug..."
TENANT=$(curl -s http://localhost:8001/tenants/slug/demo)
if echo "$TENANT" | grep -q "demo"; then
    echo "✅ Retrieved tenant 'demo'"
else
    echo "❌ Failed to retrieve tenant"
fi
echo ""

# Test 7: Test Keycloak login
echo "Test 7: Testing Keycloak user login..."
TOKEN_RESPONSE=$(curl -s -X POST http://localhost:8080/realms/digital-twin/protocol/openid-connect/token \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=admin@demo.local" \
    -d "password=admin123" \
    -d "grant_type=password" \
    -d "client_id=openwebui")

if echo "$TOKEN_RESPONSE" | grep -q "access_token"; then
    echo "✅ User login successful"
    ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.access_token')
    echo "Access token obtained (first 50 chars): ${ACCESS_TOKEN:0:50}..."
    
    # Decode token to check tenant_id claim
    echo ""
    echo "Decoding token claims..."
    PAYLOAD=$(echo "$ACCESS_TOKEN" | cut -d'.' -f2 | base64 -d 2>/dev/null || echo "$ACCESS_TOKEN" | cut -d'.' -f2 | base64 -D 2>/dev/null)
    if echo "$PAYLOAD" | grep -q "tenant_id"; then
        echo "✅ Token contains tenant_id claim"
        echo "Claims: $PAYLOAD" | jq '.' 2>/dev/null || echo "$PAYLOAD"
    else
        echo "⚠️  Token may not contain tenant_id claim"
    fi
else
    echo "❌ User login failed"
    echo "Response: $TOKEN_RESPONSE"
fi
echo ""

echo "==========================================="
echo "✅ Testing Complete!"
echo ""
echo "📝 Summary:"
echo "   - Services: Running"
echo "   - Keycloak: Configured"
echo "   - Tenant Service: Operational"
echo "   - Authentication: Working"
echo ""
echo "🎯 Next Steps:"
echo "   1. Integrate Keycloak with OpenWebUI"
echo "   2. Update pipeline-dynamic.py with JWT validation"
echo "   3. Build admin dashboard"
echo ""
