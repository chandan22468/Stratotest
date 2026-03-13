# engine/data.py
# Fetches historical OHLCV data from yfinance
# All timeframes supported with honest limitation handling

import yfinance as yf
import pandas as pd

# ── Timeframe config ──────────────────────────────────────────
TIMEFRAME_CONFIG = {
    "1m": {
        "yf_interval": "1m",
        "max_period":  "7d",
        "display":     "1 Minute",
        "warning":     "⚠️ Only 7 days available for 1min data (yfinance limit)"
    },
    "5m": {
        "yf_interval": "5m",
        "max_period":  "60d",
        "display":     "5 Minutes",
        "warning":     "⚠️ Only 60 days available for 5min data (yfinance limit)"
    },
    "15m": {
        "yf_interval": "15m",
        "max_period":  "60d",
        "display":     "15 Minutes",
        "warning":     "⚠️ Only 60 days available for 15min data (yfinance limit)"
    },
    "30m": {
        "yf_interval": "30m",
        "max_period":  "60d",
        "display":     "30 Minutes",
        "warning":     "⚠️ Only 60 days available for 30min data (yfinance limit)"
    },
    "1h": {
        "yf_interval": "1h",
        "max_period":  "2y",
        "display":     "1 Hour",
        "warning":     None
    },
    "4h": {
        "yf_interval": "1h",       # fetch 1H → resample to 4H
        "max_period":  "2y",
        "display":     "4 Hour",
        "warning":     "ℹ️ 4H candles resampled from 1H data"
    },
    "1d": {
        "yf_interval": "1d",
        "max_period":  "10y",
        "display":     "Daily",
        "warning":     None
    },
    "1wk": {
        "yf_interval": "1wk",
        "max_period":  "20y",
        "display":     "Weekly",
        "warning":     None
    }
}

# ── Period config ─────────────────────────────────────────────
PERIOD_CONFIG = {
    "7d":  "7d",
    "60d": "60d",
    "1y":  "1y",
    "2y":  "2y",
    "3y":  "3y",
    "5y":  "5y",
    "10y": "10y",
}

# ── Period to days mapping ────────────────────────────────────
PERIOD_DAYS = {
    "7d":  7,
    "60d": 60,
    "1y":  365,
    "2y":  730,
    "3y":  1095,
    "5y":  1825,
    "10y": 3650,
    "20y": 7300,
}


def fetch_data(ticker: str, timeframe: str, period: str) -> pd.DataFrame:
    """
    Fetches OHLCV data for given ticker, timeframe and period.
    Returns clean DataFrame: Open, High, Low, Close, Volume
    Returns None if fetch fails.
    """
    config = TIMEFRAME_CONFIG.get(timeframe)
    if not config:
        raise ValueError(f"Unsupported timeframe: {timeframe}. Supported: {list(TIMEFRAME_CONFIG.keys())}")

    # Cap period to what yfinance supports for this timeframe
    actual_period = _cap_period(period, config["max_period"])

    try:
        df = yf.download(
            tickers=ticker,
            period=actual_period,
            interval=config["yf_interval"],
            auto_adjust=True,
            progress=False
        )

        if df is None or df.empty:
            return None

        # Fix MultiIndex columns from yfinance
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Keep only OHLCV
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.dropna(inplace=True)

        # Resample 1H → 4H if needed
        if timeframe == "4h":
            df = _resample_to_4h(df)

        return df

    except Exception as e:
        print(f"[data.py] Failed to fetch {ticker} {timeframe}: {e}")
        return None


def get_warnings(timeframe: str, period: str) -> list:
    """Returns data limitation warnings for this timeframe/period combo"""
    warnings = []
    config = TIMEFRAME_CONFIG.get(timeframe, {})

    if config.get("warning"):
        warnings.append(config["warning"])

    # Warn if period was capped
    max_days = PERIOD_DAYS.get(config.get("max_period", "2y"), 730)
    req_days = PERIOD_DAYS.get(period, 730)
    if req_days > max_days:
        warnings.append(
            f"⚠️ Requested {period} but only {config['max_period']} "
            f"available for {timeframe} timeframe"
        )

    return warnings


def get_available_periods(timeframe: str) -> list:
    """Returns available backtest periods for a given timeframe"""
    config = TIMEFRAME_CONFIG.get(timeframe, {})
    max_period = config.get("max_period", "2y")
    max_days = PERIOD_DAYS.get(max_period, 730)

    available = []
    for period, days in PERIOD_DAYS.items():
        if days <= max_days:
            available.append(period)
    return available


# ── Private helpers ───────────────────────────────────────────

def _resample_to_4h(df: pd.DataFrame) -> pd.DataFrame:
    """Resample 1H candles into 4H candles"""
    df_4h = df.resample("4H").agg({
        "Open":   "first",
        "High":   "max",
        "Low":    "min",
        "Close":  "last",
        "Volume": "sum"
    }).dropna()
    return df_4h


def _cap_period(requested: str, max_available: str) -> str:
    """Cap requested period to what yfinance supports"""
    req_days = PERIOD_DAYS.get(requested, 730)
    max_days = PERIOD_DAYS.get(max_available, 730)
    if req_days > max_days:
        return max_available
    return requested
