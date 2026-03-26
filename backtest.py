"""
Backtesting engine for the Momentum Breakout with Volume strategy.

Fetches historical candle data from Hyperliquid (or loads from a local CSV
cache) and simulates the strategy without placing real orders.

Usage:
    python backtest.py                          # defaults: ETH, 15m, last 30 days
    python backtest.py --coin BTC --tf 1h --days 90
    python backtest.py --csv data/ETH_15m.csv   # replay from file
"""

import argparse
import csv
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from hyperliquid.info import Info
from hyperliquid.utils import constants

from Breakout import Candle, StrategyConfig, compute_atr, parse_candles, TIMEFRAME_SECONDS

log = logging.getLogger("backtest")

# ---------------------------------------------------------------------------
# Trade record
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    entry_time: int
    exit_time: int
    side: str
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    exit_reason: str       # "sl" | "tp" | "trailing" | "end"


# ---------------------------------------------------------------------------
# Simulated position
# ---------------------------------------------------------------------------

@dataclass
class SimPosition:
    side: str
    entry_time: int
    entry_price: float
    size: float
    stop_loss: float
    take_profit: float


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def fetch_candles_historical(coin: str, timeframe: str, days: int, use_testnet: bool = False) -> list[Candle]:
    api_url = constants.TESTNET_API_URL if use_testnet else constants.MAINNET_API_URL
    info = Info(api_url, skip_ws=True)
    interval_s = TIMEFRAME_SECONDS[timeframe]
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - days * 86400 * 1000

    all_candles: list[Candle] = []
    cursor = start_ms
    chunk_size = 5000 * interval_s * 1000

    while cursor < now_ms:
        end = min(cursor + chunk_size, now_ms)
        raw = info.candles_snapshot(coin, timeframe, cursor, end)
        if not raw:
            break
        batch = parse_candles(raw)
        all_candles.extend(batch)
        cursor = int(batch[-1].timestamp) + interval_s * 1000
        log.info("Fetched %d candles so far (up to %d)", len(all_candles), cursor)
        time.sleep(0.25)

    # deduplicate by timestamp
    seen: set[int] = set()
    deduped: list[Candle] = []
    for c in all_candles:
        if c.timestamp not in seen:
            seen.add(c.timestamp)
            deduped.append(c)
    deduped.sort(key=lambda c: c.timestamp)
    return deduped


