#!/bin/bash

###############################################################################
# EdusCore Analytics - Start All Applications
# This script starts all three Streamlit entry points for development/testing
###############################################################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored messages
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Function to check if port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        return 0
    else
        return 1
    fi
}

# Function to kill process on port
kill_port() {
    local port=$1
    if check_port $port; then
        print_message "$YELLOW" "Port $port is in use. Stopping existing process..."
        lsof -ti:$port | xargs kill -9 2>/dev/null || true
        sleep 2
    fi
}

# Print banner
print_message "$BLUE" "╔════════════════════════════════════════════════════════════╗"
print_message "$BLUE" "║         EdusCore Analytics - Multi-App Launcher           ║"
print_message "$BLUE" "╚════════════════════════════════════════════════════════════╝"
echo ""

# Check if streamlit is installed
if ! command -v streamlit &> /dev/null; then
    print_message "$RED" "Error: Streamlit is not installed!"
    print_message "$YELLOW" "Please install it using: pip install streamlit"
    exit 1
fi

# Check if Python files exist
if [ ! -f "app.py" ]; then
    print_message "$RED" "Error: app.py not found!"
    exit 1
fi

if [ ! -f "admin_features.py" ]; then
    print_message "$RED" "Error: admin_features.py not found!"
    exit 1
fi

if [ ! -f "parents_portal_standalone.py" ]; then
    print_message "$RED" "Error: parents_portal_standalone.py not found!"
    exit 1
fi

print_message "$GREEN" "✓ All required files found"
echo ""

# Clean up any existing processes on the ports
print_message "$YELLOW" "Checking for existing processes..."
kill_port 5000
kill_port 5001
kill_port 5002
echo ""

# Create logs directory if it doesn't exist
mkdir -p logs

# Start Main Application (app.py) on port 5000
print_message "$BLUE" "Starting Main Application on port 5000..."
nohup streamlit run app.py \
    --server.port 5000 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false \
    > logs/app.log 2>&1 &
APP_PID=$!
echo $APP_PID > logs/app.pid
print_message "$GREEN" "✓ Main Application started (PID: $APP_PID)"
sleep 2

# Start Admin Features (admin_features.py) on port 5001
print_message "$BLUE" "Starting Admin Features on port 5001..."
nohup streamlit run admin_features.py \
    --server.port 5001 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false \
    > logs/admin_features.log 2>&1 &
ADMIN_PID=$!
echo $ADMIN_PID > logs/admin_features.pid
print_message "$GREEN" "✓ Admin Features started (PID: $ADMIN_PID)"
sleep 2

# Start Parents Portal (parents_portal_standalone.py) on port 5002
print_message "$BLUE" "Starting Parents Portal on port 5002..."
nohup streamlit run parents_portal_standalone.py \
    --server.port 5002 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false \
    > logs/parents_portal.log 2>&1 &
PARENTS_PID=$!
echo $PARENTS_PID > logs/parents_portal.pid
print_message "$GREEN" "✓ Parents Portal started (PID: $PARENTS_PID)"
echo ""

# Wait for services to start
print_message "$YELLOW" "Waiting for services to start..."
sleep 5

# Check if all services are running
print_message "$YELLOW" "Verifying services..."
SERVICES_OK=true

if ! check_port 5000; then
    print_message "$RED" "✗ Main Application (port 5000) failed to start"
    SERVICES_OK=false
else
    print_message "$GREEN" "✓ Main Application running on http://localhost:5000"
fi

if ! check_port 5001; then
    print_message "$RED" "✗ Admin Features (port 5001) failed to start"
    SERVICES_OK=false
else
    print_message "$GREEN" "✓ Admin Features running on http://localhost:5001"
fi

if ! check_port 5002; then
    print_message "$RED" "✗ Parents Portal (port 5002) failed to start"
    SERVICES_OK=false
else
    print_message "$GREEN" "✓ Parents Portal running on http://localhost:5002"
fi

echo ""
print_message "$BLUE" "════════════════════════════════════════════════════════════"

if [ "$SERVICES_OK" = true ]; then
    print_message "$GREEN" "✓ All services started successfully!"
    echo ""
    print_message "$YELLOW" "Access the applications at:"
    echo "  • Main App:       http://localhost:5000"
    echo "  • Admin Features: http://localhost:5001"
    echo "  • Parents Portal: http://localhost:5002"
    echo ""
    print_message "$YELLOW" "Process IDs saved in logs/*.pid"
    print_message "$YELLOW" "Application logs saved in logs/*.log"
    echo ""
    print_message "$BLUE" "To stop all services, run: ./stop_all.sh"
    print_message "$BLUE" "Or manually: kill \$(cat logs/*.pid)"
else
    print_message "$RED" "✗ Some services failed to start. Check logs/ directory for details."
    exit 1
fi

print_message "$BLUE" "════════════════════════════════════════════════════════════"
