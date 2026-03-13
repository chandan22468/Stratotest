# agent/parser.py
# Groq LLM parser — uses Gemini optimized prompt
# Handles new JSON schema with strategy_params + exit_logic

import json
from groq import Groq
from agent.prompts import SYSTEM_PROMPT

# ── PASTE YOUR GROQ API KEY HERE ─────────────────────────────
GROQ_API_KEY = "your api key"
# Get free key at: https://console.groq.com
# ─────────────────────────────────────────────────────────────

client = Groq(api_key=GROQ_API_KEY)


async def parse_strategy(user_input: str) -> dict:
    """
    Tries AI first, then falls back to regex for common patterns if AI is down/rate-limited.
    """
    ui_lower = user_input.lower()
    
    # ── Try AI First ──────────────────────────────────────────
    models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
    last_error = None
    parsed = None
    
    for model in models:
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=1000,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_input}
                ]
            )
            raw_text = response.choices[0].message.content.strip()
            raw_text = raw_text.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(raw_text)
            break
        except Exception as e:
            last_error = e
            if "429" in str(e): continue
            else: break
            
    if parsed:
        try:
            # Normalize to unified format engine expects
            parsed = _normalize(parsed)

            # Validate required fields (only if clarification NOT needed)
            if not parsed.get("clarification_needed"):
                required = ["strategy_id", "ticker", "market", "interval", "period"]
                for field in required:
                    if field not in parsed:
                        # If this happens, LLM hallucinated the format
                        raise ValueError(f"Missing required field: {field}")
            return parsed
        except Exception as e:
            last_error = e # Store error for fallback message
            parsed = None # Ensure fallback is triggered

    # ── Safety Net: Regex Fallback ────────────────────────────
    # If LLM fails (rate limit), try to parse very basic strategies
    if "rsi" in ui_lower:
        return _normalize({
            "strategy_id": "rsi_reversal", "strategy_name": "RSI Strategy (Fallback)",
            "ticker": "^NSEI", "market": "india_equity", "interval": "1h", "period": "2y",
            "strategy_params": {"indicator": "RSI", "period": 14, "direction": "bullish"},
            "notes": "⚠️ LLM Rate Limited. Using default RSI parameters on Nifty (2 Years)."
        })
    elif "ema" in ui_lower or "ma" in ui_lower:
        return _normalize({
            "strategy_id": "ma_crossover", "strategy_name": "MA Crossover (Fallback)",
            "ticker": "^NSEI", "market": "india_equity", "interval": "1h", "period": "2y",
            "strategy_params": {"indicator": "EMA", "fast_period": 50, "slow_period": 200},
            "notes": "⚠️ LLM Rate Limited. Using default 50/200 EMA Cross on Nifty (2 Years)."
        })
        
    raise ValueError(f"AI is currently busy (Rate Limit). Please try again in a few minutes or provide a simpler strategy (e.g. 'RSI strategy'). Original error: {last_error}")


def _normalize(parsed: dict) -> dict:
    """
    Normalizes Gemini schema to unified format
    Maps strategy_params + exit_logic -> entry + stop_loss + take_profit
    so the backtest engine can read it consistently
    """
    sp  = parsed.get("strategy_params", {})
    el  = parsed.get("exit_logic", {})
    sl  = el.get("stop_loss", {})
    tp  = el.get("take_profit", {})

    parsed["entry"] = {
        "indicator":    sp.get("indicator"),
        "fast_period":  sp.get("fast_period"),
        "slow_period":  sp.get("slow_period"),
        "period":       sp.get("period"),
        "condition":    parsed.get("entry_condition", "crosses_above"),
        "value":        sp.get("value"),
        "fib_level":    sp.get("fib_level"),
        "direction":    sp.get("direction", "bullish")
    }

    parsed["stop_loss"] = {
        "type":           sl.get("type", "swing_low"),
        "value":          sl.get("value"),
        "atr_multiplier": sl.get("atr_multiplier"),
        "lookback":       sl.get("lookback", 5)
    }

    parsed["take_profit"] = {
        "type":  tp.get("type", "risk_reward"),
        "ratio": tp.get("ratio", 2.0),
        "value": tp.get("value")
    }

    return parsed
