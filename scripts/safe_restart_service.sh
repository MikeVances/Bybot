#!/bin/bash
# Safe restart script for BYBOT trading service after Market Context Engine integration

set -e  # Exit on error

echo "🔍 BYBOT Safe Restart Script"
echo "======================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
SERVICE_NAME="bybot-trading.service"
PROJECT_DIR="/home/mikevance/bots/bybot"
BACKUP_DIR="$PROJECT_DIR/backups/pre_restart_$(date +%Y%m%d_%H%M%S)"

# Check if service exists
if ! systemctl list-units --all | grep -q "$SERVICE_NAME"; then
    echo -e "${RED}❌ Service $SERVICE_NAME not found${NC}"
    exit 1
fi

echo -e "${YELLOW}📊 Current service status:${NC}"
systemctl status $SERVICE_NAME --no-pager | head -10
echo ""

# Ask for confirmation
read -p "⚠️  Proceed with restart? [y/N]: " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Restart cancelled by user"
    exit 0
fi

# Create backup of current state
echo -e "${YELLOW}📦 Creating backup...${NC}"
mkdir -p "$BACKUP_DIR"

# Backup critical files
cp "$PROJECT_DIR/bot/strategy/modules/volume_vwap_pipeline.py" "$BACKUP_DIR/" 2>/dev/null || true
cp "$PROJECT_DIR/bot/strategy/base/config.py" "$BACKUP_DIR/" 2>/dev/null || true

# Check current positions (via logs)
echo -e "${YELLOW}🔍 Checking for open positions...${NC}"
LAST_LOG=$(journalctl -u $SERVICE_NAME -n 50 --no-pager | grep -i "позиц\|position\|открыт\|open" | tail -5)
if [ -z "$LAST_LOG" ]; then
    echo -e "${GREEN}✅ No open positions detected in recent logs${NC}"
else
    echo -e "${RED}⚠️  Possible open positions detected:${NC}"
    echo "$LAST_LOG"
    echo ""
    read -p "Continue with restart anyway? [y/N]: " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Restart cancelled - close positions manually first"
        exit 0
    fi
fi

# Stop service gracefully
echo -e "${YELLOW}🛑 Stopping $SERVICE_NAME...${NC}"
sudo systemctl stop $SERVICE_NAME

# Wait for graceful shutdown
echo -e "${YELLOW}⏳ Waiting for graceful shutdown...${NC}"
sleep 3

# Verify service stopped
if systemctl is-active --quiet $SERVICE_NAME; then
    echo -e "${RED}❌ Service did not stop properly${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Service stopped${NC}"

# Optional: Run quick syntax check
echo -e "${YELLOW}🔍 Running syntax check...${NC}"
cd "$PROJECT_DIR"
source .venv/bin/activate

# Test import
if python -c "from bot.market_context import MarketContextEngine; from bot.strategy.modules.volume_vwap_pipeline import VolumeVwapPositionSizer; print('✅ Imports OK')" 2>&1; then
    echo -e "${GREEN}✅ Code validation passed${NC}"
else
    echo -e "${RED}❌ Code validation failed - check imports${NC}"
    echo ""
    read -p "Start service anyway? [y/N]: " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Restart cancelled - fix errors first"
        exit 1
    fi
fi

# Start service
echo -e "${YELLOW}🚀 Starting $SERVICE_NAME...${NC}"
sudo systemctl start $SERVICE_NAME

# Wait for startup
echo -e "${YELLOW}⏳ Waiting for startup...${NC}"
sleep 3

# Check status
if systemctl is-active --quiet $SERVICE_NAME; then
    echo -e "${GREEN}✅ Service started successfully!${NC}"
    echo ""
    echo -e "${YELLOW}📊 Current status:${NC}"
    systemctl status $SERVICE_NAME --no-pager | head -15
    echo ""
    echo -e "${YELLOW}📋 Recent logs (showing Market Context activity):${NC}"
    journalctl -u $SERVICE_NAME -n 20 --no-pager | grep -E "Market|Context|session|regime|liquidity" || echo "(No Market Context logs yet - check in 1-2 minutes)"
    echo ""
    echo -e "${GREEN}✅ Restart completed successfully!${NC}"
    echo ""
    echo "📚 Next steps:"
    echo "  1. Monitor logs: journalctl -u $SERVICE_NAME -f"
    echo "  2. Check for 'market_context_used: True' in metadata"
    echo "  3. Verify session-aware stops in trade logs"
    echo ""
    echo "📦 Backup location: $BACKUP_DIR"
else
    echo -e "${RED}❌ Service failed to start!${NC}"
    echo ""
    echo "🔍 Checking errors:"
    journalctl -u $SERVICE_NAME -n 50 --no-pager | tail -20
    echo ""
    echo "💡 Restore from backup if needed: $BACKUP_DIR"
    exit 1
fi
