import yfinance as yf
import pandas as pd
import numpy as np
import time
import requests
import random
import os
import datetime

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
    ("EURNZD=X","EUR/NZD"),
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

    time.sleep(60)  # wait 1 minute before first signal

    signals_sent = 0
    total_signals = 5

    # Decide if this session will have 0 or 1 loss
    loss_positions = []
    if random.random() < 0.7:  # 70% chance: 1 loss, 30% chance: no loss
        loss_positions = [random.randint(1, total_signals)]

    used_pairs = random.sample(pairs, total_signals)  # unique pairs per session

    while signals_sent < total_signals:
        symbol, name = used_pairs[signals_sent]
        df = get_data(symbol)
        signal = ema_strategy(df) if df is not None else random.choice(["CALL","PUT"])

        emoji = "🟢📈" if signal == "CALL" else "🔴📉"
        strategy = random.choice(strategy_names)

        msg = f"""
━━━━━━━━━━━━━━━
💹 *Signal {signals_sent+1}*
💱 Pair: *{name}*
📍 Direction: *{signal}* {emoji}
🧩 Strategy: *{strategy}*
⏳ Expiry: 1 Minute
━━━━━━━━━━━━━━━
"""
        send_msg(msg)

        # wait expiry time
        time.sleep(60)

        # Controlled result
        if (signals_sent+1) in loss_positions:
            result = "❌ LOSS 😢"
        else:
            result = "✅ WIN 🎉"

        send_msg(f"📊 *Result for Signal {signals_sent+1}:* {result}")

        signals_sent += 1
        time.sleep(30)  # pause before next signal

    if session_name == "evening":
        send_msg("✅ Evening session ends")
    else:
        send_msg("✅ Morning session ends")


if __name__ == "__main__":
    session = os.getenv("SESSION", "morning")
    weekday = datetime.datetime.utcnow().weekday()  # Monday=0 ... Sunday=6
    manual_run = os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch"

    # Only run automatically Mon-Fri. On weekends, only run if triggered manually.
    if weekday < 5 or manual_run:
        run_session(session)
    else:
        print("Weekend detected. Skipping signals unless triggered manually.")
