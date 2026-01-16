#!/bin/bash
# Keycloak Setup Script - Configure realm and client for multi-tenant auth

set -e

KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:8080}"
ADMIN_USER="${KEYCLOAK_ADMIN:-admin}"
ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
REALM_NAME="${KEYCLOAK_REALM:-self2ai}"
CLIENT_ID="${KEYCLOAK_CLIENT_ID:-openwebui}"

echo "🔐 Self² AI - Keycloak Setup"
echo "========================================"
echo ""
echo "Keycloak URL: $KEYCLOAK_URL"
echo "Realm: $REALM_NAME"
echo "Client: $CLIENT_ID"
echo ""

# Wait for Keycloak to be ready
echo "⏳ Waiting for Keycloak..."
for i in {1..60}; do
    if curl -s "$KEYCLOAK_URL/health/ready" | grep -q "UP"; then
        echo "✅ Keycloak is ready!"
        break
    fi
    echo -n "."
    sleep 2
done
echo ""

# Get admin token
echo "🔑 Getting admin access token..."
ADMIN_TOKEN=$(curl -s -X POST "$KEYCLOAK_URL/realms/master/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=$ADMIN_USER" \
    -d "password=$ADMIN_PASSWORD" \
    -d "grant_type=password" \
    -d "client_id=admin-cli" | jq -r '.access_token')

if [ "$ADMIN_TOKEN" == "null" ] || [ -z "$ADMIN_TOKEN" ]; then
    echo "❌ Failed to get admin token"
    exit 1
fi
echo "✅ Admin token obtained"
echo ""

# Create realm
echo "🏢 Creating realm: $REALM_NAME"
REALM_EXISTS=$(curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
    "$KEYCLOAK_URL/admin/realms/$REALM_NAME" | jq -r '.realm // empty')
if [ -z "$REALM_EXISTS" ]; then
    curl -s -X POST "$KEYCLOAK_URL/admin/realms" \
        -H "Authorization: Bearer $ADMIN_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"realm\": \"$REALM_NAME\",
            \"enabled\": true,
            \"sslRequired\": "none",
            \"displayName\": \"Digital Twin Multi-Tenant\",
            \"registrationAllowed\": true,
            \"loginWithEmailAllowed\": true,
            \"duplicateEmailsAllowed\": false,
            \"resetPasswordAllowed\": true,
            \"editUsernameAllowed\": false,
            \"bruteForceProtected\": true
        }" > /dev/null
    echo "✅ Realm created: $REALM_NAME"
else
    echo "✅ Realm already exists: $REALM_NAME"
fi
echo ""

# Create client
echo "📱 Creating client: $CLIENT_ID"
CLIENT_EXISTS=$(curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
    "$KEYCLOAK_URL/admin/realms/$REALM_NAME/clients?clientId=$CLIENT_ID" | jq -r '.[0].id // empty')

if [ -z "$CLIENT_EXISTS" ]; then
    curl -s -X POST "$KEYCLOAK_URL/admin/realms/$REALM_NAME/clients" \
        -H "Authorization: Bearer $ADMIN_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"clientId\": \"$CLIENT_ID\",
            \"name\": \"OpenWebUI\",
            \"description\": \"OpenWebUI Multi-Tenant Client\",
            \"enabled\": true,
            \"publicClient\": false,
            \"protocol\": \"openid-connect\",
            \"directAccessGrantsEnabled\": true,
            \"serviceAccountsEnabled\": true,
            \"authorizationServicesEnabled\": false,
            \"standardFlowEnabled\": true,
            \"implicitFlowEnabled\": false,
            \"redirectUris\": [
                \"http://localhost:3000/*\",
                \"http://localhost:8000/*\"
            ],
            \"webOrigins\": [\"+\"],
            \"attributes\": {
                \"access.token.lifespan\": \"3600\"
            }
        }" > /dev/null
    echo "✅ Client created: $CLIENT_ID"
    
    # Get client secret
    sleep 2
    CLIENT_ID_UUID=$(curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
        "$KEYCLOAK_URL/admin/realms/$REALM_NAME/clients?clientId=$CLIENT_ID" | jq -r '.[0].id')
    
    CLIENT_SECRET=$(curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
        "$KEYCLOAK_URL/admin/realms/$REALM_NAME/clients/$CLIENT_ID_UUID/client-secret" | jq -r '.value')
    
    echo ""
    echo "🔐 Client Secret: $CLIENT_SECRET"
    echo "⚠️  Save this secret! Update KEYCLOAK_CLIENT_SECRET in .env"
    echo ""
else
    echo "✅ Client already exists: $CLIENT_ID"
fi
echo ""

# Create tenant_id mapper
echo "🗺️  Creating tenant_id claim mapper..."
CLIENT_ID_UUID=$(curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
    "$KEYCLOAK_URL/admin/realms/$REALM_NAME/clients?clientId=$CLIENT_ID" | jq -r '.[0].id')

curl -s -X POST "$KEYCLOAK_URL/admin/realms/$REALM_NAME/clients/$CLIENT_ID_UUID/protocol-mappers/models" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "name": "tenant_id",
        "protocol": "openid-connect",
        "protocolMapper": "oidc-usermodel-attribute-mapper",
        "config": {
            "user.attribute": "tenant_id",
            "claim.name": "tenant_id",
            "jsonType.label": "String",
            "id.token.claim": "true",
            "access.token.claim": "true",
            "userinfo.token.claim": "true"
        }
    }' > /dev/null 2>&1 || echo "Mapper may already exist"

echo "✅ Tenant ID mapper configured"
echo ""

# Create test users
echo "👤 Creating test users..."

# Admin user
curl -s -X POST "$KEYCLOAK_URL/admin/realms/$REALM_NAME/users" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "username": "admin@demo.local",
        "email": "admin@demo.local",
        "firstName": "Admin",
        "lastName": "User",
        "enabled": true,
        "emailVerified": true,
        "attributes": {
            "tenant_id": ["demo"]
        },
        "credentials": [{
            "type": "password",
            "value": "admin123",
            "temporary": false
        }]
    }' > /dev/null 2>&1 || echo "Admin user may already exist"

# Regular user
curl -s -X POST "$KEYCLOAK_URL/admin/realms/$REALM_NAME/users" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "username": "user@demo.local",
        "email": "user@demo.local",
        "firstName": "Demo",
        "lastName": "User",
        "enabled": true,
        "emailVerified": true,
        "attributes": {
            "tenant_id": ["demo"]
        },
        "credentials": [{
            "type": "password",
            "value": "user123",
            "temporary": false
        }]
    }' > /dev/null 2>&1 || echo "Demo user may already exist"

echo "✅ Test users created"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ KEYCLOAK SETUP COMPLETE!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🌐 Access Points:"
echo "   Keycloak Admin: $KEYCLOAK_URL"
echo "   Username: $ADMIN_USER"
echo "   Password: $ADMIN_PASSWORD"
echo ""
echo "👤 Test Users:"
echo "   Admin: admin@demo.local / admin123"
echo "   User:  user@demo.local / user123"
echo ""
echo "🔗 OIDC Endpoints:"
echo "   Discovery: $KEYCLOAK_URL/realms/$REALM_NAME/.well-known/openid-configuration"
echo "   Token:     $KEYCLOAK_URL/realms/$REALM_NAME/protocol/openid-connect/token"
echo ""
echo "📝 Next Steps:"
echo "   1. Update .env with KEYCLOAK_CLIENT_SECRET"
echo "   2. Test login at http://localhost:3000"
echo "   3. Create additional tenants via tenant service"
echo ""
