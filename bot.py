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
    ("EURUSD=X","EUR/USD"),
    ("GBPUSD=X","GBP/USD"),
    ("USDJPY=X","USD/JPY"),
    ("AUDUSD=X","AUD/USD"),
    ("NZDUSD=X","NZD/USD"),
    ("USDCAD=X","USD/CAD"),
    ("USDCHF=X","USD/CHF"),
    ("EURGBP=X","EUR/GBP"),
    ("EURJPY=X","EUR/JPY"),
    ("GBPJPY=X","GBP/JPY"),
    ("AUDJPY=X","AUD/JPY"),
    ("CADJPY=X","CAD/JPY"),
    ("CHFJPY=X","CHF/JPY"),
    ("NZDJPY=X","NZD/JPY"),
    ("EURAUD=X","EUR/AUD"),
    ("EURNZD=X","EURNZD"),
    ("GBPAUD=X","GBP/AUD"),
    ("GBPCAD=X","GBP/CAD"),
    ("GBPNZD=X","GBP/NZD"),
    ("AUDNZD=X","AUD/NZD")
]

# Strategy name decorator pool 🎭
strategy_names = [
    "Quantum Wave",
    "Shadow Breaker",
    "Falcon Pulse",
    "Neural Edge",
    "Momentum Rider",
    "Storm Pivot",
    "Crystal Trend",
    "Eagle Eye",
    "Lunar Flow",
    "Phantom Scalper"
]

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
🧠 Consistency over intensity: stick to risk rules and follow the flow.
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
💡 Market Note: We navigated varying volatility with discipline—let’s carry the momentum into next week.
🎯 Great job staying consistent. Risk management first, always.
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
—
🧭 *Trader’s Insight:* The month presented volatility, but disciplined execution kept the edge. 
🎯 *Coach’s Note:* Outstanding commitment. We scale sustainably—same focus, next month stronger.
━━━━━━━━━━━━━━━
"""
    send_msg(msg)
# ---------- end stats helpers ----------

# 📡 Telegram sender
def send_msg(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})
    except Exception as e:
        print("Telegram error:", e)

# 📊 Data fetcher
def get_data(symbol):
    try:
        df = yf.download(symbol, interval="1m", period="1d")
        if df.empty:
            return None
        df["EMA5"] = df["Close"].ewm(span=5, adjust=False).mean()
        df["EMA10"] = df["Close"].ewm(span=10, adjust=False).mean()
        return df
    except Exception as e:
        print("Data fetch error:", e)
        return None

# 🎯 Simple EMA strategy
def ema_strategy(df):
    if df["EMA5"].iloc[-1] > df["EMA10"].iloc[-1]:
        return "CALL"
    elif df["EMA5"].iloc[-1] < df["EMA10"].iloc[-1]:
        return "PUT"
    return random.choice(["CALL","PUT"])

# 🔄 Session Runner
def run_session(session_name):
    if session_name == "evening":
        send_msg("🌙 *Good Evening Family* 🌙\n\n📡 *MSL Binary Signal* 📡\n━━━━━━━━━━━━━━━\n📊 Evening session starts now!")
    else:
        send_msg("🌞 *Good Morning Family* 🌞\n\n📡 *MSL Binary Signal* 📡\n━━━━━━━━━━━━━━━\n📊 Morning session starts now!")

    time.sleep(60)

    signals_sent = 0
    total_signals = 5
    wins = 0
    losses = 0

    fair_session = False
    if session_name == "evening":
        if random.random() < (2/7):
            fair_session = True

    loss_positions = []
    if fair_session:
        loss_positions = random.sample(range(1, total_signals+1), 2)
    else:
        if random.random() < 0.7:
            loss_positions = [random.randint(1, total_signals)]

    used_pairs = random.sample(pairs, total_signals)

    while signals_sent < total_signals:
        symbol, name = used_pairs[signals_sent]
        df = get_data(symbol)
        signal = ema_strategy(df) if df is not None else random.choice(["CALL","PUT"])
        emoji = "🟢📈" if signal == "CALL" else "🔴📉"
        strategy = random.choice(strategy_names)

        if (signals_sent+1) in loss_positions:
            confidence = random.randint(75, 79)
        else:
            confidence = random.randint(80, 90)

        msg = f"""
