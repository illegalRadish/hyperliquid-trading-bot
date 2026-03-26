#!/bin/bash
# Start the Hyperliquid Trading Bot

set -e

cd /home/ubuntu/hyperliquid-trading-bot

echo "🚀 Starting Hyperliquid Trading Bot..."

# Check if config exists
if [ ! -f "config.json" ]; then
    echo "❌ config.json not found!"
    echo "Please copy config.example.json to config.json and add your credentials."
    exit 1
fi

# Check if credentials are set
if grep -q "YOUR_PRIVATE_KEY_HERE" config.json; then
    echo "❌ Please update config.json with your actual credentials!"
    echo "Edit the file: nano config.json"
    exit 1
fi

# Start using systemd
echo "🔧 Starting systemd service..."
sudo systemctl start hyperliquid-bot

# Wait a moment and check status
sleep 2
if sudo systemctl is-active --quiet hyperliquid-bot; then
    echo "✅ Bot started successfully!"
    echo ""
    echo "📊 Monitor with:"
    echo "   ./deploy/monitor.sh"
    echo "   sudo journalctl -u hyperliquid-bot -f"
else
    echo "❌ Failed to start bot. Check logs:"
    echo "   sudo journalctl -u hyperliquid-bot -n 20"
fi