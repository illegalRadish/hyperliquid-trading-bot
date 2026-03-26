# Hyperliquid Momentum Breakout Trading Bot

A Python-based algorithmic trading bot that implements the **Momentum Breakout with Volume** strategy on the Hyperliquid DEX. The strategy detects price breakouts above/below N-candle ranges, confirmed by volume spikes, and manages positions with ATR-based stops and trailing functionality.

## 🎯 Strategy Overview

The **Momentum Breakout with Volume** strategy:

1. **Breakout Detection**: Monitors when price breaks above the highest high or below the lowest low of the last N candles (default: 20)
2. **Volume Confirmation**: Only triggers when current volume exceeds the average volume by a multiplier (default: 1.5x)
3. **Range Filtering**: Ignores flat markets by requiring the breakout range to be at least 2x the ATR
4. **Risk Management**: Uses ATR-based stop losses (2x ATR) and range-extension take profits (1.5x range)
5. **Trailing Stops**: Dynamically adjusts stop loss to lock in profits as the position moves favorably

## 📁 Project Structure

```
hyperliquid-trading-bot/
├── Breakout.py           # Live trading bot
├── backtest.py           # Backtesting engine
├── config.example.json   # Configuration template
├── requirements.txt      # Python dependencies
├── .gitignore           # Git ignore rules
└── README.md            # This file
```

## 🚀 Quick Start

### 1. Installation

```bash
git clone https://github.com/your-username/hyperliquid-trading-bot.git
cd hyperliquid-trading-bot
pip install -r requirements.txt
```

### 2. Configuration

Copy the example config and add your credentials:

```bash
cp config.example.json config.json
```

Edit `config.json` with your Hyperliquid wallet details:

```json
{
    "secret_key": "0xYOUR_PRIVATE_KEY_HERE",
    "account_address": "0xYOUR_ADDRESS_HERE",
    "use_testnet": false,
    "strategy": {
        "coin": "ETH",
        "timeframe": "15m",
        "lookback_periods": 20,
        "volume_multiplier": 1.5,
        "position_size_pct": 0.05,
        "atr_period": 14,
        "atr_stop_multiplier": 2.0,
        "tp_range_multiplier": 1.5,
        "min_range_atr_ratio": 2.0,
        "trailing_stop": true,
        "slippage": 0.05
    }
}
```

### 3. Backtest First

**Always backtest before going live!** Test the strategy on historical data:

```bash
# Basic backtest - ETH 15m, last 30 days
python3 backtest.py

# Custom parameters
python3 backtest.py --coin BTC --tf 1h --days 90 --capital 50000

# Test with testnet data
python3 backtest.py --testnet --coin ETH --tf 15m --days 30

# Save data for reuse
python3 backtest.py --coin ETH --tf 15m --days 60 --save-csv data/ETH_15m_60d.csv

# Load from saved data
python3 backtest.py --csv data/ETH_15m_60d.csv
```

### 4. Test on Testnet (Recommended)

Before going live, test on Hyperliquid's testnet:

```bash
# Test on testnet (via CLI flag)
python3 Breakout.py --testnet

# Or set in config.json: "use_testnet": true
python3 Breakout.py
```

### 5. Go Live

Once satisfied with testnet results:

```bash
python3 Breakout.py
```

## 📊 Backtesting

The backtesting engine (`backtest.py`) provides comprehensive analysis:

### Features
- **Historical Data**: Fetches candle data directly from Hyperliquid API
- **Exact Simulation**: Uses the same signal logic as the live bot
- **Performance Metrics**: Win rate, profit factor, max drawdown, Sharpe ratio
- **Data Caching**: Save/load CSV files to avoid re-downloading data
- **Trade Analysis**: Detailed trade log with entry/exit prices and reasons

### Example Output

```
============================================================
  BACKTEST RESULTS — Momentum Breakout with Volume
============================================================
  Total trades:      47
  Win rate:          42.6%
  Profit factor:     1.34
  Avg trade P&L:     $23.45
  Avg winner:        $89.23
  Avg loser:         -$45.67
  Max drawdown:      8.2%

  Initial capital:   $10,000.00
  Final equity:      $11,102.15
  Total return:      +11.02%
============================================================
```

### CLI Options

```bash
python3 backtest.py --help

Options:
  --coin COIN           Cryptocurrency to trade (default: ETH)
  --tf TIMEFRAME        Candle timeframe: 1m, 5m, 15m, 1h, 4h, 1d (default: 15m)
  --days DAYS           Days of historical data (default: 30)
  --capital CAPITAL     Starting capital in USD (default: 10000)
  --csv PATH            Load candles from CSV file
  --save-csv PATH       Save fetched candles to CSV
  --config PATH         Config file path (default: config.json)
  --out-trades PATH     Trade log output (default: results/trades.csv)
  --out-equity PATH     Equity curve output (default: results/equity.csv)
  --testnet             Use Hyperliquid testnet for data
```

