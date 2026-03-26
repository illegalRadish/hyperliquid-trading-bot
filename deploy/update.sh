#!/bin/bash
# Update the Hyperliquid Trading Bot

set -e

cd /home/ubuntu/hyperliquid-trading-bot

echo "🔄 Updating Hyperliquid Trading Bot..."

# Stop the bot if running
if sudo systemctl is-active --quiet hyperliquid-bot; then
    echo "🛑 Stopping bot..."
    sudo systemctl stop hyperliquid-bot
    BOT_WAS_RUNNING=true
else
    BOT_WAS_RUNNING=false
fi

# Backup current config
if [ -f "config.json" ]; then
    echo "💾 Backing up config..."
    cp config.json config.json.backup.$(date +%Y%m%d_%H%M%S)
fi

# Pull latest changes
echo "📥 Pulling latest changes..."
git pull origin main

# Update dependencies
echo "📦 Updating dependencies..."
source venv/bin/activate
pip install --upgrade -r requirements.txt

# Reload systemd service
echo "🔧 Reloading systemd service..."
sudo systemctl daemon-reload

# Restart bot if it was running
if [ "$BOT_WAS_RUNNING" = true ]; then
    echo "🚀 Restarting bot..."
    sudo systemctl start hyperliquid-bot
    sleep 2
    
    if sudo systemctl is-active --quiet hyperliquid-bot; then
        echo "✅ Bot restarted successfully!"
    else
        echo "❌ Failed to restart bot. Check logs:"
        echo "   sudo journalctl -u hyperliquid-bot -n 20"
    fi
else
    echo "✅ Update complete. Bot was not running."
fi

echo ""
echo "📊 Monitor with: ./deploy/monitor.sh"