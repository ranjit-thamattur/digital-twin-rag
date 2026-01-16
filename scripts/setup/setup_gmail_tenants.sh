#!/bin/bash

# Self² AI - Gmail-Based Multi-Tenant Setup
# Creates TenantA and TenantB with Gmail user accounts

set -e

KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:8080}"
REALM_NAME="${KEYCLOAK_REALM:-self2ai}"
ADMIN_USER="${KEYCLOAK_ADMIN:-admin}"
ADMIN_PASS="${KEYCLOAK_ADMIN_PASSWORD:-admin}"

echo "🔐 Self² AI - Gmail Multi-Tenant Setup"
echo "========================================"
echo ""

# Get admin token
echo "🔑 Getting admin access token..."
ADMIN_TOKEN=$(curl -s -X POST "$KEYCLOAK_URL/realms/master/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=$ADMIN_USER" \
    -d "password=$ADMIN_PASS" \
    -d 'grant_type=password' \
    -d 'client_id=admin-cli' | jq -r '.access_token')

if [ -z "$ADMIN_TOKEN" ] || [ "$ADMIN_TOKEN" = "null" ]; then
    echo "❌ Failed to get admin token"
    exit 1
fi

echo "✅ Admin token obtained"
echo ""

# Function to create user with tenant_id
create_tenant_user() {
    local EMAIL=$1
    local PASSWORD=$2
    local TENANT_ID=$3
    local FIRST_NAME=$4
    local LAST_NAME=$5
    
    echo "👤 Creating user: $EMAIL (tenant: $TENANT_ID)"
    
    # Check if user exists
    USER_EXISTS=$(curl -s -X GET "$KEYCLOAK_URL/admin/realms/$REALM_NAME/users?email=$EMAIL" \
        -H "Authorization: Bearer $ADMIN_TOKEN" | jq '. | length')
    
    if [ "$USER_EXISTS" -gt 0 ]; then
        echo "   ⚠️  User already exists, updating..."
        USER_ID=$(curl -s -X GET "$KEYCLOAK_URL/admin/realms/$REALM_NAME/users?email=$EMAIL" \
            -H "Authorization: Bearer $ADMIN_TOKEN" | jq -r '.[0].id')
    else
        # Create user
        curl -s -X POST "$KEYCLOAK_URL/admin/realms/$REALM_NAME/users" \
            -H "Authorization: Bearer $ADMIN_TOKEN" \
            -H "Content-Type: application/json" \
            -d "{
                \"username\": \"$EMAIL\",
                \"email\": \"$EMAIL\",
                \"firstName\": \"$FIRST_NAME\",
                \"lastName\": \"$LAST_NAME\",
                \"enabled\": true,
                \"emailVerified\": true,
                \"attributes\": {
                    \"tenant_id\": [\"$TENANT_ID\"]
                }
            }" > /dev/null
        
        # Get user ID
        sleep 1
        USER_ID=$(curl -s -X GET "$KEYCLOAK_URL/admin/realms/$REALM_NAME/users?email=$EMAIL" \
            -H "Authorization: Bearer $ADMIN_TOKEN" | jq -r '.[0].id')
    fi
    
    if [ -z "$USER_ID" ] || [ "$USER_ID" = "null" ]; then
        echo "   ❌ Failed to create/find user"
        return 1
    fi
    
    # Update tenant_id attribute
    curl -s -X PUT "$KEYCLOAK_URL/admin/realms/$REALM_NAME/users/$USER_ID" \
        -H "Authorization: Bearer $ADMIN_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"attributes\": {
                \"tenant_id\": [\"$TENANT_ID\"]
            }
        }" > /dev/null
    
    # Set password
    curl -s -X PUT "$KEYCLOAK_URL/admin/realms/$REALM_NAME/users/$USER_ID/reset-password" \
        -H "Authorization: Bearer $ADMIN_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"type\": \"password\",
            \"value\": \"$PASSWORD\",
            \"temporary\": false
        }" > /dev/null
    
    echo "   ✅ User created with tenant_id=$TENANT_ID"
}

echo "🏢 Creating TenantA Users"
echo "-------------------------"
create_tenant_user "alice.tenantA@gmail.com" "password123" "tenantA" "Alice" "TenantA"
create_tenant_user "bob.tenantA@gmail.com" "password123" "tenantA" "Bob" "TenantA"
echo ""

echo "🏢 Creating TenantB Users"
echo "-------------------------"
create_tenant_user "charlie.tenantB@gmail.com" "password123" "tenantB" "Charlie" "TenantB"
create_tenant_user "diana.tenantB@gmail.com" "password123" "tenantB" "Diana" "TenantB"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ GMAIL MULTI-TENANT SETUP COMPLETE!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "👥 TenantA Users:"
echo "   📧 alice.tenantA@gmail.com / password123"
echo "   📧 bob.tenantA@gmail.com / password123"
echo ""
echo "👥 TenantB Users:"
echo "   📧 charlie.tenantB@gmail.com / password123"
echo "   📧 diana.tenantB@gmail.com / password123"
echo ""
echo "🌐 Login at: http://localhost:3000"
echo "   Click 'Sign in with Keycloak'"
echo ""
echo "📝 Next Steps:"
echo "   1. Login with any Gmail user"
echo "   2. Select 'Self² AI RAG' model"
echo "   3. Upload documents (isolated per tenant)"
echo "   4. Query - only see your tenant's data"
