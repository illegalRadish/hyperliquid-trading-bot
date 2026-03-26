#!/bin/bash
# Test the Hyperliquid Trading Bot setup

set -e

cd /home/ubuntu/hyperliquid-trading-bot

echo "🧪 Testing Hyperliquid Trading Bot Setup..."

# Activate virtual environment
source venv/bin/activate

echo "✅ Virtual environment activated"

# Test Python dependencies
echo "🐍 Testing Python dependencies..."
python3 -c "
try:
    from hyperliquid.info import Info
    from hyperliquid.exchange import Exchange
    import eth_account
    print('✅ All dependencies imported successfully')
except ImportError as e:
    print(f'❌ Import error: {e}')
    exit(1)
"

# Test configuration
echo "⚙️ Testing configuration..."
if [ ! -f "config.json" ]; then
    echo "❌ config.json not found!"
    exit 1
fi

# Test bot help
echo "🤖 Testing bot command..."
python3 Breakout.py --help > /dev/null
echo "✅ Bot command works"

# Test backtest
echo "📊 Testing backtest (dry run)..."
python3 backtest.py --help > /dev/null
echo "✅ Backtest command works"

# Check credentials (without exposing them)
echo "🔐 Checking credentials format..."
python3 -c "
import json
with open('config.json') as f:
    config = json.load(f)
    
secret_key = config.get('secret_key', '')
address = config.get('account_address', '')

if 'YOUR_PRIVATE_KEY_HERE' in secret_key:
    print('❌ Please update secret_key in config.json')
    exit(1)
elif not secret_key.startswith('0x') or len(secret_key) != 66:
    print('❌ Invalid secret_key format (should be 0x + 64 hex chars)')
    exit(1)

if 'YOUR_ADDRESS_HERE' in address:
    print('❌ Please update account_address in config.json')
    exit(1)
elif not address.startswith('0x') or len(address) != 42:
    print('❌ Invalid account_address format (should be 0x + 40 hex chars)')
    exit(1)

print('✅ Credentials format looks good')
"

echo ""
echo "🎉 All tests passed!"
echo ""
echo "🚀 Ready to start the bot:"
echo "   ./deploy/start.sh"