def save_candles_csv(candles: list[Candle], path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for c in candles:
            w.writerow([c.timestamp, c.open, c.high, c.low, c.close, c.volume])
    log.info("Saved %d candles → %s", len(candles), path)


def load_candles_csv(path: str) -> list[Candle]:
    candles: list[Candle] = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            candles.append(Candle(
                timestamp=int(row["timestamp"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            ))
    candles.sort(key=lambda c: c.timestamp)
    return candles


# ---------------------------------------------------------------------------
# Backtest engine
# ---------------------------------------------------------------------------

class BacktestEngine:
    def __init__(self, candles: list[Candle], config: StrategyConfig, initial_capital: float = 10_000.0):
        self.candles = candles
        self.cfg = config
        self.initial_capital = initial_capital
        self.equity = initial_capital
        self.peak_equity = initial_capital
        self.position: Optional[SimPosition] = None
        self.trades: list[Trade] = []
        self.equity_curve: list[tuple[int, float]] = []

    # ---- signal (mirrors live bot logic) ----

    def _evaluate(self, window: list[Candle], all_candles: list[Candle] = None, candle_idx: int = -1) -> Optional[str]:
        n_confirm = self.cfg.confirm_candles
        if len(window) < self.cfg.lookback_periods + 1 + n_confirm:
            return None

        # --- session filter ---
        if self.cfg.blocked_utc_hours:
            import datetime
            last_ts = window[-1].timestamp / 1000
            utc_hour = datetime.datetime.utcfromtimestamp(last_ts).hour
            if utc_hour in self.cfg.blocked_utc_hours:
                return None

        lookback = window[-(self.cfg.lookback_periods + n_confirm):-n_confirm]
        highest_high = max(c.high for c in lookback)
        lowest_low = min(c.low for c in lookback)
        range_size = highest_high - lowest_low

        avg_volume = sum(c.volume for c in lookback) / len(lookback)
        atr = compute_atr(window[:-n_confirm], self.cfg.atr_period)

        if atr == 0 or range_size < atr * self.cfg.min_range_atr_ratio:
            return None

        # --- ATR regime filter ---
        if self.cfg.max_atr_percentile < 100.0 and all_candles is not None and candle_idx >= 0:
            window_len = min(self.cfg.atr_lookback_window, candle_idx)
            if window_len > self.cfg.atr_period:
                historical_atrs = []
                for j in range(self.cfg.atr_period + 1, window_len + 1):
                    slice_end = candle_idx - n_confirm - (window_len - j)
                    slice_start = max(0, slice_end - self.cfg.atr_period - 1)
                    if slice_end > slice_start:
                        a = compute_atr(all_candles[slice_start:slice_end], self.cfg.atr_period)
                        if a > 0:
                            historical_atrs.append(a)
                if historical_atrs:
                    historical_atrs.sort()
                    idx = int(len(historical_atrs) * self.cfg.max_atr_percentile / 100)
                    idx = min(idx, len(historical_atrs) - 1)
                    if atr > historical_atrs[idx]:
                        return None

        confirm_slice = window[-n_confirm:]
        total_confirm_volume = sum(c.volume for c in confirm_slice)
        avg_confirm_volume = total_confirm_volume / n_confirm

        volume_confirmed = avg_confirm_volume > avg_volume * self.cfg.volume_multiplier

        signal = None
        if all(c.close > highest_high for c in confirm_slice) and volume_confirmed:
            signal = "LONG"
        elif all(c.close < lowest_low for c in confirm_slice) and volume_confirmed:
            signal = "SHORT"

        if signal is None:
            return None

        # --- trend filter (MA) ---
        if self.cfg.ma_period > 0 and len(window) >= self.cfg.ma_period:
            ma = sum(c.close for c in window[-self.cfg.ma_period:]) / self.cfg.ma_period
            if signal == "LONG" and window[-1].close < ma:
                return None
            if signal == "SHORT" and window[-1].close > ma:
                return None

        return signal

    # ---- position management ----

    def _open(self, signal: str, window: list[Candle]) -> None:
        if self.equity <= 0:
            return

        current = window[-1]
        atr = compute_atr(window[:-1], self.cfg.atr_period)
        lookback = window[-(self.cfg.lookback_periods + 1):-1]
        range_size = max(c.high for c in lookback) - min(c.low for c in lookback)

        entry = current.close
        if signal == "LONG":
            sl = entry - atr * self.cfg.atr_stop_multiplier
            tp = entry + range_size * self.cfg.tp_range_multiplier
        else:
            sl = entry + atr * self.cfg.atr_stop_multiplier
            tp = entry - range_size * self.cfg.tp_range_multiplier

        risk_usd = self.equity * self.cfg.position_size_pct
        risk_per_unit = abs(entry - sl)
        if risk_per_unit == 0:
            return
        sz = risk_usd / risk_per_unit

        self.position = SimPosition(
            side=signal, entry_time=current.timestamp,
            entry_price=entry, size=sz, stop_loss=sl, take_profit=tp,
        )

    def _check_exit(self, candle: Candle) -> Optional[tuple[str, float]]:
        """Check if the candle triggers SL or TP. Returns (reason, fill_price) or None."""
        pos = self.position
        if pos is None:
            return None

        if pos.side == "LONG":
            if candle.low <= pos.stop_loss:
                fill = min(pos.stop_loss, candle.open)
                return "sl", fill
            if candle.high >= pos.take_profit:
                fill = max(pos.take_profit, candle.open)
                return "tp", fill
        else:
            if candle.high >= pos.stop_loss:
                fill = max(pos.stop_loss, candle.open)
                return "sl", fill
            if candle.low <= pos.take_profit:
                fill = min(pos.take_profit, candle.open)
                return "tp", fill
        return None

    def _close(self, exit_price: float, exit_time: int, reason: str) -> None:
        pos = self.position
        if pos is None:
            return

        if pos.side == "LONG":
            pnl = (exit_price - pos.entry_price) * pos.size
        else:
            pnl = (pos.entry_price - exit_price) * pos.size

        pnl_pct = pnl / self.equity if self.equity else 0.0
        self.equity += pnl

        self.trades.append(Trade(
            entry_time=pos.entry_time, exit_time=exit_time,
            side=pos.side, entry_price=pos.entry_price,
            exit_price=exit_price, size=pos.size,
            pnl=pnl, pnl_pct=pnl_pct, exit_reason=reason,
        ))
        self.position = None

    def _trailing_stop(self, window: list[Candle]) -> None:
        if self.position is None or not self.cfg.trailing_stop:
            return
        atr = compute_atr(window[:-1], self.cfg.atr_period)
        current = window[-1]
        if self.position.side == "LONG":
            new_stop = current.close - atr * self.cfg.atr_stop_multiplier
            if new_stop > self.position.stop_loss:
                self.position.stop_loss = new_stop
        else:
            new_stop = current.close + atr * self.cfg.atr_stop_multiplier
            if new_stop < self.position.stop_loss:
                self.position.stop_loss = new_stop

    # ---- run ----

    def run(self) -> "BacktestResult":
        base_warmup = max(self.cfg.lookback_periods, self.cfg.atr_period) + 5
        warmup = max(base_warmup, self.cfg.ma_period, self.cfg.atr_lookback_window)

        for i in range(warmup, len(self.candles)):
            candle = self.candles[i]
            window = self.candles[max(0, i - warmup):i + 1]

            if self.position is not None:
                exit_result = self._check_exit(candle)
                if exit_result:
                    reason, exit_px = exit_result
                    self._close(exit_px, candle.timestamp, reason)
                else:
                    self._trailing_stop(window)
            else:
                signal = self._evaluate(window, all_candles=self.candles, candle_idx=i)
                if signal:
                    self._open(signal, window)

            self.equity_curve.append((candle.timestamp, self.equity))
            self.peak_equity = max(self.peak_equity, self.equity)

        # force-close any open position at the end
        if self.position is not None:
            self._close(self.candles[-1].close, self.candles[-1].timestamp, "end")

        return BacktestResult(
            trades=self.trades,
            equity_curve=self.equity_curve,
            initial_capital=self.initial_capital,
            final_equity=self.equity,
        )


# ---------------------------------------------------------------------------
# Results / reporting
# ---------------------------------------------------------------------------

@dataclass
class BacktestResult:
    trades: list[Trade]
    equity_curve: list[tuple[int, float]]
    initial_capital: float
    final_equity: float

    @property
    def total_return_pct(self) -> float:
        return (self.final_equity - self.initial_capital) / self.initial_capital * 100

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t.pnl > 0)
        return wins / len(self.trades) * 100

    @property
    def max_drawdown_pct(self) -> float:
        peak = self.initial_capital
        max_dd = 0.0
        for _, eq in self.equity_curve:
            peak = max(peak, eq)
            dd = (peak - eq) / peak
            max_dd = max(max_dd, dd)
        return max_dd * 100

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(t.pnl for t in self.trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self.trades if t.pnl < 0))
        return gross_profit / gross_loss if gross_loss else float("inf")

    @property
    def avg_pnl(self) -> float:
        return sum(t.pnl for t in self.trades) / len(self.trades) if self.trades else 0.0

    @property
    def avg_winner(self) -> float:
        winners = [t.pnl for t in self.trades if t.pnl > 0]
        return sum(winners) / len(winners) if winners else 0.0

    @property
    def avg_loser(self) -> float:
        losers = [t.pnl for t in self.trades if t.pnl < 0]
        return sum(losers) / len(losers) if losers else 0.0

    def summary(self) -> str:
        lines = [
            "",
            "=" * 60,
            "  BACKTEST RESULTS — Momentum Breakout with Volume",
            "=" * 60,
            f"  Total trades:      {len(self.trades)}",
            f"  Win rate:          {self.win_rate:.1f}%",
            f"  Profit factor:     {self.profit_factor:.2f}",
            f"  Avg trade P&L:     ${self.avg_pnl:,.2f}",
            f"  Avg winner:        ${self.avg_winner:,.2f}",
            f"  Avg loser:         ${self.avg_loser:,.2f}",
            f"  Max drawdown:      {self.max_drawdown_pct:.2f}%",
            "",
            f"  Initial capital:   ${self.initial_capital:,.2f}",
            f"  Final equity:      ${self.final_equity:,.2f}",
            f"  Total return:      {self.total_return_pct:+.2f}%",
            "=" * 60,
        ]
        return "\n".join(lines)

    def trades_to_csv(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["entry_time", "exit_time", "side", "entry_price", "exit_price", "size", "pnl", "pnl_pct", "exit_reason"])
            for t in self.trades:
                w.writerow([t.entry_time, t.exit_time, t.side, t.entry_price, t.exit_price, t.size, t.pnl, t.pnl_pct, t.exit_reason])
        log.info("Wrote %d trades → %s", len(self.trades), path)

    def equity_to_csv(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "equity"])
            for ts, eq in self.equity_curve:
                w.writerow([ts, eq])
        log.info("Wrote equity curve → %s", path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Backtest Momentum Breakout with Volume")
    parser.add_argument("--coin", default=None, help="Cryptocurrency (overrides config)")
    parser.add_argument("--tf", default=None, help="Candle timeframe (overrides config)")
    parser.add_argument("--days", type=int, default=30, help="Days of history to fetch")
    parser.add_argument("--capital", type=float, default=10_000.0, help="Starting capital ($)")
    parser.add_argument("--csv", default="", help="Load candles from CSV instead of fetching")
    parser.add_argument("--save-csv", default="", help="Save fetched candles to CSV for reuse")
    parser.add_argument("--config", default="config.json", help="Strategy config file")
    parser.add_argument("--out-trades", default="results/trades.csv")
    parser.add_argument("--out-equity", default="results/equity.csv")
    parser.add_argument("--testnet", action="store_true", help="Use Hyperliquid testnet for data")
    args = parser.parse_args()

    cfg = StrategyConfig.from_file(args.config)
    if args.coin:
        cfg.coin = args.coin
    if args.tf:
        cfg.timeframe = args.tf

    network_name = "testnet" if args.testnet else "mainnet"

    log.info("Config: coin=%s tf=%s lookback=%d vol_mult=%.1f confirm=%d pos_size=%.2f atr_stop=%.1f tp_mult=%.1f range_atr=%.1f trail=%s",
             cfg.coin, cfg.timeframe, cfg.lookback_periods, cfg.volume_multiplier,
             cfg.confirm_candles, cfg.position_size_pct, cfg.atr_stop_multiplier,
             cfg.tp_range_multiplier, cfg.min_range_atr_ratio, cfg.trailing_stop)

    if args.csv:
        log.info("Loading candles from %s", args.csv)
        candles = load_candles_csv(args.csv)
    else:
        log.info("Fetching %d days of %s %s candles from Hyperliquid %s", args.days, cfg.coin, cfg.timeframe, network_name)
        candles = fetch_candles_historical(cfg.coin, cfg.timeframe, args.days, use_testnet=args.testnet)
        if args.save_csv:
            save_candles_csv(candles, args.save_csv)

    if len(candles) < cfg.lookback_periods + cfg.atr_period + 10:
        log.error("Not enough candle data (%d candles). Need at least %d.", len(candles), cfg.lookback_periods + cfg.atr_period + 10)
        return

    log.info("Running backtest on %d candles", len(candles))
    engine = BacktestEngine(candles, cfg, initial_capital=args.capital)
    result = engine.run()

    print(result.summary())
    result.trades_to_csv(args.out_trades)
    result.equity_to_csv(args.out_equity)


if __name__ == "__main__":
    main()
