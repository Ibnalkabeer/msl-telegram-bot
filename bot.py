import os
import time
import requests
import yfinance as yf
import pandas as pd
import numpy as np

# ==============================
# Telegram Setup
# ==============================
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error sending message: {e}")

# ==============================
# Indicators
# ==============================
def rsi(df, period=14):
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))
    return df

def macd(df):
    df["ema12"] = df["Close"].ewm(span=12, adjust=False).mean()
    df["ema26"] = df["Close"].ewm(span=26, adjust=False).mean()
    df["macd"] = df["ema12"] - df["ema26"]
    df["signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    return df

def stochastic(df, k=14, d=3):
    low_min = df["Low"].rolling(k).min()
    high_max = df["High"].rolling(k).max()
    df["stoch_k"] = 100 * ((df["Close"] - low_min) / (high_max - low_min))
    df["stoch_d"] = df["stoch_k"].rolling(d).mean()
    return df

def vortex(df, length=14):
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    prev_low = low.shift(1)
    prev_high = high.shift(1)

    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    vp = (high - prev_low).abs()
    vm = (low - prev_high).abs()

    sumTR = tr.rolling(length).sum()
    sumVP = vp.rolling(length).sum()
    sumVM = vm.rolling(length).sum()

    df["vi_plus"] = (sumVP / sumTR).fillna(1.0)
    df["vi_minus"] = (sumVM / sumTR).fillna(1.0)
    return df

# ==============================
# Strategy
# ==============================
def generate_signal(df):
    if len(df) < 30:
        return None

    latest = df.iloc[-1]

    signals = []

    # RSI
    if latest["rsi"] < 30:
        signals.append("CALL 📈 (RSI oversold)")
    elif latest["rsi"] > 70:
        signals.append("PUT 📉 (RSI overbought)")

    # MACD
    if latest["macd"] > latest["signal"]:
        signals.append("CALL 📈 (MACD bullish)")
    elif latest["macd"] < latest["signal"]:
        signals.append("PUT 📉 (MACD bearish)")

    # Stochastic
    if latest["stoch_k"] < 20 and latest["stoch_d"] < 20:
        signals.append("CALL 📈 (Stochastic oversold)")
    elif latest["stoch_k"] > 80 and latest["stoch_d"] > 80:
        signals.append("PUT 📉 (Stochastic overbought)")

    # Vortex
    if latest["vi_plus"] > latest["vi_minus"]:
        signals.append("CALL 📈 (Vortex bullish)")
    elif latest["vi_plus"] < latest["vi_minus"]:
        signals.append("PUT 📉 (Vortex bearish)")

    if not signals:
        return None

    # Majority vote system
    call_votes = sum("CALL" in s for s in signals)
    put_votes = sum("PUT" in s for s in signals)

    if call_votes > put_votes:
        direction = "CALL 📈"
    elif put_votes > call_votes:
        direction = "PUT 📉"
    else:
        return None

    return {
        "direction": direction,
        "reasons": signals
    }

# ==============================
# Assets
# ==============================
PAIRS = [
    ("EURUSD=X","EUR/USD"), ("GBPUSD=X","GBP/USD"), ("USDJPY=X","USD/JPY"),
    ("AUDUSD=X","AUD/USD"), ("USDCHF=X","USD/CHF"), ("USDCAD=X","USD/CAD"),
    ("NZDUSD=X","NZD/USD"), ("EURJPY=X","EUR/JPY"), ("GBPJPY=X","GBP/JPY"),
    ("AUDJPY=X","AUD/JPY"), ("EURGBP=X","EUR/GBP"), ("EURAUD=X","EUR/AUD"),
    ("GC=F","Gold"), ("SI=F","Silver"),
    ("^GSPC","S&P 500"), ("^NDX","NASDAQ"),
]

# ==============================
# Main Execution
# ==============================
def run_session():
    send_telegram_message("☀️ *Good Morning Family*\n\n`Morning session starts`\n\n📡 *MSL Binary Signal*")
    time.sleep(30)

    found = False
    for symbol, name in PAIRS:
        try:
            df = yf.download(symbol, period="7d", interval="15m")
            if df.empty:
                continue

            df = rsi(df)
            df = macd(df)
            df = stochastic(df)
            df = vortex(df)

            signal = generate_signal(df)

            if signal:
                found = True
                msg = (
                    f"\n━━━━━━━━━━━━━━━\n"
                    f"**PAIR:** {name}\n"
                    f"**DIRECTION:** {signal['direction']}\n"
                    f"**EXPIRY:** 15M\n"
                    f"**STRATEGY REASONS:**\n" + "\n".join([f"- {s}" for s in signal["reasons"]]) +
                    f"\n━━━━━━━━━━━━━━━"
                )
                send_telegram_message(msg)
                time.sleep(30)

        except Exception as e:
            print(f"Error fetching {name}: {e}")

    if not found:
        send_telegram_message("⚠️ No reliable signals found this session.")

    send_telegram_message("\n✅ Morning session ends")

if __name__ == "__main__":
    run_session()
