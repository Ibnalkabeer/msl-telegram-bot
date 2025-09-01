import os
import time
import requests
import yfinance as yf
import pandas as pd
import math

# -----------------------------
# CONFIG
# -----------------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Safety: require secrets
if not BOT_TOKEN or not CHAT_ID:
    print("ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set as repo secrets")
    raise SystemExit(1)

# Behavior / timing (tweak these if you want)
EXPIRY_SECONDS = 60            # expiry (1 minute)
AFTER_RESULT_DELAY = 60        # wait after showing result before next signal
START_DELAY_SECONDS = 30       # wait after "session starts" before first signal
SIGNALS_PER_SESSION = 5
MAX_ATTEMPTS = 50              # stop if we can't find enough pairs (prevents infinite loop)
YF_PERIOD = "1d"               # how much history to request
YF_INTERVAL = "1m"             # fast intraday data

# -----------------------------
# Pairs - mostly forex + gold (avoid unreliable intraday tickers)
# -----------------------------
PAIRS = [
    ("EURUSD=X","EUR/USD"), ("GBPUSD=X","GBP/USD"), ("USDJPY=X","USD/JPY"),
    ("AUDUSD=X","AUD/USD"), ("USDCHF=X","USD/CHF"), ("USDCAD=X","USD/CAD"),
    ("NZDUSD=X","NZD/USD"), ("EURJPY=X","EUR/JPY"), ("GBPJPY=X","GBP/JPY"),
    ("AUDJPY=X","AUD/JPY"), ("EURGBP=X","EUR/GBP"), ("EURAUD=X","EUR/AUD"),
    ("CADJPY=X","CAD/JPY"), ("CHFJPY=X","CHF/JPY"), ("NZDJPY=X","NZD/JPY"),
    ("GC=F","Gold")
]

# -----------------------------
# Telegram helper (HTML)
# -----------------------------
def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code != 200:
            print("Telegram send failed:", r.status_code, r.text)
    except Exception as e:
        print("Telegram error:", e)

# -----------------------------
# Indicators
# -----------------------------
def safe_div(a, b):
    try:
        return a / b
    except Exception:
        return float("nan")

def rsi(df, period=14):
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = safe_div(gain, loss)
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
    denom = (high_max - low_min).replace(0, float("nan"))
    df["stoch_k"] = 100 * ((df["Close"] - low_min) / denom)
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
    sumTR = tr.rolling(length).sum().replace(0, float("nan"))
    sumVP = vp.rolling(length).sum()
    sumVM = vm.rolling(length).sum()
    df["vi_plus"] = safe_div(sumVP, sumTR).fillna(1.0)
    df["vi_minus"] = safe_div(sumVM, sumTR).fillna(1.0)
    return df

