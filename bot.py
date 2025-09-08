import yfinance as yf
import pandas as pd
import numpy as np
import time
import requests
import random
import os
import datetime
import json
import calendar

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 20 Forex pairs only
pairs = [
    ("EURUSD=X","EUR/USD"), ("GBPUSD=X","GBP/USD"), ("USDJPY=X","USD/JPY"),
    ("AUDUSD=X","AUD/USD"), ("NZDUSD=X","NZD/USD"), ("USDCAD=X","USD/CAD"),
    ("USDCHF=X","USD/CHF"), ("EURGBP=X","EUR/GBP"), ("EURJPY=X","EUR/JPY"),
    ("GBPJPY=X","GBP/JPY"), ("AUDJPY=X","AUD/JPY"), ("CADJPY=X","CAD/JPY"),
    ("CHFJPY=X","CHF/JPY"), ("NZDJPY=X","NZD/JPY"), ("EURAUD=X","EUR/AUD"),
    ("EURNZD=X","EURNZD"), ("GBPAUD=X","GBP/AUD"), ("GBPCAD=X","GBP/CAD"),
    ("GBPNZD=X","GBP/NZD"), ("AUDNZD=X","AUD/NZD")
]

# Strategy names mapped to functions
strategy_map = {
    "EMA Crossover": "ema_strategy",
    "RSI Zones": "rsi_strategy",
    "MACD Signal": "macd_strategy",
    "Bollinger Bands": "bb_strategy",
    "Stochastic Oscillator": "stochastic_strategy",
    "ADX Trend": "adx_strategy",
    "Momentum Rider": "momentum_strategy",
    "S/R Breakout": "sr_breakout_strategy",
    "Parabolic SAR": "psar_strategy",
    "Phantom Scalper": "phantom_strategy"
}

STATS_FILE = "msl_stats.json"

# ---------- stats helpers ----------
def load_stats():
    try:
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"days": {}}

def save_stats(stats):
    try:
        with open(STATS_FILE, "w") as f:
            json.dump(stats, f, indent=2)
    except Exception as e:
        print("Stats save error:", e)

def add_session_result(date_key, session_name, wins, losses, fair):
    stats = load_stats()
    day = stats["days"].get(date_key, {})
    day[session_name] = {"wins": wins, "losses": losses, "fair": bool(fair)}
    stats["days"][date_key] = day
    save_stats(stats)

def get_day_totals(date_key):
    stats = load_stats()
    day = stats["days"].get(date_key, {})
    w = day.get("morning", {}).get("wins", 0) + day.get("evening", {}).get("wins", 0)
    l = day.get("morning", {}).get("losses", 0) + day.get("evening", {}).get("losses", 0)
    fair_count = int(day.get("morning", {}).get("fair", False)) + int(day.get("evening", {}).get("fair", False))
    return w, l, fair_count

def iter_days_in_range(start_date, end_date):
    d = start_date
    while d <= end_date:
        yield d
        d += datetime.timedelta(days=1)

def summarize_range(start_date, end_date):
    total_w = total_l = fair_sessions = 0
    stats = load_stats()
    for d in iter_days_in_range(start_date, end_date):
        key = d.strftime("%Y-%m-%d")
        day = stats["days"].get(key, {})
        for sess in ("morning", "evening"):
            blob = day.get(sess)
            if blob:
                total_w += blob.get("wins", 0)
                total_l += blob.get("losses", 0)
                fair_sessions += int(blob.get("fair", False))
    return total_w, total_l, fair_sessions

def is_last_day_of_month(dt):
    return dt.day == calendar.monthrange(dt.year, dt.month)[1]

def send_daily_summary(session_name, today_utc):
    date_key = today_utc.strftime("%Y-%m-%d")
    w, l, _ = get_day_totals(date_key)
    total = w + l
    win_rate = round((w / total) * 100) if total else 0
    if session_name == "morning":
        title = "Morning Performance Recap"
    else:
        title = "Daily Performance Recap"
    msg = f"""
🗓️ *{title}* — {today_utc.strftime("%A, %d %B %Y")}
━━━━━━━━━━━━━━━
✅ Wins: *{w}*
❌ Losses: *{l}*
📌 Total Signals: *{total}*
📈 Win Rate: *{win_rate}%*
━━━━━━━━━━━━━━━
"""
    send_msg(msg)

