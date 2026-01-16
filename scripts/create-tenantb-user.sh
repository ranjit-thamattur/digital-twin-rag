#!/bin/bash
# Create TenantB user in Keycloak

KEYCLOAK_URL="http://localhost:8080"
REALM="self2ai"
ADMIN_USER="admin"
ADMIN_PASS="admin"

echo "Creating user: ranjit@tenantb"

# Get admin token
TOKEN=$(curl -s -X POST "$KEYCLOAK_URL/realms/master/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=$ADMIN_USER" \
  -d "password=$ADMIN_PASS" \
  -d "grant_type=password" \
  -d "client_id=admin-cli" \
  | jq -r '.access_token')

if [ -z "$TOKEN" ] || [ "$TOKEN" == "null" ]; then
  echo "❌ Failed to get admin token"
  exit 1
fi

echo "✅ Got admin token"

# Create user
USER_RESPONSE=$(curl -s -X POST "$KEYCLOAK_URL/admin/realms/$REALM/users" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "ranjit@tenantb",
    "email": "ranjit@tenantb",
    "enabled": true,
    "emailVerified": true,
    "firstName": "Ranjit",
    "lastName": "TenantB"
  }' -w "%{http_code}" -o /dev/null)

if [ "$USER_RESPONSE" -eq 201 ] || [ "$USER_RESPONSE" -eq 409 ]; then
  echo "✅ User created or already exists"
else
  echo "❌ Failed to create user (HTTP $USER_RESPONSE)"
  exit 1
fi

# Get user ID
USER_ID=$(curl -s "$KEYCLOAK_URL/admin/realms/$REALM/users?username=ranjit@tenantb" \
  -H "Authorization: Bearer $TOKEN" \
  | jq -r '.[0].id')

if [ -z "$USER_ID" ] || [ "$USER_ID" == "null" ]; then
  echo "❌ Failed to get user ID"
  exit 1
fi

echo "✅ User ID: $USER_ID"

# Set password
curl -s -X PUT "$KEYCLOAK_URL/admin/realms/$REALM/users/$USER_ID/reset-password" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "password",
    "value": "password123",
    "temporary": false
  }'

echo "✅ Password set: password123"

# Assign user role
curl -s -X POST "$KEYCLOAK_URL/admin/realms/$REALM/users/$USER_ID/role-mappings/realm" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '[{
    "name": "user"
  }]'

echo "✅ Role assigned: user"

echo ""
echo "=========================================="
echo "✅ TenantB User Created!"
echo "=========================================="
echo "Email:    ranjit@tenantb"
echo "Password: password123"
echo "Tenant:   tenant-tenantb (auto-extracted)"
echo "=========================================="
echo ""
echo "Login at: http://localhost:3000"
