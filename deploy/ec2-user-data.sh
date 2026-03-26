#!/bin/bash
# EC2 User Data Script - Automatically sets up the bot on instance launch
# Add this to your EC2 instance's User Data field when launching

set -e

# Log everything
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1

echo "🚀 Starting EC2 auto-setup for Hyperliquid Trading Bot..."

# Wait for system to be ready
sleep 30

# Update system
apt update && apt upgrade -y

# Install basic tools
apt install -y curl wget git htop

# Switch to ubuntu user for the rest
sudo -u ubuntu bash << 'EOF'
cd /home/ubuntu

# Clone the repository
git clone https://github.com/your-username/hyperliquid-trading-bot.git
cd hyperliquid-trading-bot

# Run setup script
chmod +x deploy/setup.sh
./deploy/setup.sh

echo "✅ EC2 auto-setup complete!"
echo "🔧 Next: SSH into the instance and configure credentials"
EOF

echo "📝 Setup log saved to /var/log/user-data.log"