# frontend/app.py
# Streamlit frontend — calls FastAPI backend
# Run: streamlit run frontend/app.py

import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go

API_URL = "http://localhost:8000/api/v1"

# ── Page config ───────────────────────────────────────────────
st.set_page_config(
    page_title="Prahari — AI Backtester",
    page_icon="📊",
    layout="wide"
)


# ══════════════════════════════════════════════════════════════
# CHART FUNCTIONS — defined first so they can be called below
# ══════════════════════════════════════════════════════════════

def render_price_chart(data):
    candles    = data["candles"]
    trades     = data["trades"]
    indicators = data["indicators"]

    fig = go.Figure()

    # Candlestick
    fig.add_trace(go.Candlestick(
        x    =[c["time"]  for c in candles],
        open =[c["open"]  for c in candles],
        high =[c["high"]  for c in candles],
        low  =[c["low"]   for c in candles],
        close=[c["close"] for c in candles],
        name="Price",
        increasing_line_color="#26a69a",
        decreasing_line_color="#ef5350"
    ))

    # Indicator lines (EMA, SMA etc)
    colors = ["#ff9800", "#2196f3", "#9c27b0", "#4caf50"]
    for idx, (name, series) in enumerate(indicators.items()):
        if series:
            fig.add_trace(go.Scatter(
                x   =[s["time"]  for s in series],
                y   =[s["value"] for s in series],
                name=name,
                line=dict(color=colors[idx % len(colors)], width=1.5)
            ))

    # Trade entry markers (green triangle up)
    entry_times  = [t["entry_time"]  for t in trades]
    entry_prices = [t["entry_price"] for t in trades]
    fig.add_trace(go.Scatter(
        x=entry_times, y=entry_prices,
        mode="markers",
        name="Entry",
        marker=dict(symbol="triangle-up", color="#26a69a", size=12)
    ))

    # Trade exit markers (green = win, red = loss)
    for trade in trades:
        color = "#26a69a" if trade["result"] == "win" else "#ef5350"
        fig.add_trace(go.Scatter(
            x=[trade["exit_time"]],
            y=[trade["exit_price"]],
            mode="markers",
            showlegend=False,
            marker=dict(symbol="triangle-down", color=color, size=12)
        ))

    fig.update_layout(
        template="plotly_dark",
        height=520,
        xaxis_rangeslider_visible=False,
        title=f"{data['ticker']} — {data['timeframe']} — {data['strategy_name']}",
        legend=dict(orientation="h", yanchor="bottom", y=1.02)
    )
    st.plotly_chart(fig, use_container_width=True)


def render_equity_curve(data):
    curve = data["equity_curve"]
    if not curve:
        st.info("No equity data")
        return
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x   =[e["time"]  for e in curve],
        y   =[e["value"] for e in curve],
        fill="tozeroy",
        fillcolor="rgba(38,166,154,0.15)",
        line=dict(color="#26a69a", width=2),
        name="Portfolio Value"
    ))
    fig.update_layout(
        template="plotly_dark", height=350,
        title="💰 Equity Curve",
        yaxis_title="Portfolio Value (₹)"
    )
    st.plotly_chart(fig, use_container_width=True)


def render_drawdown(data):
    curve = data["drawdown_curve"]
    if not curve:
        st.info("No drawdown data")
        return
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x   =[e["time"]  for e in curve],
        y   =[e["value"] for e in curve],
        fill="tozeroy",
        fillcolor="rgba(239,83,80,0.2)",
        line=dict(color="#ef5350", width=1.5),
        name="Drawdown %"
    ))
    fig.update_layout(
        template="plotly_dark", height=350,
        title="📉 Drawdown Chart",
        yaxis_title="Drawdown %"
    )
    st.plotly_chart(fig, use_container_width=True)


