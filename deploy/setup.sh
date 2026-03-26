#!/bin/bash
# Hyperliquid Trading Bot - EC2 Setup Script
set -e

echo "🚀 Setting up Hyperliquid Trading Bot on EC2..."

# Update system
echo "📦 Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install Python 3.9+ and pip
echo "🐍 Installing Python..."
sudo apt install -y python3 python3-pip python3-venv git htop screen

# Install Node.js (for PM2 process manager)
echo "📦 Installing Node.js and PM2..."
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm install -g pm2

# Clone repository (if not already present)
if [ ! -d "/home/ubuntu/hyperliquid-trading-bot" ]; then
    echo "📥 Cloning repository..."
    cd /home/ubuntu
    git clone https://github.com/your-username/hyperliquid-trading-bot.git
    cd hyperliquid-trading-bot
else
    echo "📁 Repository already exists, updating..."
    cd /home/ubuntu/hyperliquid-trading-bot
    git pull origin main
fi

# Create Python virtual environment
echo "🔧 Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "📦 Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt

# Create directories
echo "📁 Creating directories..."
mkdir -p logs data results

# Set up configuration
echo "⚙️ Setting up configuration..."
if [ ! -f "config.json" ]; then
    cp config.example.json config.json
    echo "✅ Created config.json from template"
    echo "⚠️  IMPORTANT: Edit config.json with your credentials!"
else
    echo "✅ config.json already exists"
fi

# Set up systemd service (alternative to PM2)
echo "🔧 Setting up systemd service..."
sudo tee /etc/systemd/system/hyperliquid-bot.service > /dev/null <<EOF
[Unit]
Description=Hyperliquid Trading Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/hyperliquid-trading-bot
Environment=PATH=/home/ubuntu/hyperliquid-trading-bot/venv/bin
ExecStart=/home/ubuntu/hyperliquid-trading-bot/venv/bin/python Breakout.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Set up log rotation
echo "📝 Setting up log rotation..."
sudo tee /etc/logrotate.d/hyperliquid-bot > /dev/null <<EOF
/home/ubuntu/hyperliquid-trading-bot/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
EOF

# Set permissions
echo "🔐 Setting permissions..."
sudo chown -R ubuntu:ubuntu /home/ubuntu/hyperliquid-trading-bot
chmod +x deploy/*.sh

# Enable and start the service (but don't start it yet)
sudo systemctl daemon-reload
sudo systemctl enable hyperliquid-bot

echo ""
echo "✅ Setup complete!"
echo ""
echo "📋 Next steps:"
echo "1. Edit config.json with your credentials:"
echo "   nano config.json"
echo ""
echo "2. Test the bot:"
echo "   ./deploy/test.sh"
echo ""
echo "3. Start the bot:"
echo "   ./deploy/start.sh"
echo ""
echo "4. Monitor the bot:"
echo "   ./deploy/monitor.sh"
echo ""
echo "🔧 Useful commands:"
echo "   sudo systemctl status hyperliquid-bot    # Check status"
echo "   sudo systemctl start hyperliquid-bot     # Start service"
echo "   sudo systemctl stop hyperliquid-bot      # Stop service"
echo "   sudo journalctl -u hyperliquid-bot -f    # View logs"