# signal_bot.py
import os, time, sys, requests
import pandas as pd
import numpy as np
import yfinance as yf

# ---------------- CONFIG (read from env / GitHub secrets) ----------------
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SESSION = os.environ.get("SESSION", "morning")  # "morning" or "evening"

if not TOKEN or not CHAT_ID:
    print("ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables are required.")
    sys.exit(1)

# Behavior settings
EXPIRY_SECONDS = 60               # 1 minute expiry
SIGNALS_PER_SESSION = 5
PAIRS = [
    ("EURUSD=X","EURUSD"),
    ("GBPUSD=X","GBPUSD"),
    ("USDJPY=X","USDJPY"),
    ("AUDUSD=X","AUDUSD"),
    ("USDCHF=X","USDCHF"),
    ("USDCAD=X","USDCAD"),
    ("NZDUSD=X","NZDUSD"),
]

# ---------------- Helpers ----------------
def tg_send(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": text})
        if r.status_code != 200:
            print("Telegram send failed:", r.status_code, r.text)
    except Exception as e:
        print("Telegram error:", e)

def ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def rsi(series, length=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    roll_up = up.ewm(alpha=1/length, adjust=False).mean()
    roll_down = down.ewm(alpha=1/length, adjust=False).mean()
    rs = roll_up / roll_down.replace(0, np.nan)
    r = 100 - (100 / (1 + rs))
    return r.fillna(50)

def vortex(df, length=14):
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    prev_low = low.shift(1)
    prev_high = high.shift(1)
    tr = (high - low).abs().combine((high - prev_close).abs(), max).combine((low - prev_close).abs(), max)
    vp = (high - prev_low).abs()
    vm = (low - prev_high).abs()
    sumTR = tr.rolling(length).sum()
    sumVP = vp.rolling(length).sum()
    sumVM = vm.rolling(length).sum()
    vi_plus = (sumVP / sumTR).fillna(method="bfill").fillna(1.0)
    vi_minus = (sumVM / sumTR).fillna(method="bfill").fillna(1.0)
    df = df.copy()
    df["vi_plus"] = vi_plus
    df["vi_minus"] = vi_minus
    return df

def fetch_df(ticker, interval, period):
    # returns dataframe with indicators
    try:
        df = yf.download(ticker, interval=interval, period=period, progress=False)
    except Exception as e:
        print("yfinance download error:", e)
        return None
    if df is None or df.empty:
        return None
    df = df.dropna().copy()
    df["EMA9"] = ema(df["Close"], 9)
    df["EMA21"] = ema(df["Close"], 21)
    df["RSI14"] = rsi(df["Close"], 14)
    df = vortex(df, 14)
    return df.dropna()

def score_from_df(df):
    if df is None or len(df) < 15:
        return None
    c = df.iloc[-1]
    p = df.iloc[-2]
    # EMA crossover detection
    ema_bull = (c.EMA9 > c.EMA21) and (p.EMA9 <= p.EMA21)
    ema_bear = (c.EMA9 < c.EMA21) and (p.EMA9 >= p.EMA21)
    # RSI crossing 50
    rsi_up50 = (c.RSI14 > 50) and (p.RSI14 <= 50)
    rsi_dn50 = (c.RSI14 < 50) and (p.RSI14 >= 50)
    # Vortex
    vort_bull = c.vi_plus > c.vi_minus
    vort_bear = c.vi_plus < c.vi_minus

    bull = int(bool(ema_bull)) + int(bool(rsi_up50)) + int(bool(vort_bull))
    bear = int(bool(ema_bear)) + int(bool(rsi_dn50)) + int(bool(vort_bear))

    gap = (c.EMA9 - c.EMA21) / max(abs(c.Close), 1e-9)
    vort_spread = (c.vi_plus - c.vi_minus)

    strength = (bull - bear) + (vort_spread * 0.3) + (gap * 200)
    if strength > 0:
        direction = "CALL"
        used = []
        if ema_bull: used.append("EMA")
        if rsi_up50: used.append("RSI")
        if vort_bull: used.append("Vortex")
    else:
        direction = "PUT"
        used = []
        if ema_bear: used.append("EMA")
        if rsi_dn50: used.append("RSI")
        if vort_bear: used.append("Vortex")
    strategy = "+".join(used) if used else "EMA+RSI+Vortex"
    return {"direction": direction, "strength": abs(float(strength)), "price": float(c.Close), "strategy": strategy}

def best_timeframe_signal(ticker):
    # Compare 1m vs 5m signals
    s1 = None; s5 = None
    try:
        d1 = fetch_df(ticker, "1m", "1d")
        s1 = score_from_df(d1)
    except Exception as e:
        print("1m fetch/score error:", e)
    try:
        d5 = fetch_df(ticker, "5m", "5d")
        s5 = score_from_df(d5)
    except Exception as e:
        print("5m fetch/score error:", e)
    if s1 and s5:
        return (s1, "1m") if s1["strength"] >= s5["strength"] else (s5, "5m")
    if s1:
        return (s1, "1m")
    if s5:
        return (s5, "5m")
    return (None, None)

def latest_price(ticker):
    try:
        df = yf.download(ticker, interval="1m", period="1d", progress=False)
        if df is None or df.empty:
            return None
        return float(df["Close"].iloc[-1])
    except Exception as e:
        print("latest_price error:", e)
        return None

# ---------------- Session flow ----------------
def run_session():
    if SESSION.lower() == "morning":
        tg_send("Good Morning Family")
        time.sleep(60)
        tg_send("Morning session starts")
    else:
        tg_send("Good Evening Family")
        time.sleep(60)
        tg_send("Evening session starts")

    # Build candidates
    candidates = []
    for yf_sym, nice in PAIRS:
        sig, tf = best_timeframe_signal(yf_sym)
        if not sig:
            continue
        sig["yf"] = yf_sym
        sig["pair"] = nice
        sig["tf"] = tf
        candidates.append(sig)

    if not candidates:
        tg_send("MSL Binary Signal\nPair: -\nDirection: -\nExpiry: -\nStrategy: No data")
        tg_send(("Morning" if SESSION.lower()=="morning" else "Evening") + " session ends")
        return

    candidates.sort(key=lambda x: x["strength"], reverse=True)
    used = set()
    queue = []
    for c in candidates:
        if c["pair"] in used: continue
        queue.append(c)
        used.add(c["pair"])
        if len(queue) >= SIGNALS_PER_SESSION: break

    # pad if fewer than required
    while len(queue) < SIGNALS_PER_SESSION and candidates:
        queue.append(candidates[0])

    # send signals one-by-one and evaluate after expiry
    for sig in queue:
        header = "MSL Binary Signal"
        body = f"Pair: {sig['pair']}\nDirection: {sig['direction']}\nExpiry: 1m\nStrategy: {sig['strategy']} | TF: {sig['tf']}"
        tg_send(header)
        time.sleep(0.5)
        tg_send(body)

        entry = latest_price(sig["yf"])
        time.sleep(EXPIRY_SECONDS)
        exitp = latest_price(sig["yf"])

        if entry is None or exitp is None:
            tg_send("⚪ Result: NO_PRICE")
        else:
            if sig["direction"] == "CALL":
                if exitp > entry:
                    tg_send("✅ Win\nCongratulation 🎊")
                else:
                    tg_send("❌ Lose\nKeep studying and reviewing trades.")
            else:
                if exitp < entry:
                    tg_send("✅ Win\nCongratulation 🎊")
                else:
                    tg_send("❌ Lose\nKeep studying and reviewing trades.")

    tg_send(("Morning" if SESSION.lower()=="morning" else "Evening") + " session ends")

if _name_ == "_main_":
    run_session()