def render_trade_log(data):
    trades = data["trades"]
    if not trades:
        st.info("No trades generated")
        return
    df = pd.DataFrame(trades)
    df["result"] = df["result"].apply(
        lambda x: "✅ WIN" if x == "win" else "❌ LOSS"
    )
    df["pnl"] = df["pnl"].apply(lambda x: f"₹{x:,.2f}")
    st.dataframe(df[[
        "trade_number", "entry_time", "exit_time",
        "entry_price", "exit_price", "sl_price", "tp_price",
        "result", "pnl", "rr_achieved"
    ]], use_container_width=True)


# ══════════════════════════════════════════════════════════════
# MAIN UI
# ══════════════════════════════════════════════════════════════

# ── Header ────────────────────────────────────────────────────
st.markdown("# 📊 Prahari — Agentic AI Backtesting")
st.markdown("*Describe your trading strategy in plain English. Get results in seconds.*")
st.divider()

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuration")
    ticker    = st.text_input("Ticker", value="RELIANCE.NS",
                              help="NSE: RELIANCE.NS | Index: ^NSEI | Crypto: BTC-USD")
    timeframe = st.selectbox("Timeframe", ["5m","15m","30m","1h","4h","1d"], index=3)
    period    = st.selectbox("Backtest Period", ["1y","2y","3y","5y"], index=1)
    capital   = st.number_input("Initial Capital (₹)", value=100000, step=10000)
    market    = st.selectbox("Market", ["india_equity","us_equity","crypto","forex"])

    st.divider()
    st.markdown("**📋 Quick Strategies**")
    st.caption("Click to prefill — edit and submit")

    examples = [
        ("MA Crossover",  "Buy when 50 EMA crosses above 200 EMA, SL below last swing low, 1:2 RR"),
        ("RSI Reversal",  "Buy when RSI drops below 30 and bounces back, SL below swing low, 1:2 RR"),
        ("Order Block",   "Buy at bullish order block, SL below the OB, 1:3 RR"),
        ("FVG Entry",     "Buy when price fills bullish fair value gap, SL below FVG, 1:2 RR"),
        ("Fibonacci",     "Buy at 0.618 fibonacci level in uptrend, SL below swing low, 1:2 RR"),
        ("BOS Pullback",  "Buy after break of structure pullback, SL below BOS level, 1:2 RR"),
    ]

    for label, example in examples:
        if st.button(label, use_container_width=True):
            st.session_state["prefill"] = example

    st.divider()

    # API status check
    try:
        r = requests.get(f"{API_URL}/health", timeout=2)
        if r.status_code == 200:
            st.success("✅ API Connected")
        else:
            st.error("❌ API Error")
    except:
        st.error("❌ API Offline — run: uvicorn main:app --reload")

# ── Session state init ────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "prefill" not in st.session_state:
    st.session_state["prefill"] = ""

# ── Display chat history ──────────────────────────────────────
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# ── Strategy input ────────────────────────────────────────────
prefill = st.session_state.get("prefill", "")
if prefill:
    st.session_state["prefill"] = ""  # clear after reading

prompt = st.chat_input(
    placeholder="e.g. Buy when 50 EMA crosses above 200 EMA, SL below swing low, 1:2 RR"
)

# Use prefill if a quick button was clicked
if prefill and not prompt:
    prompt = prefill