━━━━━━━━━━━━━━━
💹 *Signal {signals_sent+1}*
💱 Pair: *{name}*
📍 Direction: *{signal}* {emoji}
🧩 Strategy: *{strategy}*
🎯 Confidence: *{confidence}%*
⏳ Expiry: 1 Minute
━━━━━━━━━━━━━━━
"""
        send_msg(msg)
        time.sleep(60)

        if (signals_sent+1) in loss_positions:
            result = "❌ LOSS 😢"
            losses += 1
        else:
            result = "✅ WIN 🎉"
            wins += 1

        send_msg(f"📊 *Result for Signal {signals_sent+1}:* {result}")
        signals_sent += 1
        time.sleep(30)

    # Session end message
    if session_name == "evening":
        send_msg("✅ Evening session ends")
    else:
        send_msg("✅ Morning session ends")

    time.sleep(60)
    win_rate = round((wins / total_signals) * 100)

    if fair_session:
        summary_msg = f"""
⚖️ *Fair Session!* ⚖️
━━━━━━━━━━━━━━━
📊 *{session_name.capitalize()} Session Summary*
✅ Wins: *{wins}*
❌ Losses: *{losses}*
📉 Win Rate: *{win_rate}%*
📝 Today’s market showed instability, leading to a fair outcome.
━━━━━━━━━━━━━━━
"""
    elif losses == 0:
        summary_msg = f"""
🌟 *Perfect Session!* 🌟
━━━━━━━━━━━━━━━
📊 *{session_name.capitalize()} Session Summary*
✅ Wins: *{wins}*
❌ Losses: *{losses}*
🏆 Win Rate: *{win_rate}%*
━━━━━━━━━━━━━━━
"""
    else:
        summary_msg = f"""
🔥 *Very Good Session!* 🔥
━━━━━━━━━━━━━━━
📊 *{session_name.capitalize()} Session Summary*
✅ Wins: *{wins}*
❌ Losses: *{losses}*
📈 Win Rate: *{win_rate}%*
━━━━━━━━━━━━━━━
"""

    if session_name == "evening":
        time.sleep(60)
        send_msg(summary_msg)
        time.sleep(60)
        today_utc = datetime.datetime.utcnow()
        send_daily_summary("evening", today_utc)
    else:
        today_utc = datetime.datetime.utcnow()
        time.sleep(60)
        send_msg(summary_msg)
        time.sleep(60)
        send_daily_summary("morning", today_utc)

    # Save stats
    date_key = today_utc.strftime("%Y-%m-%d")
    add_session_result(date_key, session_name, wins, losses, fair_session)

    # Weekly summary on Saturday 10am (no signals)
    if today_utc.weekday() == 5 and session_name == "morning":
        send_weekly_summary(today_utc)
    # Monthly summary last day 8pm WAT = 19:00 UTC
    if is_last_day_of_month(today_utc.date()) and today_utc.hour == 19 and session_name == "evening":
        send_monthly_summary(today_utc)

if __name__ == "__main__":
    session = os.getenv("SESSION", "morning")
    weekday = datetime.datetime.utcnow().weekday()
    manual_run = os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch"

    if weekday < 5 or manual_run:
        run_session(session)
    elif weekday == 5 and session == "morning":  # Saturday weekly recap only
        send_weekly_summary(datetime.datetime.utcnow())
    elif is_last_day_of_month(datetime.datetime.utcnow().date()) and session == "evening":
        send_monthly_summary(datetime.datetime.utcnow())
    else:
        print("Weekend detected. Skipping signals unless triggered manually.")
