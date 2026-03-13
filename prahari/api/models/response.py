# api/models/response.py
# All response models — what frontend receives

from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class TradeResult(BaseModel):
    trade_number:  int
    entry_time:    str
    exit_time:     str
    entry_price:   float
    exit_price:    float
    sl_price:      float
    tp_price:      float
    result:        str       # "win" or "loss"
    pnl:           float     # profit/loss in INR
    pnl_pct:       float     # profit/loss in %
    rr_achieved:   float     # actual RR ratio achieved
    friction_cost: float     # total cost of trade


class PerformanceMetrics(BaseModel):
    total_trades:        int
    winning_trades:      int
    losing_trades:       int
    win_rate:            float
    total_return_pct:    float
    total_return_inr:    float
    annual_return_pct:   float
    sharpe_ratio:        float
    max_drawdown_pct:    float
    profit_factor:       float
    avg_rr_achieved:     float
    calmar_ratio:        float
    max_consec_wins:     int
    max_consec_losses:   int
    avg_win_inr:         float
    avg_loss_inr:        float
    total_friction_cost: float
    return_without_friction: float


class CandleData(BaseModel):
    time:   str
    open:   float
    high:   float
    low:    float
    close:  float
    volume: float


class BacktestResponse(BaseModel):
    # Strategy info
    strategy_name:   str
    ticker:          str
    timeframe:       str
    period:          str
    parsed_rules:    Dict[str, Any]

    # Performance
    metrics:         PerformanceMetrics

    # Trade log
    trades:          List[TradeResult]

    # Chart data (sent to frontend for rendering)
    candles:         List[CandleData]
    equity_curve:    List[Dict]          # [{time, value}]
    drawdown_curve:  List[Dict]          # [{time, value}]

    # Indicator data for chart
    indicators:      Dict[str, List[Dict]]  # {ema_50: [{time, value}]}

    # Zones for chart
    zones:           Dict[str, List[Dict]]  # {order_blocks: [{top, bottom, start, end}]}

    # Warnings and confidence
    warnings:        List[str]
    confidence:      str             # "low" / "medium" / "high"
    confidence_reason: str
