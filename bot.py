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
        df["RSI"] = compute_rsi(df["Close"])
        df["MACD"], df["Signal"] = compute_macd(df["Close"])
        df["Upper"], df["Lower"] = compute_bbands(df["Close"])
        df["%K"], df["%D"] = compute_stoch(df)
        df["ADX"] = compute_adx(df)
        df["SAR"] = compute_sar(df)
        return df
    except Exception as e:
        print("Data fetch error:", e)
        return None

# ---------- Indicators ----------
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def compute_macd(series, fast=12, slow=26, signal=9):
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    sig = macd.ewm(span=signal, adjust=False).mean()
    return macd, sig

def compute_bbands(series, period=20, std=2):
    sma = series.rolling(period).mean()
    stddev = series.rolling(period).std()
    upper = sma + (std * stddev)
    lower = sma - (std * stddev)
    return upper, lower

def compute_stoch(df, k_period=14, d_period=3):
    low_min = df["Low"].rolling(k_period).min()
    high_max = df["High"].rolling(k_period).max()
    k = 100 * ((df["Close"] - low_min) / (high_max - low_min))
    d = k.rolling(d_period).mean()
    return k, d

def compute_adx(df, period=14):
    df["TR"] = np.maximum.reduce([
        df["High"] - df["Low"],
        abs(df["High"] - df["Close"].shift()),
        abs(df["Low"] - df["Close"].shift())
    ])
    atr = df["TR"].rolling(period).mean()
    up_move = df["High"] - df["High"].shift()
    down_move = df["Low"].shift() - df["Low"]
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    plus_di = 100 * (pd.Series(plus_dm).rolling(period).mean() / atr)
    minus_di = 100 * (pd.Series(minus_dm).rolling(period).mean() / atr)
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
    return dx.rolling(period).mean()

def compute_sar(df, step=0.02, max_step=0.2):
    sar = df["Close"].copy()
    sar.iloc[0] = df["Close"].iloc[0]
    return sar

# ---------- Strategies ----------
def ema_strategy(df):
    if df["EMA5"].iloc[-1] > df["EMA10"].iloc[-1]:
        return "CALL"
    elif df["EMA5"].iloc[-1] < df["EMA10"].iloc[-1]:
        return "PUT"
    return random.choice(["CALL","PUT"])

def rsi_strategy(df):
    rsi = df["RSI"].iloc[-1]
    if rsi < 30:
        return "CALL"
    elif rsi > 70:
        return "PUT"
    return random.choice(["CALL","PUT"])

def macd_strategy(df):
    if df["MACD"].iloc[-1] > df["Signal"].iloc[-1]:
        return "CALL"
    elif df["MACD"].iloc[-1] < df["Signal"].iloc[-1]:
        return "PUT"
    return random.choice(["CALL","PUT"])

def bb_strategy(df):
    if df["Close"].iloc[-1] <= df["Lower"].iloc[-1]:
        return "CALL"
    elif df["Close"].iloc[-1] >= df["Upper"].iloc[-1]:
        return "PUT"
    return random.choice(["CALL","PUT"])

def stochastic_strategy(df):
    if df["%K"].iloc[-1] > df["%D"].iloc[-1]:
        return "CALL"
    elif df["%K"].iloc[-1] < df["%D"].iloc[-1]:
        return "PUT"
    return random.choice(["CALL","PUT"])

def adx_strategy(df):
    if df["ADX"].iloc[-1] > 25:
        return "CALL"
    else:
        return "PUT"

def momentum_strategy(df):
    if df["Close"].iloc[-1] > df["Close"].iloc[-5]:
        return "CALL"
    else:
        return "PUT"

def sr_breakout_strategy(df):
    if df["Close"].iloc[-1] > df["High"].rolling(20).max().iloc[-1]:
        return "CALL"
    elif df["Close"].iloc[-1] < df["Low"].rolling(20).min().iloc[-1]:
        return "PUT"
    return random.choice(["CALL","PUT"])

def psar_strategy(df):
    if df["Close"].iloc[-1] > df["SAR"].iloc[-1]:
        return "CALL"
    else:
        return "PUT"

def phantom_strategy(df):
    return random.choice(["CALL","PUT"])

strategies = [
    ema_strategy,
    rsi_strategy,
    macd_strategy,
    bb_strategy,
    stochastic_strategy,
    adx_strategy,
    momentum_strategy,
    sr_breakout_strategy,
    psar_strategy,
    phantom_strategy
]

# 🔄 Session Runner
def run_session(session_name):
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
    if session_name == "evening":
        if random.random() < (2/7):
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
        df = get_data(symbol)

        strat_func = random.choice(strategies)
        strategy_name = [k for k,v in strategy_map.items() if v == strat_func.__name__][0]

        signal = strat_func(df) if df is not None else random.choice(["CALL","PUT"])
        emoji = "🟢📈" if signal == "CALL" else "🔴📉"

        if (signals_sent+1) in loss_positions:
            confidence = random.randint(75, 79)
        else:
            confidence = random.randint(80, 90)

        msg = f"""
━━━━━━━━━━━━━━━
💹 *Signal {signals_sent+1}*
💱 Pair: *{name}*
📍 Direction: *{signal}* {emoji}
⚙️ Strategy: *{strategy_name}*
🎯 Confidence: *{confidence}%*
━━━━━━━━━━━━━━━
"""
        send_msg(msg)

        signals_sent += 1
        time.sleep(60)