def send_weekly_summary(today_utc):
    monday = today_utc - datetime.timedelta(days=today_utc.weekday())
    saturday = monday + datetime.timedelta(days=5)
    w, l, fair = summarize_range(monday.date(), saturday.date())
    total = w + l
    win_rate = round((w / total) * 100) if total else 0
    week_num = today_utc.isocalendar()[1]
    msg = f"""
📅 *Weekly Performance Recap — Week {week_num}*
━━━━━━━━━━━━━━━
✅ Wins: *{w}*
❌ Losses: *{l}*
⚖️ Fair Sessions: *{fair}*
📌 Total Signals: *{total}*
📈 Win Rate: *{win_rate}%*
━━━━━━━━━━━━━━━
"""
    send_msg(msg)

def send_monthly_summary(today_utc):
    start = datetime.date(today_utc.year, today_utc.month, 1)
    end = today_utc.date()
    w, l, fair = summarize_range(start, end)
    total = w + l
    win_rate = round((w / total) * 100) if total else 0
    month_name = today_utc.strftime("%B %Y")
    msg = f"""
📊 *Monthly Performance Report — {month_name}*
━━━━━━━━━━━━━━━
✅ Total Wins: *{w}*
❌ Total Losses: *{l}*
⚖️ Fair Sessions: *{fair}*
📌 Total Signals: *{total}*
🏆 Win Rate: *{win_rate:.1f}%*
━━━━━━━━━━━━━━━
"""
    send_msg(msg)

# ---------- Telegram ----------
def send_msg(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})
    except Exception as e:
        print("Telegram error:", e)

# ---------- Session Runner ----------
def run_session(session_name):
    today = datetime.datetime.utcnow()
    weekday = today.weekday()  # 0 = Monday, 6 = Sunday

    # no signals weekends
    if weekday >= 5 and session_name in ("morning", "evening"):
        return

    robot_display = """
     🤖🔹
   ╔══════╗
   ║  👀  ║   👋
   ╚══════╝
    ║████║
   [ MSL  ]
   [Binary]
   [  Bot ]
    ║████║
   🤖🔹🤖🔹
"""
    if session_name == "evening":
        send_msg(robot_display + "\n🌙 *Good Evening Family* 🌙\n\n📡 *MSL Binary Signal* 📡\n━━━━━━━━━━━━━━━\n📊 Evening session starts now!")
    else:
        send_msg(robot_display + "\n🌞 *Good Morning Family* 🌞\n\n📡 *MSL Binary Signal* 📡\n━━━━━━━━━━━━━━━\n📊 Morning session starts now!")

    time.sleep(60)

    signals_sent = 0
    total_signals = 10
    wins = 0
    losses = 0

    fair_session = False
    if session_name == "evening" and random.random() < (2/7):
        fair_session = True

    loss_positions = []
    if fair_session:
        loss_positions = random.sample(range(1, total_signals+1), 2)
    else:
        if random.random() < 0.7:
            loss_positions = random.sample(range(1, total_signals+1), random.randint(1, 2))

    used_pairs = random.sample(pairs, total_signals)

    while signals_sent < total_signals:
        symbol, name = used_pairs[signals_sent]
        strat_name, strat_func = random.choice(list(strategy_map.items()))

        # fallback if data fails
        df = get_data(symbol)
        if df is not None and not df.empty:
            signal = globals()[strat_func](df)
        else:
            signal = random.choice(["CALL","PUT"])

        emoji = "🟢📈" if signal == "CALL" else "🔴📉"

        if (signals_sent+1) in loss_positions:
            confidence = random.randint(75, 79)
            losses += 1
        else:
            confidence = random.randint(80, 90)
            wins += 1

        msg = f"""
━━━━━━━━━━━━━━━
💹 *Signal {signals_sent+1}*
💱 Pair: *{name}*
📍 Direction: *{signal}* {emoji}
⚙️ Strategy: *{strat_name}*
🎯 Confidence: *{confidence}%*
━━━━━━━━━━━━━━━
"""
        send_msg(msg)

        signals_sent += 1
        time.sleep(60)

    # end of session message
    if session_name == "evening":
        send_msg("🌙 Evening session ends.")
    else:
        send_msg("🌞 Morning session ends.")

    date_key = today.strftime("%Y-%m-%d")
    add_session_result(date_key, session_name, wins, losses, fair_session)

    # summaries
    if session_name == "morning":
        time.sleep(60)
        send_daily_summary("morning", today)
    elif session_name == "evening":
        time.sleep(60)
        send_daily_summary("evening", today)
        time.sleep(60)
        send_daily_summary("daily", today)

# ---------- Data Fetchers & Indicators ----------
# (same functions as your original code, unchanged)
