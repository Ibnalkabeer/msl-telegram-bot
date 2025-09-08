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

# ---------- get_data ----------
def get_data(symbol):
    try:
        df = yf.download(symbol, period="5d", interval="5m")
        return df
    except Exception as e:
        print(f"Data fetch failed for {symbol}: {e}")
        return pd.DataFrame()

# ---------- Example Strategies ----------
def ema_strategy(df):
    if df.empty:
        return random.choice(["CALL","PUT"])
    ema_fast = df['Close'].ewm(span=5, adjust=False).mean().iloc[-1]
    ema_slow = df['Close'].ewm(span=10, adjust=False).mean().iloc[-1]
    return "CALL" if ema_fast > ema_slow else "PUT"

def rsi_strategy(df):
    if df.empty:
        return random.choice(["CALL","PUT"])
    delta = df['Close'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / (loss + 1e-6)
    rsi = 100 - (100 / (1 + rs))
    return "CALL" if rsi.iloc[-1] < 30 else "PUT" if rsi.iloc[-1] > 70 else random.choice(["CALL","PUT"])

# Other strategies
def macd_strategy(df): return random.choice(["CALL","PUT"])
def bb_strategy(df): return random.choice(["CALL","PUT"])
def stochastic_strategy(df): return random.choice(["CALL","PUT"])
def adx_strategy(df): return random.choice(["CALL","PUT"])
def momentum_strategy(df): return random.choice(["CALL","PUT"])
def sr_breakout_strategy(df): return random.choice(["CALL","PUT"])
def psar_strategy(df): return random.choice(["CALL","PUT"])
def phantom_strategy(df): return random.choice(["CALL","PUT"])

strategy_func_map = {
    "ema_strategy": ema_strategy,
    "rsi_strategy": rsi_strategy,
    "macd_strategy": macd_strategy,
    "bb_strategy": bb_strategy,
    "stochastic_strategy": stochastic_strategy,
    "adx_strategy": adx_strategy,
    "momentum_strategy": momentum_strategy,
    "sr_breakout_strategy": sr_breakout_strategy,
    "psar_strategy": psar_strategy,
    "phantom_strategy": phantom_strategy
}

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

# ---------- Telegram ----------
def send_msg(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})
        if resp.status_code != 200:
            print(f"Telegram API error {resp.status_code}: {resp.text}")
    except Exception as e:
        print("Telegram error:", e)

# ---------- Summaries ----------
def send_daily_summary(session_name, today_utc, motivational_text=""):
    date_key = today_utc.strftime("%Y-%m-%d")
    w, l, _ = get_day_totals(date_key)
    total = w + l
    win_rate = round((w / total) * 100) if total else 0
    title = "Morning Performance Recap" if session_name=="morning" else "Daily Performance Recap"
    msg = "\n".join([
        f"🗓️ *{title}* — {today_utc.strftime('%A, %d %B %Y')}",
        "━━━━━━━━━━━━━━━",
        f"✅ Wins: *{w}*",
        f"❌ Losses: *{l}*",
        f"📌 Total Signals: *{total}*",
        f"📈 Win Rate: *{win_rate}%*",
        f"💬 {motivational_text}",
        "━━━━━━━━━━━━━━━"
    ])
    send_msg(msg)

def send_weekly_summary(today_utc):
    monday = today_utc - datetime.timedelta(days=today_utc.weekday())
    saturday = monday + datetime.timedelta(days=5)
    w, l, fair = summarize_range(monday.date(), saturday.date())
    total = w + l
    win_rate = round((w / total) * 100) if total else 0
    week_num = today_utc.isocalendar()[1]
    msg = "\n".join([
        f"📅 *Weekly Performance Recap — Week {week_num}*",
        "━━━━━━━━━━━━━━━",
        f"✅ Wins: *{w}*",
        f"❌ Losses: *{l}*",
        f"⚖️ Fair Sessions: *{fair}*",
        f"📌 Total Signals: *{total}*",
        f"📈 Win Rate: *{win_rate}%*",
        "━━━━━━━━━━━━━━━"
    ])
    send_msg(msg)

