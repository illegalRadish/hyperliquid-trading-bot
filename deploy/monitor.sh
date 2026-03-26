#!/bin/bash
# Monitor the Hyperliquid Trading Bot

echo "📊 Hyperliquid Trading Bot Status"
echo "================================="

# Service status
echo "🔧 Service Status:"
sudo systemctl status hyperliquid-bot --no-pager -l

echo ""
echo "📈 System Resources:"
echo "CPU Usage: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | awk -F'%' '{print $1}')"
echo "Memory: $(free -h | awk '/^Mem:/ {print $3 "/" $2}')"
echo "Disk: $(df -h / | awk 'NR==2 {print $3 "/" $2 " (" $5 " used)"}')"

echo ""
echo "📝 Recent Logs (last 10 lines):"
echo "================================"
sudo journalctl -u hyperliquid-bot -n 10 --no-pager

echo ""
echo "🔄 Useful Commands:"
echo "  sudo journalctl -u hyperliquid-bot -f     # Follow live logs"
echo "  sudo systemctl restart hyperliquid-bot    # Restart service"
echo "  ./deploy/stop.sh                          # Stop bot"
echo "  htop                                      # System monitor"