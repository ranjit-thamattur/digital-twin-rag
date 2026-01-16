#!/bin/bash
# Digital Twin RAG - Complete Startup Script
# This script handles the complete initialization sequence

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DOCKER_DIR="$PROJECT_ROOT/deployment/docker"

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🚀 Self² AI - Complete Startup${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ============================================
# STEP 1: Pre-flight Checks
# ============================================

echo -e "${YELLOW}📋 Step 1: Pre-flight Checks${NC}"
echo ""

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker installed${NC}"

# Check Docker Compose
if ! command -v docker compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}❌ Docker Compose is not installed${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker Compose installed${NC}"

# Check if Docker daemon is running
if ! docker info &> /dev/null; then
    echo -e "${RED}❌ Docker daemon is not running${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker daemon running${NC}"

echo ""

# ============================================
# STEP 2: Directory Setup
# ============================================

echo -e "${YELLOW}📁 Step 2: Creating Required Directories${NC}"
echo ""

cd "$DOCKER_DIR"

# Create directories
mkdir -p pipelines
echo -e "${GREEN}✅ Created: pipelines/${NC}"

mkdir -p lambda
echo -e "${GREEN}✅ Created: lambda/${NC}"

mkdir -p localstack_data
echo -e "${GREEN}✅ Created: localstack_data/${NC}"

echo ""

# ============================================
# STEP 3: Environment Configuration
# ============================================

echo -e "${YELLOW}⚙️  Step 3: Environment Configuration${NC}"
echo ""

if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo -e "${GREEN}✅ Created .env file${NC}"
    echo -e "${BLUE}ℹ️  Review .env file and update if needed${NC}"
else
    echo -e "${GREEN}✅ .env file already exists${NC}"
fi

echo ""

# ============================================
# STEP 4: Stop Existing Containers
# ============================================

echo -e "${YELLOW}🛑 Step 4: Stopping Existing Containers${NC}"
echo ""

if docker compose ps -q 2>/dev/null | grep -q .; then
    echo "Stopping existing containers..."
    docker compose down
    echo -e "${GREEN}✅ Containers stopped${NC}"
else
    echo -e "${GREEN}✅ No existing containers running${NC}"
fi

echo ""

# ============================================
# STEP 5: Start Docker Services
# ============================================

echo -e "${YELLOW}🐳 Step 5: Starting Docker Services${NC}"
echo ""

echo "Starting containers in detached mode..."
docker compose up -d

echo -e "${GREEN}✅ Containers started${NC}"
echo ""

# ============================================
# STEP 6: Wait for Services
# ============================================

echo -e "${YELLOW}⏳ Step 6: Waiting for Services to be Ready${NC}"
echo ""

# Wait for Qdrant
echo -n "Waiting for Qdrant..."
for i in {1..30}; do
    if curl -s http://localhost:6333/collections 2>/dev/null | grep -q "collections"; then
        echo -e " ${GREEN}✅${NC}"
        break
    fi
    echo -n "."
    sleep 2
done

# Wait for Ollama
echo -n "Waiting for Ollama..."
for i in {1..30}; do
    if curl -s http://localhost:11434/api/tags 2>/dev/null | grep -q "models"; then
        echo -e " ${GREEN}✅${NC}"
        break
    fi
    echo -n "."
    sleep 2
done

# Wait for Keycloak
echo -n "Waiting for Keycloak..."
for i in {1..60}; do
    if curl -s http://localhost:8080/health/ready 2>/dev/null | grep -q "UP"; then
        echo -e " ${GREEN}✅${NC}"
        break
    fi
    echo -n "."
    sleep 2
done

# Wait for Tenant Service
echo -n "Waiting for Tenant Service..."
for i in {1..30}; do
    if curl -s http://localhost:8001/health 2>/dev/null | grep -q "healthy"; then
        echo -e " ${GREEN}✅${NC}"
        break
    fi
    echo -n "."
    sleep 2
done

# Wait for n8n
echo -n "Waiting for n8n..."
for i in {1..30}; do
    if curl -s http://localhost:5678 2>/dev/null | grep -q "n8n"; then
        echo -e " ${GREEN}✅${NC}"
        break
    fi
    echo -n "."
    sleep 2
done

# Wait for LocalStack
echo -n "Waiting for LocalStack..."
for i in {1..30}; do
    if curl -s http://localhost:4566/_localstack/health 2>/dev/null | grep -q "running"; then
        echo -e " ${GREEN}✅${NC}"
        break
    fi
    echo -n "."
    sleep 2
done

# Wait for OpenWebUI
echo -n "Waiting for OpenWebUI..."
for i in {1..30}; do
    if curl -s http://localhost:3000 2>/dev/null > /dev/null; then
        echo -e " ${GREEN}✅${NC}"
        break
    fi
    echo -n "."
    sleep 2
done

echo ""

# ============================================
# STEP 7: Run Setup Script
# ============================================

echo -e "${YELLOW}🔧 Step 7: Running Setup Script${NC}"
echo ""

if [ -f "$SCRIPT_DIR/setup/setup_complete.sh" ]; then
    echo "Executing setup_complete.sh..."
    bash "$SCRIPT_DIR/setup/setup_complete.sh"
else
    echo -e "${YELLOW}⚠️  Setup script not found, skipping...${NC}"
fi

echo ""

# ============================================
# STEP 7.5: Setup Keycloak
# ============================================

echo -e "${YELLOW}🔐 Step 7.5: Setting Up Keycloak${NC}"
echo ""

if [ -f "$SCRIPT_DIR/setup/setup_keycloak.sh" ]; then
    echo "Executing setup_keycloak.sh..."
    bash "$SCRIPT_DIR/setup/setup_keycloak.sh"
else
    echo -e "${YELLOW}⚠️  Keycloak setup script not found, skipping...${NC}"
fi

echo ""

# ============================================
# STEP 8: Pull Ollama Models
# ============================================

echo -e "${YELLOW}🤖 Step 8: Checking Ollama Models${NC}"
echo ""

# Check if models are already pulled
EMBEDDING_MODEL="nomic-embed-text"
CHAT_MODEL="llama3.2"

echo "Checking for embedding model: $EMBEDDING_MODEL"
if docker exec ollama ollama list | grep -q "$EMBEDDING_MODEL"; then
    echo -e "${GREEN}✅ $EMBEDDING_MODEL already available${NC}"
else
    echo "Pulling $EMBEDDING_MODEL (this may take a while)..."
    docker exec ollama ollama pull "$EMBEDDING_MODEL"
    echo -e "${GREEN}✅ $EMBEDDING_MODEL pulled${NC}"
fi

echo ""
echo "Checking for chat model: $CHAT_MODEL"
if docker exec ollama ollama list | grep -q "$CHAT_MODEL"; then
    echo -e "${GREEN}✅ $CHAT_MODEL already available${NC}"
else
    echo "Pulling $CHAT_MODEL (this may take a while)..."
    docker exec ollama ollama pull "$CHAT_MODEL"
    echo -e "${GREEN}✅ $CHAT_MODEL pulled${NC}"
fi

echo ""

# ============================================
# STEP 9: Display Status
# ============================================

echo -e "${YELLOW}📊 Step 9: Service Status${NC}"
echo ""

docker compose ps

echo ""

# ============================================
# COMPLETION
# ============================================

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ STARTUP COMPLETE!${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${BLUE}🌐 Access Points:${NC}"
echo ""
echo -e "  ${GREEN}OpenWebUI:${NC}       http://localhost:3000"
echo -e "  ${GREEN}Keycloak Admin:${NC}  http://localhost:8080 (admin/admin)"
echo -e "  ${GREEN}Tenant Service:${NC}  http://localhost:8001"
echo -e "  ${GREEN}n8n:${NC}             http://localhost:5678"
echo -e "  ${GREEN}Qdrant:${NC}          http://localhost:6333/dashboard"
echo -e "  ${GREEN}Ollama:${NC}          http://localhost:11434"
echo -e "  ${GREEN}LocalStack:${NC}      http://localhost:4566"
echo ""
echo -e "${BLUE}📝 Next Steps:${NC}"
echo ""
echo "  1. Configure n8n workflows at http://localhost:5678"
echo "  2. Access OpenWebUI at http://localhost:3000"
echo "  3. Test document upload:"
echo "     aws --endpoint-url=http://localhost:4566 s3 cp test-tenant-123.txt s3://digital-twin-files/tenant-123/persona-cfo/reports/q4.txt"
echo ""
echo -e "${BLUE}🛠️  Useful Commands:${NC}"
echo ""
echo "  View logs:        docker compose logs -f [service-name]"
echo "  Stop services:    docker compose down"
echo "  Restart:          docker compose restart [service-name]"
echo ""
echo -e "${GREEN}Happy coding! 🚀${NC}"
echo ""
