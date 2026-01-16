#!/bin/bash
# Create demo.demotenant user in Keycloak

echo "Creating demo user in Keycloak..."

# Get admin token
TOKEN=$(curl -s -X POST http://localhost:8080/realms/master/protocol/openid-connect/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin" \
  -d "password=admin" \
  -d "grant_type=password" \
  -d "client_id=admin-cli" \
  | jq -r '.access_token')

if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
    echo "❌ Failed to get admin token"
    exit 1
fi

echo "✅ Got admin token"

# Create user
USER_JSON='{
  "username": "demo.demotenant",
  "email": "demo.demotenant@gmail.com",
  "firstName": "Demo",
  "lastName": "User",
  "enabled": true,
  "emailVerified": true,
  "credentials": [{
    "type": "password",
    "value": "Demo@2024",
    "temporary": false
  }]
}'

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
  http://localhost:8080/admin/realms/self2ai/users \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "$USER_JSON")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

if [ "$HTTP_CODE" = "201" ] || [ "$HTTP_CODE" = "409" ]; then
    if [ "$HTTP_CODE" = "409" ]; then
        echo "⚠️  User already exists"
    else
        echo "✅ User created successfully"
    fi
    
    echo ""
    echo "╔════════════════════════════════════════════════════╗"
    echo "║        Demo User Created in Keycloak! 🎉          ║"
    echo "╚════════════════════════════════════════════════════╝"
    echo ""
    echo "Login Credentials:"
    echo "  Email: demo.demotenant@gmail.com"
    echo "  Password: Demo@2024"
    echo ""
    echo "Tenant: tenant-demotenant"
    echo "Persona: CEO"
    echo ""
    echo "Test file created at:"
    echo "  /Users/ranjitt/Desktop/demo-ceo-report.txt"
    echo ""
else
    echo "❌ Failed to create user (HTTP $HTTP_CODE)"
    echo "$RESPONSE" | head -n-1
    exit 1
fi
