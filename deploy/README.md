# AWS EC2 Deployment Guide

This guide will help you deploy the Hyperliquid Trading Bot on AWS EC2.

## 🚀 Quick Start

### Option 1: Automated Setup (Recommended)

1. **Launch EC2 Instance**
   - AMI: Ubuntu 22.04 LTS
   - Instance Type: t3.micro (sufficient for the bot)
   - Security Group: Allow SSH (port 22)
   - Key Pair: Create or use existing

2. **Auto-Setup with User Data**
   - In "Advanced Details" → "User data"
   - Copy contents of `deploy/ec2-user-data.sh`
   - Replace `your-username` with your GitHub username
   - Launch instance

3. **SSH and Configure**
   ```bash
   ssh -i your-key.pem ubuntu@your-ec2-ip
   cd hyperliquid-trading-bot
   nano config.json  # Add your credentials
   ./deploy/test.sh   # Test setup
   ./deploy/start.sh  # Start bot
   ```

### Option 2: Manual Setup

1. **Launch EC2 Instance** (same as above)

2. **SSH and Clone**
   ```bash
   ssh -i your-key.pem ubuntu@your-ec2-ip
   git clone https://github.com/your-username/hyperliquid-trading-bot.git
   cd hyperliquid-trading-bot
   ```

3. **Run Setup**
   ```bash
   chmod +x deploy/setup.sh
   ./deploy/setup.sh
   ```

4. **Configure and Start**
   ```bash
   nano config.json   # Add credentials
   ./deploy/test.sh   # Test
   ./deploy/start.sh  # Start
   ```

## 📋 Management Commands

| Command | Description |
|---------|-------------|
| `./deploy/start.sh` | Start the trading bot |
| `./deploy/stop.sh` | Stop the trading bot |
| `./deploy/monitor.sh` | Check bot status and logs |
| `./deploy/test.sh` | Test configuration |
| `./deploy/update.sh` | Update bot to latest version |

## 📊 Monitoring

### Real-time Logs
```bash
sudo journalctl -u hyperliquid-bot -f
```

### System Status
```bash
./deploy/monitor.sh
```

### Check Service Status
```bash
sudo systemctl status hyperliquid-bot
```

## 🔧 Configuration

### Edit Configuration
```bash
nano config.json
```

### Restart After Config Changes
```bash
sudo systemctl restart hyperliquid-bot
```

### Test Configuration
```bash
./deploy/test.sh
```

## 🛡️ Security Best Practices

### 1. Secure Your Instance
```bash
# Update system regularly
sudo apt update && sudo apt upgrade -y

# Configure firewall (only allow SSH)
sudo ufw enable
sudo ufw allow ssh
```

### 2. Secure Your Keys
- Never commit `config.json` to git
- Use separate keys for testnet/mainnet
- Consider using AWS Secrets Manager for production

### 3. Monitor Resources
```bash
# Check system resources
htop

# Check disk space
df -h

# Check memory usage
free -h
```

## 📈 Scaling and Optimization

### Instance Types

| Type | vCPU | RAM | Use Case |
|------|------|-----|----------|
| t3.micro | 2 | 1GB | Testing, single bot |
| t3.small | 2 | 2GB | Production, single bot |
| t3.medium | 2 | 4GB | Multiple bots |

### Cost Optimization
- Use **Spot Instances** for development (up to 90% savings)
- Use **Reserved Instances** for production (up to 75% savings)
- Monitor with **AWS CloudWatch** for cost alerts

## 🔄 Backup and Recovery

### Backup Configuration
```bash
# Manual backup
cp config.json config.json.backup.$(date +%Y%m%d)

# Automated backup (add to crontab)
0 6 * * * cp /home/ubuntu/hyperliquid-trading-bot/config.json /home/ubuntu/backups/config.$(date +\%Y\%m\%d).json
```

### Recovery
```bash
# Restore from backup
cp config.json.backup.YYYYMMDD config.json
sudo systemctl restart hyperliquid-bot
```

## 🚨 Troubleshooting

### Bot Won't Start
```bash
# Check logs
sudo journalctl -u hyperliquid-bot -n 50

# Test configuration
./deploy/test.sh

# Check credentials format
python3 -c "import json; print(json.load(open('config.json'))['secret_key'][:10])"
```

### High Memory Usage
```bash
# Check memory
free -h

# Restart service
sudo systemctl restart hyperliquid-bot
```

### Network Issues
```bash
# Test connectivity
ping app.hyperliquid.xyz

# Check DNS
nslookup app.hyperliquid.xyz
```

### Permission Issues
```bash
# Fix permissions
sudo chown -R ubuntu:ubuntu /home/ubuntu/hyperliquid-trading-bot
chmod +x deploy/*.sh
```

## 📞 Support

### Logs Location
- Service logs: `sudo journalctl -u hyperliquid-bot`
- Setup logs: `/var/log/user-data.log`
- System logs: `/var/log/syslog`

### Useful Commands
```bash
# Service management
sudo systemctl start|stop|restart|status hyperliquid-bot

# View configuration
cat config.json | jq .

# Check Python environment
source venv/bin/activate && python3 --version

# Test network connectivity
curl -s https://api.hyperliquid.xyz/info | jq .
```

## 💰 Cost Estimation

### Monthly Costs (us-east-1)
- **t3.micro**: ~$8.50/month (free tier eligible)
- **t3.small**: ~$17/month
- **t3.medium**: ~$34/month

### Additional Costs
- **EBS Storage**: ~$0.10/GB/month
- **Data Transfer**: First 1GB free, then $0.09/GB
- **Elastic IP**: Free if attached, $0.005/hour if unattached

*Prices subject to change. Check AWS pricing for current rates.*