"""
Momentum Breakout with Volume — Live Trading Bot for Hyperliquid

Detects price breakouts above/below an N-candle range, confirmed by a volume
spike, and enters with ATR-based stop-losses and range-extension take-profits.
Manages positions with a trailing stop.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import eth_account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class StrategyConfig:
    coin: str = "ETH"
    timeframe: str = "15m"
    lookback_periods: int = 20
    volume_multiplier: float = 1.5
    position_size_pct: float = 0.05       # fraction of account value per trade
    atr_period: int = 14
    atr_stop_multiplier: float = 2.0
    tp_range_multiplier: float = 1.5      # take-profit = range_size * this
    min_range_atr_ratio: float = 2.0      # skip flat ranges
    confirm_candles: int = 1              # candles that must close past breakout level
    trailing_stop: bool = True
    slippage: float = 0.05
    max_atr_percentile: float = 70.0      # skip entries when ATR above this percentile of recent history
    atr_lookback_window: int = 200        # candles used to compute ATR distribution
    blocked_utc_hours: list = field(default_factory=list)  # e.g. [14,15,16,17,18,19,20] to skip US session
    ma_period: int = 0                    # 0 = disabled; >0 = only trade with-trend (price vs MA)

    @classmethod
    def from_file(cls, path: str = "config.json") -> "StrategyConfig":
        p = Path(path)
        if not p.exists():
            return cls()
        with open(p) as f:
            data = json.load(f)
        return cls(**{k: v for k, v in data.get("strategy", {}).items() if k in cls.__dataclass_fields__})


@dataclass
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Position:
    side: str          # "LONG" | "SHORT"
    entry_price: float
    size: float
    stop_loss: float
    take_profit: float
    stop_oid: Optional[int] = None
    tp_oid: Optional[int] = None


# ---------------------------------------------------------------------------
# Timeframe → seconds mapping
# ---------------------------------------------------------------------------

TIMEFRAME_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900,
    "30m": 1800, "1h": 3600, "2h": 7200, "4h": 14400,
    "1d": 86400,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_candles(raw: list[dict]) -> list[Candle]:
    return [
        Candle(
            timestamp=int(c["t"]),
            open=float(c["o"]),
            high=float(c["h"]),
            low=float(c["l"]),
            close=float(c["c"]),
            volume=float(c["v"]),
        )
        for c in raw
    ]


def compute_atr(candles: list[Candle], period: int) -> float:
    trs: list[float] = []
    for i in range(1, len(candles)):
        prev_close = candles[i - 1].close
        c = candles[i]
        tr = max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close))
        trs.append(tr)
    if len(trs) < period:
        return sum(trs) / len(trs) if trs else 0.0
    return sum(trs[-period:]) / period


def load_credentials(path: str = "config.json") -> tuple[str, str, bool]:
    with open(path) as f:
        data = json.load(f)
    return data["secret_key"], data.get("account_address", ""), data.get("use_testnet", False)


def spot_meta_for_perp_bot(api_url: str) -> Optional[dict[str, Any]]:
    """Testnet spot_meta can reference token indices outside tokens[]; SDK Info() crashes with IndexError.
    Perp-only bots do not need spot asset indexing — pass an empty universe so Info/Exchange can init."""
    if api_url.rstrip("/") == constants.TESTNET_API_URL.rstrip("/"):
        return {"universe": [], "tokens": []}
    return None


# ---------------------------------------------------------------------------
# Core strategy
# ---------------------------------------------------------------------------

class MomentumBreakout:
    def __init__(self, config: StrategyConfig, info: Info, exchange: Exchange, address: str):
        self.cfg = config
        self.info = info
        self.exchange = exchange
        self.address = address
        self.position: Optional[Position] = None
        self.log = logging.getLogger("breakout")

    # ---- data ----

    def fetch_candles(self) -> list[Candle]:
        base_need = self.cfg.lookback_periods + self.cfg.atr_period + 5
        needed = max(base_need, self.cfg.ma_period + self.cfg.confirm_candles + 1,
                     self.cfg.atr_lookback_window + self.cfg.confirm_candles + 1)
        interval_s = TIMEFRAME_SECONDS[self.cfg.timeframe]
        now_ms = int(time.time() * 1000)
        start_ms = now_ms - needed * interval_s * 1000
        raw = self.info.candles_snapshot(self.cfg.coin, self.cfg.timeframe, start_ms, now_ms)
        return parse_candles(raw)

    # ---- account ----

    def _spot_usdc_balance(self) -> float:
        try:
            spot = self.info.spot_user_state(self.address)
        except Exception as e:
            self.log.warning("Could not fetch spot balances (spotClearinghouseState): %s", e)
            return 0.0
        for b in spot.get("balances") or []:
            coin = str(b.get("coin", "")).upper()
            if coin == "USDC":
                return float(b.get("total", 0) or 0)
        return 0.0

    def get_account_value(self) -> float:
        """Capital used for sizing in unified-safe order:
        1) marginSummary.accountValue (perp clearinghouse)
        2) withdrawable
        3) spot USDC balance
        """
        state = self.info.user_state(self.address)
        ms = state.get("marginSummary") or {}
        perp_account_value = float(ms.get("accountValue", 0) or 0)
        if perp_account_value > 1e-6:
            return perp_account_value
        withdrawable = float(state.get("withdrawable", 0) or 0)
        if withdrawable > 1e-6:
            return withdrawable
        spot_usdc = self._spot_usdc_balance()
        if spot_usdc > 1e-6:
            return spot_usdc
        return 0.0

    def log_capital_summary(self) -> None:
        """Log perp margin vs spot balances. Perp `accountValue` is often $0 until USDC is moved from spot → perp."""
        ch = self.info.user_state(self.address)
        ms = ch.get("marginSummary") or {}
        cms = ch.get("crossMarginSummary") or {}
        perp = float(ms.get("accountValue", 0) or 0)
        total_raw = float(ms.get("totalRawUsd", 0) or 0)
        withdrawable = float(ch.get("withdrawable", 0) or 0)
        sizing_capital = self.get_account_value()
        source = "marginSummary.accountValue"
        if perp <= 1e-6 and withdrawable > 1e-6:
            source = "withdrawable"
        elif perp <= 1e-6 and withdrawable <= 1e-6:
            source = "spot USDC fallback"
        self.log.info(
            "Perp margin — accountValue=$%.2f, totalRawUsd=$%.2f, withdrawable=$%.2f",
            perp, total_raw, withdrawable,
        )
        self.log.info("Sizing capital = $%.2f (source: %s)", sizing_capital, source)
        if cms:
            self.log.debug("crossMarginSummary accountValue=%s", cms.get("accountValue"))

        spot_usdc = self._spot_usdc_balance()
        if spot_usdc > 1e-12:
            self.log.info("Spot — USDC: total=%.4f", spot_usdc)

        if perp < 1e-6 and spot_usdc > 1e-6:
            self.log.warning("Perp accountValue is $0; using spot USDC fallback ($%.2f) for sizing.", spot_usdc)

    def sync_position_from_exchange(self) -> None:
        """Reconcile local state with what's actually on the exchange."""
        state = self.info.user_state(self.address)
        for pos in state.get("assetPositions", []):
            item = pos["position"]
            if item["coin"] != self.cfg.coin:
                continue
            szi = float(item["szi"])
            if abs(szi) < 1e-12:
                continue
            if self.position is None:
                self.log.info("Detected orphan position szi=%s, tracking it", szi)
                entry = float(item["entryPx"]) if item.get("entryPx") else 0.0
                self.position = Position(
                    side="LONG" if szi > 0 else "SHORT",
                    entry_price=entry,
                    size=abs(szi),
                    stop_loss=0.0,
                    take_profit=0.0,
                )
            return
        if self.position is not None:
            self.log.info("Position closed on-chain, clearing local state")
            self.position = None

    # ---- order helpers ----

    def _place_trigger(self, is_buy: bool, sz: float, trigger_px: float, tpsl: str) -> Optional[int]:
        result = self.exchange.order(
            self.cfg.coin,
            is_buy,
            sz,
            trigger_px,
            order_type={"trigger": {"triggerPx": str(trigger_px), "isMarket": True, "tpsl": tpsl}},
            reduce_only=True,
        )
        if result["status"] == "ok":
            statuses = result["response"]["data"]["statuses"]
            if statuses and "resting" in statuses[0]:
                return statuses[0]["resting"]["oid"]
        self.log.warning("Trigger order response: %s", result)
        return None

    def place_bracket(self, side: str, sz: float, stop_loss: float, take_profit: float) -> tuple[Optional[int], Optional[int]]:
        is_long = side == "LONG"
        sl_oid = self._place_trigger(is_buy=not is_long, sz=sz, trigger_px=stop_loss, tpsl="sl")
        tp_oid = self._place_trigger(is_buy=not is_long, sz=sz, trigger_px=take_profit, tpsl="tp")
        return sl_oid, tp_oid

    def cancel_bracket(self) -> None:
        if self.position is None:
            return
        for oid in (self.position.stop_oid, self.position.tp_oid):
            if oid is not None:
                try:
                    self.exchange.cancel(self.cfg.coin, oid)
                except Exception as e:
                    self.log.debug("Cancel oid %s: %s", oid, e)

    # ---- sizing ----

    def compute_size(self, entry: float, stop: float) -> float:
        acct = self.get_account_value()
        risk_usd = acct * self.cfg.position_size_pct
        risk_per_unit = abs(entry - stop)
        if risk_per_unit == 0:
            return 0.0
        return risk_usd / risk_per_unit

    # ---- main logic ----

    def evaluate(self, candles: list[Candle]) -> Optional[str]:
        """Return 'LONG', 'SHORT', or None."""
        n_confirm = self.cfg.confirm_candles
        if len(candles) < self.cfg.lookback_periods + 1 + n_confirm:
            return None

        # --- session filter ---
        if self.cfg.blocked_utc_hours:
            import datetime
            last_ts = candles[-1].timestamp / 1000
            utc_hour = datetime.datetime.utcfromtimestamp(last_ts).hour
            if utc_hour in self.cfg.blocked_utc_hours:
                return None

        lookback = candles[-(self.cfg.lookback_periods + n_confirm):-n_confirm]
        highest_high = max(c.high for c in lookback)
        lowest_low = min(c.low for c in lookback)
        range_size = highest_high - lowest_low

        avg_volume = sum(c.volume for c in lookback) / len(lookback)
        atr = compute_atr(candles[:-(n_confirm)], self.cfg.atr_period)

        if atr == 0 or range_size < atr * self.cfg.min_range_atr_ratio:
            return None

        # --- ATR regime filter: skip when volatility is already elevated ---
        if self.cfg.max_atr_percentile < 100.0:
            window_len = min(self.cfg.atr_lookback_window, len(candles) - n_confirm - 1)
            if window_len > self.cfg.atr_period:
                historical_atrs = []
                for j in range(self.cfg.atr_period + 1, window_len + 1):
                    slice_end = len(candles) - n_confirm - (window_len - j)
                    slice_start = max(0, slice_end - self.cfg.atr_period - 1)
                    a = compute_atr(candles[slice_start:slice_end], self.cfg.atr_period)
                    if a > 0:
                        historical_atrs.append(a)
                if historical_atrs:
                    historical_atrs.sort()
                    idx = int(len(historical_atrs) * self.cfg.max_atr_percentile / 100)
                    idx = min(idx, len(historical_atrs) - 1)
                    if atr > historical_atrs[idx]:
                        return None

        confirm_slice = candles[-n_confirm:]
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
        if self.cfg.ma_period > 0 and len(candles) >= self.cfg.ma_period:
            ma = sum(c.close for c in candles[-self.cfg.ma_period:]) / self.cfg.ma_period
            if signal == "LONG" and candles[-1].close < ma:
                return None
            if signal == "SHORT" and candles[-1].close > ma:
                return None

        return signal

    def enter(self, signal: str, candles: list[Candle]) -> None:
        current = candles[-1]
        atr = compute_atr(candles[:-1], self.cfg.atr_period)
        lookback = candles[-(self.cfg.lookback_periods + 1):-1]
        range_size = max(c.high for c in lookback) - min(c.low for c in lookback)

        entry_price = current.close
        if signal == "LONG":
            stop_loss = entry_price - atr * self.cfg.atr_stop_multiplier
            take_profit = entry_price + range_size * self.cfg.tp_range_multiplier
        else:
            stop_loss = entry_price + atr * self.cfg.atr_stop_multiplier
            take_profit = entry_price - range_size * self.cfg.tp_range_multiplier

        sz = self.compute_size(entry_price, stop_loss)
        if sz <= 0:
            self.log.warning("Computed size <= 0, skipping")
            return

        is_buy = signal == "LONG"
        self.log.info(
            "ENTRY %s | price=%.4f size=%.6f sl=%.4f tp=%.4f",
            signal, entry_price, sz, stop_loss, take_profit,
        )

        result = self.exchange.market_open(self.cfg.coin, is_buy, sz, slippage=self.cfg.slippage)
        if result["status"] != "ok":
            self.log.error("Market open failed: %s", result)
            return

        sl_oid, tp_oid = self.place_bracket(signal, sz, stop_loss, take_profit)

        self.position = Position(
            side=signal,
            entry_price=entry_price,
            size=sz,
            stop_loss=stop_loss,
            take_profit=take_profit,
            stop_oid=sl_oid,
            tp_oid=tp_oid,
        )

    def update_trailing_stop(self, candles: list[Candle]) -> None:
        if self.position is None or not self.cfg.trailing_stop:
            return

        atr = compute_atr(candles[:-1], self.cfg.atr_period)
        current = candles[-1]

        if self.position.side == "LONG":
            new_stop = current.close - atr * self.cfg.atr_stop_multiplier
            if new_stop > self.position.stop_loss:
                self._move_stop(new_stop)
        else:
            new_stop = current.close + atr * self.cfg.atr_stop_multiplier
            if new_stop < self.position.stop_loss:
                self._move_stop(new_stop)

    def _move_stop(self, new_stop: float) -> None:
        if self.position is None:
            return
        old_oid = self.position.stop_oid
        if old_oid is not None:
            try:
                self.exchange.cancel(self.cfg.coin, old_oid)
            except Exception:
                pass
        is_long = self.position.side == "LONG"
        new_oid = self._place_trigger(
            is_buy=not is_long,
            sz=self.position.size,
            trigger_px=new_stop,
            tpsl="sl",
        )
        self.log.info("TRAIL STOP %.4f → %.4f", self.position.stop_loss, new_stop)
        self.position.stop_loss = new_stop
        self.position.stop_oid = new_oid

    # ---- run loop ----

    def run_once(self) -> None:
        self.sync_position_from_exchange()
        candles = self.fetch_candles()
        if not candles:
            self.log.warning("No candle data returned")
            return

        if self.position is None:
            signal = self.evaluate(candles)
            if signal:
                self.enter(signal, candles)
        else:
            self.update_trailing_stop(candles)

    def run(self) -> None:
        interval = TIMEFRAME_SECONDS.get(self.cfg.timeframe, 900)
        self.log.info(
            "Starting Momentum Breakout | coin=%s tf=%s lookback=%d",
            self.cfg.coin, self.cfg.timeframe, self.cfg.lookback_periods,
        )
        while True:
            try:
                self.run_once()
            except Exception:
                self.log.exception("Error in run loop")
            self.log.debug("Sleeping %ds until next candle close", interval)
            time.sleep(interval)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Momentum Breakout Trading Bot")
    parser.add_argument("--testnet", action="store_true", help="Use Hyperliquid testnet instead of mainnet")
    parser.add_argument("--config", default="config.json", help="Path to config file")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    secret_key, account_address, config_testnet = load_credentials(args.config)
    cfg = StrategyConfig.from_file(args.config)

    # CLI flag overrides config file
    use_testnet = args.testnet or config_testnet
    api_url = constants.TESTNET_API_URL if use_testnet else constants.MAINNET_API_URL
    
    network_name = "TESTNET" if use_testnet else "MAINNET"
    logging.getLogger("breakout").info(f"Starting bot on {network_name}")

    wallet = eth_account.Account.from_key(secret_key)
    sm = spot_meta_for_perp_bot(api_url)
    info = Info(api_url, skip_ws=True, spot_meta=sm)
    exchange = Exchange(wallet, api_url, account_address=account_address or None, spot_meta=sm)
    address = account_address or wallet.address

    bot = MomentumBreakout(cfg, info, exchange, address)
    try:
        bot.log_capital_summary()
    except Exception:
        logging.getLogger("breakout").exception("Failed to fetch capital summary on startup")
    bot.run()


if __name__ == "__main__":
    main()
