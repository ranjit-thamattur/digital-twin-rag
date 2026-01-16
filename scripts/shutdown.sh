#!/bin/bash
# Self² AI - Shutdown Script
# Gracefully stops all services

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DOCKER_DIR="$PROJECT_ROOT/deployment/docker"

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🛑 Self² AI - Shutdown${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

cd "$DOCKER_DIR"

# Check if containers are running
if docker compose ps -q 2>/dev/null | grep -q .; then
    echo -e "${YELLOW}Stopping containers...${NC}"
    echo ""
    
    docker compose down
    
    echo ""
    echo -e "${GREEN}✅ All services stopped${NC}"
else
    echo -e "${YELLOW}⚠️  No containers are currently running${NC}"
fi

echo ""
echo -e "${BLUE}To remove volumes as well, run:${NC}"
echo "  docker compose down -v"
echo ""
