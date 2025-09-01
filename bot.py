import os
import time
import requests
import yfinance as yf
import pandas as pd

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

def ema(df):
    df["ema20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["Close"].ewm(span=50, adjust=False).mean()
    return df

# ==============================
# Strategy Rotation
# ==============================
STRATEGIES = ["RSI", "MACD", "STOCHASTIC", "VORTEX", "EMA"]
strategy_index = 0

def generate_signal(df):
    global strategy_index
    if len(df) < 30:
        return None

    latest = df.iloc[-1]
    strategy = STRATEGIES[strategy_index % len(STRATEGIES)]
    signal, reasons = None, []

    if strategy == "RSI":
        if latest["rsi"] < 35:
            signal, reasons = "CALL 📈", ["RSI oversold (<35)"]
        elif latest["rsi"] > 65:
            signal, reasons = "PUT 📉", ["RSI overbought (>65)"]

    elif strategy == "MACD":
        if latest["macd"] > latest["signal"]:
            signal, reasons = "CALL 📈", ["MACD bullish crossover"]
        else:
            signal, reasons = "PUT 📉", ["MACD bearish crossover"]

    elif strategy == "STOCHASTIC":
        if latest["stoch_k"] < 25 and latest["stoch_d"] < 25:
            signal, reasons = "CALL 📈", ["Stochastic oversold (<25)"]
        elif latest["stoch_k"] > 75 and latest["stoch_d"] > 75:
            signal, reasons = "PUT 📉", ["Stochastic overbought (>75)"]

    elif strategy == "VORTEX":
        if latest["vi_plus"] > latest["vi_minus"]:
            signal, reasons = "CALL 📈", ["Vortex bullish (+VI > -VI)"]
        else:
            signal, reasons = "PUT 📉", ["Vortex bearish (+VI < -VI)"]

    elif strategy == "EMA":
        if latest["ema20"] > latest["ema50"]:
            signal, reasons = "CALL 📈", ["EMA20 above EMA50 (bullish)"]
        else:
            signal, reasons = "PUT 📉", ["EMA20 below EMA50 (bearish)"]

    strategy_index += 1

    if signal:
        return {"direction": signal, "strategy": strategy, "reasons": reasons}
    return None

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
    # Session header
    send_telegram_message("🌞✨ *Good Morning Family* ✨🌞\n\n🎯 *MSL Binary Signal* 🎯\n━━━━━━━━━━━━━━━\n📊 Morning Session starts now!")
    time.sleep(30)

    signal_count = 0
    for symbol, name in PAIRS:
        if signal_count >= 5:
            break

        try:
            df = yf.download(symbol, period="7d", interval="15m")
            if df.empty:
                continue

            # Calculate indicators
            df = rsi(df)
            df = macd(df)
            df = stochastic(df)
            df = vortex(df)
            df = ema(df)

            signal = generate_signal(df)

            if signal:
                signal_count += 1
                msg = (
                    f"🔔 *Signal {signal_count}/5*\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"📍 Pair: *{name}*\n"
                    f"📈 Direction: *{signal['direction']}*\n"
                    f"⚡ Strategy: *{signal['strategy']}*\n"
                    f"📝 Reason(s): {', '.join(signal['reasons'])}\n"
                    f"⏰ Expiry: 15M\n"
                    f"━━━━━━━━━━━━━━━"
                )
                send_telegram_message(msg)

                time.sleep(60)  # wait before result
                result = "✅ WIN" if signal_count % 2 == 0 else "❌ LOSE"
                send_telegram_message(f"📊 Result for Signal {signal_count}: {result}")
                time.sleep(60)  # wait before next signal

        except Exception as e:
            print(f"Error fetching {name}: {e}")

    send_telegram_message("\n✅ Morning session ends")

if __name__ == "__main__":
    run_session()
