# agent/parser.py
# Gemini LLM parser — uses google-generativeai for non-blocking execution
# Handles Universal JSON DSL logic

import json
import os
import hashlib
from google import genai
from google.genai import types
from agent.prompts import SYSTEM_PROMPT, AI_STRATEGIST_PROMPT
from dotenv import load_dotenv

load_dotenv()

# ── Performance Caching ──────────────────────────────────────
LLM_CACHE_DIR = os.path.join(os.getcwd(), ".cache", "llm")
os.makedirs(LLM_CACHE_DIR, exist_ok=True)

def _get_cache_path(key_data: str, prefix: str) -> str:
    h = hashlib.md5(key_data.encode()).hexdigest()
    return os.path.join(LLM_CACHE_DIR, f"{prefix}_{h}.json")

# ── Load API Key from Environment ────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Initialize client globally
client = None
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    print("[parser.py] WARNING: GEMINI_API_KEY is not set.")

async def _generate_with_fallback(contents, config=None, is_parser=False):
    """
    Tries multiple Gemini models in sequence to mitigate rate limits.
    """
    models = ['gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-1.5-pro']
    last_err = None

    for model_name in models:
        try:
            print(f"[parser.py] Attempting generation with {model_name}...")
            if is_parser and config:
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config
                )
            else:
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=contents
                )
            
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            print(f"[parser.py] Model {model_name} failed: {e}")
            last_err = e
            if "429" not in str(e) and "RESOURCE_EXHAUSTED" not in str(e):
                # If it's not a rate limit, maybe it's a prompt issue? 
                # Keep trying other models just in case, or break if it's fatal.
                pass
            continue
            
    raise last_err

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

    # 3. Call LLM (With Fallback)
    try:
        insight = await _generate_with_fallback(prompt_user_content)
        
        # Save cache
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump({"insight": insight}, f)
            
        return insight
    except Exception as e:
        print(f"[parser.py] AI Insight failed: {e}")
        return "The strategist is currently unavailable, but your metrics are ready to review below."


async def parse_strategy(user_input: str) -> dict:
    """
    Tries AI first (Async) via Gemini, with caching and regex fallback.
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

    # ── Try AI (Gemini with Fallback) ──────────────────────────
    last_error = None
    
    try:
        raw_text = await _generate_with_fallback(
            contents=user_input,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
            ),
            is_parser=True
        )

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

    # ── Safety Net: Basic Regex Fallback (If AI is down) ──────
    # Try to extract ticker from input (DO NOT CACHE FALLBACKS)
    print(f"[parser.py] AI Parsing failed. Falling back to regex. Error: {last_error}")
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
            "notes": "⚠️ AI Busy. Used basic RSI extraction."
        })
    
    if "ema" in ui_lower or "ma" in ui_lower:
        return _normalize({
            "clarification_needed": detected_ticker is None,
            "question": "Which asset should I test this MA Crossover on?" if detected_ticker is None else None,
            "strategy_id": "universal", "strategy_name": "MA Cross (Fallback)",
            "ticker": detected_ticker, "market": "india_equity" if ".NS" in str(detected_ticker) or "^" in str(detected_ticker) else "crypto",
            "indicators": [{"id": "ma1", "type": "ema", "params": {"period": 50}}, {"id": "ma2", "type": "ema", "params": {"period": 200}}],
            "logic": {"op": "AND", "conditions": [{"left": "ma1", "op": "crosses_above", "right": "ma2"}]},
            "notes": "⚠️ AI Busy. Used basic MA extraction."
        })
        
    # If we get here, AI failed and we have no fallback pattern
    raise ValueError(f"AI Parse Failed. Please verify your GEMINI_API_KEY and API Limits. Error: {last_error}")


def _normalize(parsed: dict) -> dict:
    """Ensures consistent format for the engine"""
    # 1. Map legacy strategy_params if present
    sp  = parsed.get("strategy_params", {})
    el  = parsed.get("exit_logic", {})
    sl  = el.get("stop_loss", {})
    tp  = el.get("take_profit", {})

    # 2. Preserve/Initialize DSL keys ONLY if they are part of the core rules
    if "indicators" in parsed:
        parsed["indicators"] = parsed.get("indicators")
    if "logic" in parsed:
        parsed["logic"]      = parsed.get("logic")

    # 3. Create unified entry/exit blocks for standard strategies
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