## ⚙️ Configuration Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `use_testnet` | Use Hyperliquid testnet instead of mainnet | false |
| `coin` | Trading pair (e.g., "ETH", "BTC") | "ETH" |
| `timeframe` | Candle interval (1m, 5m, 15m, 1h, 4h, 1d) | "15m" |
| `lookback_periods` | Number of candles for breakout range | 20 |
| `volume_multiplier` | Volume confirmation threshold | 1.5 |
| `position_size_pct` | Risk per trade as % of account | 0.05 (5%) |
| `atr_period` | ATR calculation period | 14 |
| `atr_stop_multiplier` | Stop loss distance (ATR × multiplier) | 2.0 |
| `tp_range_multiplier` | Take profit extension (range × multiplier) | 1.5 |
| `min_range_atr_ratio` | Minimum range size filter | 2.0 |
| `trailing_stop` | Enable trailing stop functionality | true |
| `slippage` | Market order slippage tolerance | 0.05 (5%) |

## 🔧 Live Trading Features

### Position Management
- **Market Entry**: Uses `market_open()` for immediate execution
- **Bracket Orders**: Automatically places stop-loss and take-profit triggers
- **Position Sync**: Reconciles local state with exchange on each loop
- **Trailing Stops**: Dynamically adjusts stops to lock in profits

### Risk Controls
- **Position Sizing**: Risk-based sizing using account equity and ATR
- **Range Filtering**: Avoids trading in flat/choppy markets
- **Volume Confirmation**: Reduces false breakouts
- **Stop Losses**: Hard stops at 2× ATR from entry

### Monitoring
- **Structured Logging**: Timestamped logs for all actions
- **Position Tracking**: Real-time position and P&L monitoring
- **Error Handling**: Graceful handling of API errors and reconnection

## 📈 Strategy Performance

### Strengths
- **Trend Following**: Captures momentum moves effectively
- **Volume Filter**: Reduces false signals in low-volume breakouts
- **Risk Management**: Consistent position sizing and stop losses
- **Adaptability**: Works across different timeframes and assets

### Considerations
- **Whipsaw Risk**: Can generate losses in ranging markets
- **Slippage Impact**: Market orders may face slippage in fast moves
- **Parameter Sensitivity**: Performance varies with configuration
- **Market Regime**: Works best in trending market conditions

## 🛡️ Security & Best Practices

### API Security
- **Private Keys**: Store in `config.json` (gitignored by default)
- **Testnet First**: Always test on Hyperliquid testnet before mainnet
- **Key Rotation**: Regularly rotate API keys and private keys
- **Separate Keys**: Use different keys for testnet and mainnet

### Risk Management
- **Start Small**: Begin with small position sizes
- **Monitor Closely**: Watch initial trades carefully
- **Gradual Scaling**: Increase size only after consistent performance
- **Kill Switch**: Have a manual override process

### Operational
- **Logging**: Monitor logs for errors and performance
- **Backups**: Keep backups of config and trade history
- **Updates**: Stay updated with Hyperliquid API changes
- **Testing**: Backtest after any parameter changes

## 🔍 Troubleshooting

### Common Issues

**Bot won't start:**
- Check `config.json` format and credentials
- Verify network connectivity to Hyperliquid
- Ensure sufficient account balance

**No trades executing:**
- Check if market is ranging (no clear breakouts)
- Verify volume is meeting the multiplier threshold
- Review ATR and range size requirements

**Unexpected behavior:**
- Check logs for error messages
- Verify position sync with exchange
- Ensure bracket orders are placing correctly

### Debug Mode

Enable debug logging by modifying the logging level in `Breakout.py`:

```python
logging.basicConfig(level=logging.DEBUG)
```

## 📚 Dependencies

- **hyperliquid-python-sdk**: Official Hyperliquid Python SDK
- **eth-account**: Ethereum account management for wallet operations

## ⚠️ Disclaimer

This trading bot is for educational and research purposes. Algorithmic trading involves substantial risk of loss. Past performance does not guarantee future results. Always:

- Test thoroughly on testnet
- Start with small amounts
- Monitor performance closely
- Understand the risks involved
- Never risk more than you can afford to lose

## 🚀 AWS EC2 Deployment

For production deployment on AWS EC2, see the [deployment guide](deploy/README.md).

### Quick EC2 Setup
```bash
# 1. Launch Ubuntu 22.04 EC2 instance
# 2. SSH into instance
ssh -i your-key.pem ubuntu@your-ec2-ip

# 3. Clone and setup
git clone https://github.com/your-username/hyperliquid-trading-bot.git
cd hyperliquid-trading-bot
./deploy/setup.sh

# 4. Configure credentials
nano config.json

# 5. Test and start
./deploy/test.sh
./deploy/start.sh
```

## 📄 License

MIT License - see LICENSE file for details.

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## 📞 Support

For questions or issues:
- Open a GitHub issue
- Check Hyperliquid documentation
- Review the code comments and logs