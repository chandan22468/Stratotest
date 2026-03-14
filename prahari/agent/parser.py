# agent/parser.py
# Groq LLM parser — uses AsyncGroq for non-blocking execution
# Handles Universal JSON DSL logic

import json
import os
import hashlib
from groq import AsyncGroq
from agent.prompts import SYSTEM_PROMPT, AI_STRATEGIST_PROMPT

# ── Performance Caching ──────────────────────────────────────
LLM_CACHE_DIR = os.path.join(os.getcwd(), ".cache", "llm")
os.makedirs(LLM_CACHE_DIR, exist_ok=True)

def _get_cache_path(key_data: str, prefix: str) -> str:
    h = hashlib.md5(key_data.encode()).hexdigest()
    return os.path.join(LLM_CACHE_DIR, f"{prefix}_{h}.json")

# ── Load API Key from Environment ────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
client = AsyncGroq(api_key=GROQ_API_KEY)


async def generate_ai_insight(results: dict) -> str:
    """
    Generates a professional 'Chief Strategist' take on the backtest results.
    """
    if not results or "metrics" not in results:
        return "No sufficient data for AI insight."

    m = results.get("metrics", {})
    vbt = results.get("vbt_analytics", {})
    
    # 1. Check Cache
    cache_key = f"{results.get('strategy_name')}_{results.get('ticker')}_{results.get('timeframe')}_{m.get('total_return_pct')}"
    cache_path = _get_cache_path(cache_key, "insight")

    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f).get("insight", "")
        except: pass

    # 2. Format Prompt
    prompt_user_content = AI_STRATEGIST_PROMPT.format(
        strategy_name=results.get("strategy_name", "Unknown Strategy"),
        ticker=results.get("ticker", "Unknown Asset"),
        timeframe=results.get("timeframe", "Unknown Timeframe"),
        total_return=round(m.get("total_return_pct", 0), 2),
        win_rate=round(m.get("win_rate", 0), 2),
        profit_factor=round(vbt.get("profit_factor", 0), 2),
        max_drawdown=round(m.get("max_drawdown_pct", 0), 2),
        sortino=round(vbt.get("sortino_ratio", 0), 2)
    )

    # 3. Call LLM (Async)
    try:
        response = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            max_tokens=250,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt_user_content}]
        )
        insight = response.choices[0].message.content.strip()
        
        # Save cache
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump({"insight": insight}, f)
            
        return insight
    except Exception as e:
        print(f"[parser.py] AI Insight failed: {e}")
        return "The strategist is currently unavailable, but your metrics are ready review below."


async def parse_strategy(user_input: str) -> dict:
    """
    Tries AI first (Async), with caching and regex fallback.
    """
    ui_lower = user_input.lower().strip()
    
    # ── Check Cache ──────────────────────────────────────────
    cache_path = _get_cache_path(ui_lower, "parse")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                print(f"[parser.py] Loading parse result from cache...")
                return json.load(f)
        except: pass

    # ── Try AI (Turbo Mode) ──────────────────────────────────
    models = ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"]
    last_error = None
    
    for model in models:
        try:
            response = await client.chat.completions.create(
                model=model,
                max_tokens=1000,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_input}
                ],
                response_format={"type": "json_object"}
            )
            raw_text = response.choices[0].message.content.strip()
            parsed = json.loads(raw_text)
            
            if parsed:
                # Normalize and cache
                parsed = _normalize(parsed)
                try:
                    with open(cache_path, 'w', encoding='utf-8') as f:
                        json.dump(parsed, f)
                except: pass
                return parsed
            
        except Exception as e:
            last_error = e
            if "429" in str(e): continue
            else: break

    # ── Safety Net: Basic Regex Fallback (If AI is down) ──────
    # Try to extract ticker from input
    detected_ticker = None
    if "bitcoin" in ui_lower or "btc" in ui_lower: detected_ticker = "BTC-USD"
    elif "eth" in ui_lower: detected_ticker = "ETH-USD"
    elif "sol" in ui_lower: detected_ticker = "SOL-USD"
    elif "reliance" in ui_lower: detected_ticker = "RELIANCE.NS"
    elif "nifty" in ui_lower: detected_ticker = "^NSEI"
    
    if "rsi" in ui_lower:
        return _normalize({
            "clarification_needed": detected_ticker is None,
            "question": "Which asset should I test this RSI strategy on?" if detected_ticker is None else None,
            "strategy_id": "universal", "strategy_name": "RSI (Fallback)",
            "ticker": detected_ticker, "market": "india_equity" if ".NS" in str(detected_ticker) or "^" in str(detected_ticker) else "crypto",
            "indicators": [{"id": "rsi1", "type": "rsi", "params": {"period": 14}}],
            "logic": {"op": "AND", "conditions": [{"left": "rsi1", "op": "lt", "right": 30}]},
            "notes": "⚠️ AI Busy (Rate Limit). Used basic RSI extraction."
        })
    
    if "ema" in ui_lower or "ma" in ui_lower:
        return _normalize({
            "clarification_needed": detected_ticker is None,
            "question": "Which asset should I test this MA Crossover on?" if detected_ticker is None else None,
            "strategy_id": "universal", "strategy_name": "MA Cross (Fallback)",
            "ticker": detected_ticker, "market": "india_equity" if ".NS" in str(detected_ticker) or "^" in str(detected_ticker) else "crypto",
            "indicators": [{"id": "ma1", "type": "ema", "params": {"period": 50}}, {"id": "ma2", "type": "ema", "params": {"period": 200}}],
            "logic": {"op": "AND", "conditions": [{"left": "ma1", "op": "crosses_above", "right": "ma2"}]},
            "notes": "⚠️ AI Busy (Rate Limit). Used basic MA extraction."
        })
        
    # If we get here, AI failed and we have no fallback pattern
    raise ValueError(f"AI Parse Failed (Rate Limit). Please try again or simplify your request. Error: {last_error}")


def _normalize(parsed: dict) -> dict:
    """Ensures consistent format for the engine"""
    # 1. Map legacy strategy_params if present
    sp  = parsed.get("strategy_params", {})
    el  = parsed.get("exit_logic", {})
    sl  = el.get("stop_loss", {})
    tp  = el.get("take_profit", {})

    # 2. Preserve/Initialize DSL keys ONLY if they are part of the core rules
    # We allow them to be None if not provided, so backtester can decide
    parsed["indicators"] = parsed.get("indicators")
    parsed["logic"]      = parsed.get("logic")

    # 3. Create unified entry/exit blocks for standard strategies
    # (The UniversalStrategy will ignore these if DSL is present)
    parsed["entry"] = {
        "indicator":    sp.get("indicator"),
        "condition":    parsed.get("entry_condition", "crosses_above"),
        "direction":    sp.get("direction", "bullish"),
        "params":       sp
    }

    parsed["stop_loss"] = {
        "type":           sl.get("type", "swing_low"),
        "lookback":       sl.get("lookback", 5),
        "value":          sl.get("value")
    }

    parsed["take_profit"] = {
        "type":  tp.get("type", "risk_reward"),
        "ratio": tp.get("ratio", 2.0)
    }

    return parsed
