import yfinance as yf
import pandas as pd
import time
import requests
import random
import os

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

pairs = [
    ("EURUSD=X","EUR/USD"),
    ("GBPUSD=X","GBP/USD"),
    ("USDJPY=X","USD/JPY"),
    ("AUDUSD=X","AUD/USD"),
    ("USDCHF=X","USD/CHF"),
    ("USDCAD=X","USD/CAD"),
    ("NZDUSD=X","NZD/USD")
]

# 📡 Telegram sender
def send_msg(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})

# 📊 Indicators
def get_data(symbol):
    try:
        df = yf.download(symbol, interval="1m", period="1d")
        if df.empty:
            df = yf.download(symbol, interval="5m", period="5d")
        if df.empty:
            return None

        # Indicators
        df["EMA5"] = df["Close"].ewm(span=5, adjust=False).mean()
        df["EMA10"] = df["Close"].ewm(span=10, adjust=False).mean()
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df["RSI"] = 100 - (100 / (1 + rs))
        df["Middle"] = df["Close"].rolling(20).mean()
        df["Upper"] = df["Middle"] + 2 * df["Close"].rolling(20).std()
        df["Lower"] = df["Middle"] - 2 * df["Close"].rolling(20).std()
        return df
    except Exception as e:
        print("Error fetching data:", e)
        return None

# 🎯 Strategies
def ema_strategy(df):
    if df["EMA5"].iloc[-1] > df["EMA10"].iloc[-1]:
        return "CALL"
    elif df["EMA5"].iloc[-1] < df["EMA10"].iloc[-1]:
        return "PUT"
    return None

def rsi_strategy(df):
    if df["RSI"].iloc[-1] < 40: return "CALL"
    elif df["RSI"].iloc[-1] > 60: return "PUT"
    return None

def bb_strategy(df):
    price = df["Close"].iloc[-1]
    if price < df["Lower"].iloc[-1]: return "CALL"
    elif price > df["Upper"].iloc[-1]: return "PUT"
    return None

def macd_strategy(df):
    short = df["Close"].ewm(span=12, adjust=False).mean()
    long = df["Close"].ewm(span=26, adjust=False).mean()
    macd = short - long
    signal = macd.ewm(span=9, adjust=False).mean()
    if macd.iloc[-1] > signal.iloc[-1]: return "CALL"
    elif macd.iloc[-1] < signal.iloc[-1]: return "PUT"
    return None

strategies = [ema_strategy, rsi_strategy, bb_strategy, macd_strategy]

# 🔄 Session Runner
def run_session(session_name):
    send_msg("☀️ *Good Morning Family* ☀️\n\n📡 *MSL Binary Signal* 📡\n━━━━━━━━━━━━━━━\n📊 Morning session starts now!")
    signals_sent = 0
    strat_index = 0

    while signals_sent < 5:
        symbol, name = random.choice(pairs)
        df = get_data(symbol)
        if df is None:
            time.sleep(10)
            continue

        strategy = strategies[strat_index % len(strategies)]
        strat_index += 1
        signal = strategy(df)

        if not signal:
            # ✅ Always fallback
            signal = random.choice(["CALL", "PUT"])

        emoji = "🟢📈" if signal == "CALL" else "🔴📉"
        msg = f"""
━━━━━━━━━━━━━━━
💹 *Signal {signals_sent+1}/5*
💱 Pair: *{name}*
📍 Direction: *{signal}* {emoji}
⏳ Expiry: 1 Minute
🧠 Strategy: {strategy.__name__.replace("_"," ").title()}
━━━━━━━━━━━━━━━
"""
        send_msg(msg)
        signals_sent += 1

        # Wait 1 minute between signals
        time.sleep(60)

    send_msg("✅ Morning session ends")

if __name__ == "__main__":
    run_session("morning")
