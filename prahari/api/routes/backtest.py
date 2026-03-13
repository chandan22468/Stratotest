# api/routes/backtest.py
import traceback
from fastapi import APIRouter, HTTPException
from api.models.request import BacktestRequest
from api.models.response import BacktestResponse
from agent.parser import parse_strategy
from engine.data import fetch_data, get_warnings
from engine.backtester import run_backtest
from engine.tearsheet import generate_tearsheet

router = APIRouter(tags=["backtest"])


@router.post("/backtest", response_model=BacktestResponse)
async def backtest(request: BacktestRequest):
    try:
        # Step 1 — LLM parses strategy
        parsed_rules = await parse_strategy(request.user_input)

        # Step 2 — Resolve ticker (LLM detected or user provided)
        ticker = request.ticker
        if ticker in ("AUTO", "", None):
            ticker = parsed_rules.get("ticker")
            if not ticker:
                raise HTTPException(
                    status_code=400,
                    detail="Could not detect asset. Please mention asset name e.g. 'nifty', 'bitcoin', 'gold'"
                )

        # Step 3 — Use LLM interval/period if user left defaults
        timeframe = request.timeframe.value
        period    = request.period.value

        # Override with LLM detected values if available
        if parsed_rules.get("interval"):
            timeframe = parsed_rules["interval"]
        if parsed_rules.get("period"):
            period = parsed_rules["period"]

        # Step 4 — Get warnings
        warnings = get_warnings(timeframe, period)

        # Step 5 — Fetch data
        df = fetch_data(ticker=ticker, timeframe=timeframe, period=period)
        if df is None or df.empty:
            raise HTTPException(
                status_code=400,
                detail=f"No data for '{ticker}' on {timeframe}. Try different timeframe or period."
            )

        # Step 6 — Detect market from LLM if not specified
        market = request.market.value
        if parsed_rules.get("market"):
            market = parsed_rules["market"]

        # Step 7 — Run backtest
        results = run_backtest(
            df=df,
            rules=parsed_rules,
            market=market,
            initial_capital=request.initial_capital
        )

        # Step 8 — Generate tearsheet
        response = generate_tearsheet(
            results=results,
            df=df,
            parsed_rules=parsed_rules,
            ticker=ticker,
            timeframe=timeframe,
            period=period
        )

        response.warnings = warnings + response.warnings
        return response

    except HTTPException:
        raise
    except Exception as e:
        print("=== FULL ERROR ===")
        traceback.print_exc()
        print("==================")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/parse")
async def parse_only(user_input: str):
    """Test LLM parsing — see exactly what JSON is returned"""
    try:
        rules = await parse_strategy(user_input)
        return {"success": True, "parsed_rules": rules}
    except Exception as e:
        print("=== PARSE ERROR ===")
        traceback.print_exc()
        print("===================")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/timeframes")
def get_timeframes():
    return {
        "timeframes": [
            {"value": "1m",  "display": "1 Minute",  "max_history": "7 days",   "warning": True},
            {"value": "5m",  "display": "5 Minutes", "max_history": "60 days",  "warning": True},
            {"value": "15m", "display": "15 Minutes","max_history": "60 days",  "warning": True},
            {"value": "30m", "display": "30 Minutes","max_history": "60 days",  "warning": True},
            {"value": "1h",  "display": "1 Hour",    "max_history": "2 years",  "warning": False},
            {"value": "4h",  "display": "4 Hour",    "max_history": "2 years",  "warning": False},
            {"value": "1d",  "display": "Daily",     "max_history": "10 years", "warning": False},
            {"value": "1wk", "display": "Weekly",    "max_history": "20 years", "warning": False},
        ]
    }
