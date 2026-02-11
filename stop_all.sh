#!/bin/bash

###############################################################################
# EdusCore Analytics - Stop All Applications
# This script stops all three Streamlit entry points
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

# Print banner
print_message "$BLUE" "╔════════════════════════════════════════════════════════════╗"
print_message "$BLUE" "║      EdusCore Analytics - Stop All Applications          ║"
print_message "$BLUE" "╚════════════════════════════════════════════════════════════╝"
echo ""

# Function to stop process
stop_process() {
    local name=$1
    local pid_file=$2
    
    if [ -f "$pid_file" ]; then
        PID=$(cat "$pid_file")
        if ps -p $PID > /dev/null 2>&1; then
            print_message "$YELLOW" "Stopping $name (PID: $PID)..."
            kill $PID 2>/dev/null || kill -9 $PID 2>/dev/null || true
            sleep 1
            
            if ps -p $PID > /dev/null 2>&1; then
                print_message "$RED" "✗ Failed to stop $name"
            else
                print_message "$GREEN" "✓ $name stopped"
                rm -f "$pid_file"
            fi
        else
            print_message "$YELLOW" "$name is not running (stale PID file)"
            rm -f "$pid_file"
        fi
    else
        print_message "$YELLOW" "$name PID file not found"
    fi
}

# Stop all services
if [ -d "logs" ]; then
    stop_process "Main Application" "logs/app.pid"
    stop_process "Admin Features" "logs/admin_features.pid"
    stop_process "Parents Portal" "logs/parents_portal.pid"
else
    print_message "$YELLOW" "No logs directory found. Attempting to stop by port..."
    
    # Try to stop by port
    for port in 5000 5001 5002; do
        if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1 ; then
            print_message "$YELLOW" "Stopping process on port $port..."
            lsof -ti:$port | xargs kill -9 2>/dev/null || true
        fi
    done
fi

echo ""
print_message "$BLUE" "════════════════════════════════════════════════════════════"
print_message "$GREEN" "All services stopped"
print_message "$BLUE" "════════════════════════════════════════════════════════════"