def ema(df):
    df["ema20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["Close"].ewm(span=50, adjust=False).mean()
    return df

def bollinger(df, period=20):
    df["sma"] = df["Close"].rolling(period).mean()
    df["stddev"] = df["Close"].rolling(period).std()
    df["upper_bb"] = df["sma"] + (df["stddev"] * 2)
    df["lower_bb"] = df["sma"] - (df["stddev"] * 2)
    return df

# -----------------------------
# Strategy rotation
# -----------------------------
STRATEGIES = ["RSI", "MACD", "STOCHASTIC", "VORTEX", "EMA", "BOLLINGER"]
strategy_index = 0

def generate_signal(df):
    """Use current strategy (rotating) and always return a direction + reasons."""
    global strategy_index
    latest = df.iloc[-1]
    strat = STRATEGIES[strategy_index % len(STRATEGIES)]
    direction = None
    reasons = []

    # RSS/logic with safe getters
    r = float(latest.get("rsi", float("nan"))) if not pd.isna(latest.get("rsi", None)) else math.nan
    mac = float(latest.get("macd", math.nan))
    mac_sig = float(latest.get("signal", math.nan))
    sk = float(latest.get("stoch_k", math.nan))
    sd = float(latest.get("stoch_d", math.nan))
    vplus = float(latest.get("vi_plus", math.nan))
    vminus = float(latest.get("vi_minus", math.nan))
    ema20 = float(latest.get("ema20", math.nan))
    ema50 = float(latest.get("ema50", math.nan))
    close = float(latest.get("Close", math.nan))
    lower_bb = float(latest.get("lower_bb", math.nan)) if "lower_bb" in latest else math.nan
    upper_bb = float(latest.get("upper_bb", math.nan)) if "upper_bb" in latest else math.nan

    if strat == "RSI":
        if r < 40:
            direction = "CALL 📈"; reasons = ["RSI oversold (<40)"]
        elif r > 60:
            direction = "PUT 📉"; reasons = ["RSI overbought (>60)"]
        else:
            direction = "CALL 📈"; reasons = ["RSI neutral → slight CALL bias"]

    elif strat == "MACD":
        if mac > mac_sig:
            direction = "CALL 📈"; reasons = ["MACD > signal"]
        else:
            direction = "PUT 📉"; reasons = ["MACD < signal"]

    elif strat == "STOCHASTIC":
        if sk < 30 and sd < 30:
            direction = "CALL 📈"; reasons = ["Stochastic oversold (<30)"]
        elif sk > 70 and sd > 70:
            direction = "PUT 📉"; reasons = ["Stochastic overbought (>70)"]
        else:
            direction = "CALL 📈"; reasons = ["Stochastic neutral → CALL bias"]

    elif strat == "VORTEX":
        if vplus > vminus:
            direction = "CALL 📈"; reasons = ["Vortex +VI > -VI"]
        else:
            direction = "PUT 📉"; reasons = ["Vortex +VI < -VI"]

    elif strat == "EMA":
        if ema20 > ema50:
            direction = "CALL 📈"; reasons = ["EMA20 > EMA50 (bullish)"]
        else:
            direction = "PUT 📉"; reasons = ["EMA20 < EMA50 (bearish)"]

    elif strat == "BOLLINGER":
        if not math.isnan(lower_bb) and close <= lower_bb:
            direction = "CALL 📈"; reasons = ["Price at/below lower Bollinger band"]
        elif not math.isnan(upper_bb) and close >= upper_bb:
            direction = "PUT 📉"; reasons = ["Price at/above upper Bollinger band"]
        else:
            direction = "CALL 📈"; reasons = ["Price mid-BB → CALL bias"]

    strategy_index += 1
    return {"direction": direction, "strategy": strat, "reasons": reasons}

# -----------------------------
# Helper: get latest price (1m)
# -----------------------------
def latest_price(ticker):
    try:
        df = yf.download(ticker, period="1d", interval="1m", progress=False)
        if df is None or df.empty:
            return None
        return float(df["Close"].iloc[-1])
    except Exception as e:
        print("latest_price error:", e)
        return None

# -----------------------------
# Pretty format for signal
# -----------------------------
def format_signal_card(n, pair_name, sig, expiry_mins):
    reasons = ", ".join(sig.get("reasons", [])) if sig else ""
    return (
        f"<pre>"
        f"┏━━━━━━━━ SIGNAL ━━━━━━━━\n"
        f"┃ Signal: {n}/{SIGNALS_PER_SESSION}\n"
        f"┃ Pair:   {pair_name}\n"
        f"┃ Dir:    {sig.get('direction')}\n"
        f"┃ Expiry: {expiry_mins}m\n"
        f"┃ Strat:  {sig.get('strategy')} \n"
        f"┃ Note:   {reasons}\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━"
        f"</pre>"
    )

# -----------------------------
# Main session runner
# -----------------------------
def run_session(session_name="Morning"):
    # Header
    send_telegram_message(f"☀️ <b>Good {session_name} Family</b>\n\n📡 <b>MSL Binary Signal</b>\n<b>{session_name} session starts</b>")
    time.sleep(START_DELAY_SECONDS)

    signal_count = 0
    pair_index = 0
    attempts = 0

    while signal_count < SIGNALS_PER_SESSION and attempts < MAX_ATTEMPTS:
        attempts += 1
        symbol, nice = PAIRS[pair_index % len(PAIRS)]
        pair_index += 1

        try:
            # fetch 1m intraday data for the last day
            df = yf.download(symbol, period=YF_PERIOD, interval=YF_INTERVAL, progress=False)
            if df is None or df.empty or len(df) < 20:
                print(f"[WARN] No usable data for {nice} ({symbol}), len={0 if df is None else len(df)}")
                continue

            # compute indicators (will add columns, may produce NaNs at top)
            df = rsi(df)
            df = macd(df)
            df = stochastic(df)
            df = vortex(df)
            df = ema(df)
            df = bollinger(df)

            # ensure latest row has required columns
            if df.empty or len(df) < 20:
                print(f"[WARN] After indicators, no data for {nice}")
                continue

            sig = generate_signal(df)

            # capture entry price (latest)
            entry = latest_price(symbol)
            entry_text = f"{entry:.5f}" if entry is not None and not math.isnan(entry) else "NO_PRICE"

            signal_count += 1
            # send nicely formatted card
            card = format_signal_card(signal_count, nice, sig, expiry_mins=1)
            send_telegram_message(card)
            # send a compact body with entry price
            send_telegram_message(f"<b>Entry:</b> {entry_text}   ⏱️ Expiry: 1m   <b>Strategy:</b> {sig.get('strategy')}")

            # wait expiry and then compute result
            time.sleep(EXPIRY_SECONDS + 1)  # small buffer
            exit_price = latest_price(symbol)
            if entry is None or exit_price is None:
                send_telegram_message("⚪ <b>Result:</b> NO_PRICE (couldn't fetch entry or exit price)")
            else:
                win = None
                dir_text = sig.get("direction", "")
                # check CALL/PUT
                if "CALL" in dir_text:
                    win = exit_price > entry
                elif "PUT" in dir_text:
                    win = exit_price < entry
                else:
                    win = False

                if win:
                    send_telegram_message("✅ <b>Win</b>\nCongratulation 🎊")
                else:
                    send_telegram_message("❌ <b>Lose</b>\nKeep studying and reviewing trades.")

            # pause after result before next signal
            time.sleep(AFTER_RESULT_DELAY)

        except Exception as e:
            print(f"[ERROR] fetching/processing {nice}: {e}")
            # continue trying other pairs

    # end session
    send_telegram_message(f"✅ <b>{session_name} session ends</b>")

# -----------------------------
# Entrypoint
# -----------------------------
if __name__ == "__main__":
    # Default uses "Morning" — your workflows set SESSION env if you want "Evening"
    sess = os.environ.get("SESSION", "Morning")
    run_session(session_name=sess)