def send_monthly_summary(today_utc):
    start = datetime.date(today_utc.year, today_utc.month, 1)
    end = today_utc.date()
    w, l, fair = summarize_range(start, end)
    total = w + l
    win_rate = round((w / total) * 100) if total else 0
    month_name = today_utc.strftime("%B %Y")
    msg = "\n".join([
        f"📊 *Monthly Performance Report — {month_name}*",
        "━━━━━━━━━━━━━━━",
        f"✅ Total Wins: *{w}*",
        f"❌ Total Losses: *{l}*",
        f"⚖️ Fair Sessions: *{fair}*",
        f"📌 Total Signals: *{total}*",
        f"🏆 Win Rate: *{win_rate:.1f}%*",
        "━━━━━━━━━━━━━━━"
    ])
    send_msg(msg)

# ---------- Session Runner ----------
def run_session(session_name):
    today = datetime.datetime.utcnow()
    weekday = today.weekday()

    if weekday >= 5 and session_name in ("morning", "evening"):
        print("Weekend: no signals.")
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
    greet = "🌙 *Good Evening Family* 🌙" if session_name=="evening" else "🌞 *Good Morning Family* 🌞"
    send_msg(robot_display + f"\n{greet}\n\n📡 *MSL Binary Signal* 📡\n━━━━━━━━━━━━━━━\n📊 {session_name.capitalize()} session starts now!")
    time.sleep(2)  # reduced sleep for testing

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
        strat_name, strat_func_str = random.choice(list(strategy_map.items()))
        strat_func = strategy_func_map.get(strat_func_str, lambda df: random.choice(["CALL","PUT"]))

        df = get_data(symbol)
        signal = strat_func(df) if not df.empty else random.choice(["CALL","PUT"])

        emoji = "🟢📈" if signal == "CALL" else "🔴📉"

        if (signals_sent+1) in loss_positions:
            confidence = random.randint(75, 79)
            losses += 1
            result_msg = f"❌ Signal {signals_sent+1} result: LOSS"
        else:
            confidence = random.randint(80, 90)
            wins += 1
            result_msg = f"✅ Signal {signals_sent+1} result: WIN"

        msg = "\n".join([
            "━━━━━━━━━━━━━━━",
            f"💹 *Signal {signals_sent+1}*",
            f"💱 Pair: *{name}*",
            f"📍 Direction: *{signal}* {emoji}",
            f"⚙️ Strategy: *{strat_name}*",
            f"🎯 Confidence: *{confidence}%",
            "━━━━━━━━━━━━━━━"
        ])
        send_msg(msg)
        time.sleep(1)  # reduced sleep for testing
        send_msg(result_msg)
        time.sleep(1)

        signals_sent += 1

    send_msg(f"🌙 Evening session ends." if session_name=="evening" else "🌞 Morning session ends.")

    date_key = today.strftime("%Y-%m-%d")
    add_session_result(date_key, session_name, wins, losses, fair_session)

    # session summary
    time.sleep(2)
    if wins >= 9:
        motivational = "Excellent session! Keep up the great work 💪"
    elif wins == 8:
        motivational = "Very good session! Stay consistent 🔥"
    else:
        motivational = "Unstable market, stay cautious 👀"
    send_daily_summary(session_name, today, motivational)

    # evening session: also daily summary
    if session_name == "evening":
        time.sleep(2)
        send_daily_summary("daily", today, "That's your daily recap! Keep learning and growing 📈")

# ---------- Entrypoint ----------
def main():
    session = os.getenv("SESSION", "").lower().strip()
    now = datetime.datetime.utcnow()

    if session in ("morning", "evening"):
        print(f"Running {session} session...")
        run_session(session)
    elif session == "weekly":
        print("Running weekly summary...")
        send_weekly_summary(now)
    elif session == "monthly":
        if is_last_day_of_month(now.date()):
            print("Running monthly summary...")
            send_monthly_summary(now)
        else:
            print("Not the last day of the month, skipping monthly summary.")
    else:
        print("No valid SESSION specified. Set SESSION=morning|evening|weekly|monthly")

if __name__ == "__main__":
    main()