# ── Run on submit ─────────────────────────────────────────────
if prompt:
    st.session_state["messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):

        # Step 1 — Parse strategy
        with st.spinner("🧠 Parsing strategy with AI..."):
            try:
                parse_resp = requests.post(
                    f"{API_URL}/parse",
                    params={"user_input": prompt},
                    timeout=30
                )
                if parse_resp.status_code == 200:
                    parsed = parse_resp.json()["parsed_rules"]
                    with st.expander("📋 Parsed Strategy Rules (JSON)"):
                        st.json(parsed)
                else:
                    st.error(f"Parse failed: {parse_resp.json().get('detail')}")
                    st.stop()
            except Exception as e:
                st.error(f"Parse error: {e}")
                st.stop()

        # Step 2 — Run backtest
        with st.spinner("⚡ Running backtest with realistic friction modelling..."):
            try:
                bt_resp = requests.post(
                    f"{API_URL}/backtest",
                    json={
                        "user_input":      prompt,
                        "ticker":          ticker,
                        "timeframe":       timeframe,
                        "period":          period,
                        "initial_capital": capital,
                        "market":          market
                    },
                    timeout=120
                )
                if bt_resp.status_code != 200:
                    st.error(f"Backtest failed: {bt_resp.json().get('detail')}")
                    st.stop()
                data = bt_resp.json()
            except Exception as e:
                st.error(f"Backtest error: {e}")
                st.stop()

        # ── Warnings ──────────────────────────────────────────
        for w in data.get("warnings", []):
            st.warning(w)

        # ── Confidence badge ──────────────────────────────────
        conf = data["confidence"]
        conf_color = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(conf, "⚪")
        st.caption(f"{conf_color} Confidence: {data['confidence_reason']}")

        # ── Key metrics ───────────────────────────────────────
        st.markdown("### 📊 Performance Summary")
        m = data["metrics"]
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Total Trades",  m["total_trades"])
        c2.metric("Win Rate",      f"{m['win_rate']}%")
        c3.metric("Total Return",  f"{m['total_return_pct']}%")
        c4.metric("Annual Return", f"{m['annual_return_pct']}%")

        c5,c6,c7,c8 = st.columns(4)
        c5.metric("Sharpe Ratio",  m["sharpe_ratio"])
        c6.metric("Max Drawdown",  f"{m['max_drawdown_pct']}%")
        c7.metric("Profit Factor", m["profit_factor"])
        c8.metric("Avg RR",        m["avg_rr_achieved"])

        c9,c10,c11,c12 = st.columns(4)
        c9.metric("Max Consec. Wins",   m["max_consec_wins"])
        c10.metric("Max Consec. Loss",  m["max_consec_losses"])
        c11.metric("Avg Win (₹)",       f"₹{m['avg_win_inr']:,.0f}")
        c12.metric("Avg Loss (₹)",      f"₹{m['avg_loss_inr']:,.0f}")

        # ── Charts ────────────────────────────────────────────
        st.divider()
        tab1, tab2, tab3, tab4 = st.tabs([
            "📈 Price Chart",
            "💰 Equity Curve",
            "📉 Drawdown",
            "📋 Trade Log"
        ])

        with tab1:
            render_price_chart(data)
        with tab2:
            render_equity_curve(data)
        with tab3:
            render_drawdown(data)
        with tab4:
            render_trade_log(data)

        # ── Friction comparison (your killer feature) ─────────
        st.divider()
        st.markdown("### 🔍 Friction Impact (Reality vs Fantasy)")
        fc1, fc2, fc3 = st.columns(3)
        fc1.metric("Return WITH Friction",
                   f"{m['total_return_pct']}%",
                   help="Realistic — includes all costs")
        fc2.metric("Return WITHOUT Friction",
                   f"{m['return_without_friction']}%",
                   help="What most backtesting tools show")
        fc3.metric("Hidden Cost of Trading",
                   f"₹{m['total_friction_cost']:,.0f}",
                   delta=f"-{round(m['return_without_friction'] - m['total_return_pct'], 2)}%",
                   delta_color="inverse")

        # ── Save to chat history ──────────────────────────────
        summary = (
            f"✅ **{data['strategy_name']}** on {ticker} | "
            f"{m['total_trades']} trades | "
            f"Win: {m['win_rate']}% | "
            f"Return: {m['total_return_pct']}% | "
            f"Sharpe: {m['sharpe_ratio']} | "
            f"Max DD: {m['max_drawdown_pct']}%"
        )
        st.session_state["messages"].append({"role": "assistant", "content": summary})
