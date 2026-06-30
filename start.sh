#!/bin/bash

# Clarity Agentic App - One-Command Startup Script
# This script handles all setup and startup steps automatically

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo -e "${BLUE}🚀 Clarity Agentic App - Starting...${NC}"
echo ""

# ============================================================================
# STEP 1: Check Docker
# ============================================================================

echo -e "${YELLOW}📦 Checking Docker...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed${NC}"
    echo "Please install Docker Desktop from https://www.docker.com/products/docker-desktop"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo -e "${RED}❌ Docker daemon is not running${NC}"
    echo "Please start Docker Desktop and try again"
    exit 1
fi

echo -e "${GREEN}✅ Docker is running${NC}"
echo ""

# ============================================================================
# STEP 2: Check Environment Configuration
# ============================================================================

echo -e "${YELLOW}⚙️  Checking environment configuration...${NC}"

if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  No .env file found - copying from .env.example${NC}"
    cp .env.example .env
    echo -e "${GREEN}✅ Created .env file${NC}"
    echo ""
    echo -e "${YELLOW}⚠️  IMPORTANT: You need to add your Anthropic API key${NC}"
    echo -e "${YELLOW}   Edit .env and set ANTHROPIC_API_KEY=your-key-here${NC}"
    echo -e "${YELLOW}   Get your key at: https://console.anthropic.com/${NC}"
    echo ""
    read -p "Press Enter after you've added your API key..."
fi

# Validate ANTHROPIC_API_KEY is set
source .env
if [ -z "$ANTHROPIC_API_KEY" ] || [ "$ANTHROPIC_API_KEY" = "sk-ant-xxxxx" ]; then
    echo -e "${RED}❌ ANTHROPIC_API_KEY is not configured${NC}"
    echo ""
    echo "Please edit .env and add your Anthropic API key:"
    echo "  ANTHROPIC_API_KEY=your-actual-key-here"
    echo ""
    echo "Get your key at: https://console.anthropic.com/"
    exit 1
fi

echo -e "${GREEN}✅ Environment configured${NC}"
echo ""

# ============================================================================
# STEP 3: Start Services
# ============================================================================

echo -e "${YELLOW}🐳 Starting Docker services...${NC}"

# Pull latest images (optional, speeds up first start)
docker-compose pull --quiet 2>/dev/null || true

# Start services in detached mode
docker-compose up -d

echo -e "${GREEN}✅ Services started${NC}"
echo ""

# ============================================================================
# STEP 4: Wait for Services to be Healthy
# ============================================================================

echo -e "${YELLOW}⏳ Waiting for services to be ready...${NC}"

# Wait for PostgreSQL
echo -n "  Waiting for PostgreSQL..."
max_attempts=30
attempt=0
until docker-compose exec -T postgres pg_isready -U clarity_user -d clarity_agentic_app > /dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ $attempt -ge $max_attempts ]; then
        echo -e " ${RED}TIMEOUT${NC}"
        echo -e "${RED}❌ PostgreSQL failed to start${NC}"
        echo "Check logs with: docker-compose logs postgres"
        exit 1
    fi
    sleep 1
    echo -n "."
done
echo -e " ${GREEN}✓${NC}"

# Wait for Backend
echo -n "  Waiting for Backend..."
attempt=0
until curl -s http://localhost:8000/health > /dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ $attempt -ge $max_attempts ]; then
        echo -e " ${RED}TIMEOUT${NC}"
        echo -e "${RED}❌ Backend failed to start${NC}"
        echo "Check logs with: docker-compose logs backend"
        exit 1
    fi
    sleep 1
    echo -n "."
done
echo -e " ${GREEN}✓${NC}"

# Wait for Frontend
echo -n "  Waiting for Frontend..."
attempt=0
until curl -s http://localhost:3200 > /dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ $attempt -ge $max_attempts ]; then
        echo -e " ${RED}TIMEOUT${NC}"
        echo -e "${RED}❌ Frontend failed to start${NC}"
        echo "Check logs with: docker-compose logs frontend"
        exit 1
    fi
    sleep 1
    echo -n "."
done
echo -e " ${GREEN}✓${NC}"

echo ""
echo -e "${GREEN}✅ All services are healthy!${NC}"
echo ""

# ============================================================================
# SUCCESS - Show Information
# ============================================================================

echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                                                            ║${NC}"
echo -e "${GREEN}║  🎉 Clarity Agentic App is running!                       ║${NC}"
echo -e "${GREEN}║                                                            ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}📱 Access your app:${NC}"
echo ""
echo -e "  Frontend (UI):        ${GREEN}http://localhost:3200${NC}"
echo -e "  Backend (API):        ${GREEN}http://localhost:8000${NC}"
echo -e "  API Documentation:    ${GREEN}http://localhost:8000/docs${NC}"
echo ""
echo -e "${BLUE}🛠️  Useful commands:${NC}"
echo ""
echo -e "  View logs:            ${YELLOW}docker-compose logs -f${NC}"
echo -e "  Stop services:        ${YELLOW}docker-compose down${NC}"
echo -e "  Restart services:     ${YELLOW}docker-compose restart${NC}"
echo -e "  View database:        ${YELLOW}docker-compose exec postgres psql -U clarity_user -d clarity_agentic_app${NC}"
echo ""
echo -e "${BLUE}📚 Documentation:${NC}"
echo ""
echo -e "  README.md             Complete guide and architecture"
echo -e "  CLAUDE.md             Developer guide (for AI assistants)"
echo -e "  SUBMISSION_REQUIREMENTS.md    Marketplace submission checklist"
echo ""
echo -e "${GREEN}Happy coding! 🚀${NC}"
echo ""
