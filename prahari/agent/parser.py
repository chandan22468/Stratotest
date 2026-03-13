# agent/parser.py
# Groq LLM parser — uses Gemini optimized prompt
# Handles new JSON schema with strategy_params + exit_logic

import json
from groq import Groq
from agent.prompts import SYSTEM_PROMPT

# ── PASTE YOUR GROQ API KEY HERE ─────────────────────────────
GROQ_API_KEY = "YOUR_GROQ_KEY_HERE"
# Get free key at: https://console.groq.com
# ─────────────────────────────────────────────────────────────

client = Groq(api_key=GROQ_API_KEY)


async def parse_strategy(user_input: str) -> dict:
    """
    Converts plain English strategy to structured JSON
    Uses Gemini-optimized prompt for better accuracy
    """
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=1000,
            temperature=0.1,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_input}
            ]
        )

        raw_text = response.choices[0].message.content.strip()

        # Clean any accidental markdown
        raw_text = raw_text.replace("```json", "").replace("```", "").strip()

        parsed = json.loads(raw_text)

        # Normalize to unified format engine expects
        parsed = _normalize(parsed)

        # Validate required fields
        required = ["strategy_id", "ticker", "market", "interval", "period"]
        for field in required:
            if field not in parsed:
                raise ValueError(f"Missing required field: {field}")

        return parsed

    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned invalid JSON: {e}")
    except Exception as e:
        raise ValueError(f"Strategy parsing failed: {e}")


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
