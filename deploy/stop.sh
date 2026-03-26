#!/bin/bash
# Stop the Hyperliquid Trading Bot

set -e

echo "🛑 Stopping Hyperliquid Trading Bot..."

# Stop systemd service
sudo systemctl stop hyperliquid-bot

echo "✅ Bot stopped successfully!"
echo ""
echo "📊 Check final status:"
echo "   sudo systemctl status hyperliquid-bot"