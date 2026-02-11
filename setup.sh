#!/bin/bash

###############################################################################
# INSTANT SETUP - Get Your 3 Streamlit URLs Running
# Run this once, then use start_all.sh to start the apps
###############################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   EdusCore Analytics - First Time Setup                   ║${NC}"
echo -e "${BLUE}║   Setting up your 3 Streamlit URLs...                     ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check Python
echo -e "${YELLOW}Checking Python...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 is not installed!${NC}"
    echo "Please install Python 3.8 or higher"
    exit 1
fi
echo -e "${GREEN}✓ Python found: $(python3 --version)${NC}"
echo ""

# Check pip
echo -e "${YELLOW}Checking pip...${NC}"
if ! command -v pip3 &> /dev/null && ! command -v pip &> /dev/null; then
    echo -e "${RED}❌ pip is not installed!${NC}"
    echo "Please install pip"
    exit 1
fi
echo -e "${GREEN}✓ pip found${NC}"
echo ""

# Install dependencies
echo -e "${YELLOW}Installing dependencies (this may take 1-2 minutes)...${NC}"
pip3 install -q streamlit pandas 2>&1 | tail -5 || pip install -q streamlit pandas 2>&1 | tail -5
echo -e "${GREEN}✓ Streamlit installed${NC}"

pip3 install -q -r requirements.txt 2>&1 | tail -5 || pip install -q -r requirements.txt 2>&1 | tail -5
echo -e "${GREEN}✓ All dependencies installed${NC}"
echo ""

# Make scripts executable
echo -e "${YELLOW}Setting up scripts...${NC}"
chmod +x start_all.sh 2>/dev/null || true
chmod +x stop_all.sh 2>/dev/null || true
echo -e "${GREEN}✓ Scripts ready${NC}"
echo ""

# Success message
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ SETUP COMPLETE!${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Next step: Start your 3 Streamlit URLs${NC}"
echo ""
echo -e "Run this command:"
echo -e "  ${GREEN}./start_all.sh${NC}"
echo ""
echo -e "Then open your browser to:"
echo -e "  • ${BLUE}http://localhost:5000${NC}  (Main App)"
echo -e "  • ${BLUE}http://localhost:5001${NC}  (Admin Dashboard)"
echo -e "  • ${BLUE}http://localhost:5002${NC}  (Parents Portal)"
echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
