#!/bin/bash

# 🎬 BROWNS SOCIAL MEDIA APP - ONE-CLICK LAUNCHER
# This script sets up and launches the entire application

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Paths
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NODE_MODULES="$APP_DIR/node_modules"
ENV_FILE="$APP_DIR/.env.local"

echo -e "${BLUE}"
echo "╔════════════════════════════════════════════════════╗"
echo "║     🎬 BROWNS SOCIAL MEDIA APP - LAUNCHER          ║"
echo "║     AI-Powered Video Synthesis Platform            ║"
echo "╚════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Step 1: Check Node.js
echo -e "${YELLOW}[1/5] Checking Node.js...${NC}"
if ! command -v node &> /dev/null; then
    echo -e "${RED}✗ Node.js not found!${NC}"
    echo "Install from: https://nodejs.org/"
    exit 1
fi
NODE_VERSION=$(node -v)
echo -e "${GREEN}✓ Node.js $NODE_VERSION found${NC}"

# Step 2: Check dependencies
echo -e "${YELLOW}[2/5] Checking dependencies...${NC}"
if [ ! -d "$NODE_MODULES" ]; then
    echo -e "${YELLOW}Installing npm packages...${NC}"
    cd "$APP_DIR"
    npm install
    echo -e "${GREEN}✓ Dependencies installed${NC}"
else
    echo -e "${GREEN}✓ Dependencies already installed${NC}"
fi

# Step 3: Check environment variables
echo -e "${YELLOW}[3/5] Checking configuration...${NC}"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}Creating .env.local from template...${NC}"
    if [ -f "$APP_DIR/.env.example" ]; then
        cp "$APP_DIR/.env.example" "$ENV_FILE"
        echo -e "${YELLOW}⚠ Note: Update .env.local with your API keys${NC}"
        echo -e "${YELLOW}   Edit: $ENV_FILE${NC}"
    fi
fi
echo -e "${GREEN}✓ Configuration ready${NC}"

# Step 4: Build Next.js app
echo -e "${YELLOW}[4/5] Building application...${NC}"
cd "$APP_DIR"
if [ ! -d ".next" ]; then
    npm run build
    echo -e "${GREEN}✓ Build complete${NC}"
else
    echo -e "${GREEN}✓ Build cache found${NC}"
fi

# Step 5: Start the app
echo -e "${YELLOW}[5/5] Starting application...${NC}"
echo -e "${GREEN}"
echo "╔════════════════════════════════════════════════════╗"
echo "║                                                    ║"
echo "║  ✅ APPLICATION STARTING                           ║"
echo "║                                                    ║"
echo "║  📱 Open your browser and go to:                   ║"
echo "║     👉 http://localhost:3000                       ║"
echo "║                                                    ║"
echo "║  Ready to create amazing videos! 🎬              ║"
echo "║                                                    ║"
echo "╚════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Start the server
cd "$APP_DIR"
npm run dev
