#!/bin/bash
# PostgreSQL Tenant Verification Guide

echo "========================================="
echo "PostgreSQL Tenant Database Verification"
echo "========================================="
echo ""

# Method 1: Via tenant-service container
echo "Method 1: Using tenant-service container"
echo "-----------------------------------------"
echo ""
echo "# View all tenants:"
docker exec tenant-service-dt psql postgresql://keycloak:keycloak_password@postgres:5432/postgres -c "SELECT tenant_id, company_name, industry, is_active, created_at FROM tenants ORDER BY created_at DESC;"

echo ""
echo "# View all tenant users:"
docker exec tenant-service-dt psql postgresql://keycloak:keycloak_password@postgres:5432/postgres -c "SELECT email, tenant_id, persona, is_active FROM tenant_users ORDER BY tenant_id;"

echo ""
echo "# View MedPlus tenant specifically:"
docker exec tenant-service-dt psql postgresql://keycloak:keycloak_password@postgres:5432/postgres -c "SELECT * FROM tenants WHERE tenant_id = 'tenant-medplus';"

echo ""
echo "# View MedPlus users:"
docker exec tenant-service-dt psql postgresql://keycloak:keycloak_password@postgres:5432/postgres -c "SELECT * FROM tenant_users WHERE tenant_id = 'tenant-medplus';"

echo ""
echo "# View personas for a tenant:"
docker exec tenant-service-dt psql postgresql://keycloak:keycloak_password@postgres:5432/postgres -c "SELECT * FROM tenant_personas WHERE tenant_id = 'tenant-medplus';"

echo ""
echo "========================================="
echo "Quick Stats"
echo "========================================="
docker exec tenant-service-dt psql postgresql://keycloak:keycloak_password@postgres:5432/postgres -c "
SELECT 
    (SELECT COUNT(*) FROM tenants) as total_tenants,
    (SELECT COUNT(*) FROM tenant_users) as total_users,
    (SELECT COUNT(*) FROM tenant_personas) as total_personas;
"

echo ""
echo "Done!"
