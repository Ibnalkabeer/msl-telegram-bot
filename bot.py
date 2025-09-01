import os, time, sys, requests
import pandas as pd
import numpy as np
import yfinance as yf

# ---------------- CONFIG ----------------
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SESSION = os.environ.get("SESSION", "morning")

if not TOKEN or not CHAT_ID:
    print("ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set as repo secrets")
    sys.exit(1)

# Behavior
EXPIRY_SECONDS = 300            # 5 minutes expiry
SIGNALS_PER_SESSION = 5
START_DELAY_SECONDS = 30        # wait after "session starts" before first signal
AFTER_RESULT_DELAY = 30         # wait after each result before next signal

PAIRS = [
    ("EURUSD=X","EUR/USD"), ("GBPUSD=X","GBP/USD"), ("USDJPY=X","USD/JPY"),
    ("AUDUSD=X","AUD/USD"), ("USDCHF=X","USD/CHF"), ("USDCAD=X","USD/CAD"),
    ("NZDUSD=X","NZD/USD"), ("EURJPY=X","EUR/JPY"), ("GBPJPY=X","GBP/JPY"),
    ("AUDJPY=X","AUD/JPY"), ("EURGBP=X","EUR/GBP"), ("EURAUD=X","EUR/AUD"),
    ("XAUUSD=X","Gold"), ("XAGUSD=X","Silver"),
    ("^GSPC","S&P 500"), ("^NDX","NASDAQ"),
]

# ---------------- Telegram ----------------
def tg_send(text, parse_mode="HTML"):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }, timeout=20)
        if r.status_code != 200:
            print("Telegram send failed:", r.status_code, r.text)
    except Exception as e:
        print("Telegram error:", e)

def stylish_greeting():
    if SESSION.lower() == "morning":
        tg_send("☀️ <b><i>Good Morning Family</i></b>")
        time.sleep(1)
        tg_send("<b>Morning session starts</b>\n\n📡 <b>MSL Binary Signal</b>")
    else:
        tg_send("🌙 <b><i>Good Evening Family</i></b>")
        time.sleep(1)
        tg_send("<b>Evening session starts</b>\n\n📡 <b>MSL Binary Signal</b>")

# ---------------- Indicators ----------------
def ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def rsi(series, length=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    roll_up = up.ewm(alpha=1/length, adjust=False).mean()
    roll_down = down.ewm(alpha=1/length, adjust=False).mean()
    rs = roll_up.div(roll_down.replace(0, np.nan))
    return (100 - (100 / (1 + rs))).fillna(50)

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
    df["vi_plus"] = (sumVP / sumTR).fillna(1.0)
    df["vi_minus"] = (sumVM / sumTR).fillna(1.0)
    return df

def add_extra_indicators(df):
    # MACD
    df["ema12"] = ema(df["Close"], 12)
    df["ema26"] = ema(df["Close"], 26)
    df["macd"] = df["ema12"] - df["ema26"]
    df["macd_signal"] = ema(df["macd"], 9)
    # Stochastic
    low14 = df["Low"].rolling(14).min()
    high14 = df["High"].rolling(14).max()
    df["stoch_k"] = 100 * (df["Close"] - low14) / (high14 - low14)
    df["stoch_d"] = df["stoch_k"].rolling(3).mean()
    # Bollinger Bands
    df["sma20"] = df["Close"].rolling(20).mean()
    std20 = df["Close"].rolling(20).std()
    df["bb_upper"] = df["sma20"] + 2 * std20
    df["bb_lower"] = df["sma20"] - 2 * std20
    return df

# ---------------- Data & Signal ----------------
def fetch_df(ticker, interval, period):
    try:
        df = yf.download(ticker, interval=interval, period=period, progress=False)
        if df is None or df.empty:
            print(f"[WARN] No data for {ticker} interval={interval}")
            return None
    except Exception as e:
        print(f"[ERROR] yfinance error {ticker} {interval}: {e}")
        return None
    df = df.dropna().copy()
    df["EMA9"] = ema(df["Close"], 9)
    df["EMA21"] = ema(df["Close"], 21)
    df["RSI14"] = rsi(df["Close"], 14)
    df = vortex(df, 14)
    df = add_extra_indicators(df)
    return df.dropna()

def score_from_df(df):
    # require enough history for the indicators
    if df is None or len(df) < 25:
        return None
    c, p = df.iloc[-1], df.iloc[-2]

    # Base signals
    ema_bull = (c.EMA9 > c.EMA21) and (p.EMA9 <= p.EMA21)
    ema_bear = (c.EMA9 < c.EMA21) and (p.EMA9 >= p.EMA21)
    rsi_up50 = (c.RSI14 > 50) and (p.RSI14 <= 50)
    rsi_dn50 = (c.RSI14 < 50) and (p.RSI14 >= 50)
    vort_bull = c.vi_plus > c.vi_minus
    vort_bear = c.vi_plus < c.vi_minus

    # New indicators
    macd_bull = (c.macd > c.macd_signal) and (p.macd <= p.macd_signal)
    macd_bear = (c.macd < c.macd_signal) and (p.macd >= p.macd_signal)
    stoch_bull = (not np.isnan(c.stoch_k)) and (c.stoch_k > c.stoch_d) and (c.stoch_k < 80)
    stoch_bear = (not np.isnan(c.stoch_k)) and (c.stoch_k < c.stoch_d) and (c.stoch_k > 20)
    bb_bull = c.Close < c.bb_lower
    bb_bear = c.Close > c.bb_upper

    # Combine scores
    bull = sum([ema_bull, rsi_up50, vort_bull, macd_bull, stoch_bull, bb_bull])
    bear = sum([ema_bear, rsi_dn50, vort_bear, macd_bear, stoch_bear, bb_bear])

    strength = float(bull - bear)
    direction = "CALL 🔼" if strength > 0 else "PUT 🔽"

    used = []
    if ema_bull or ema_bear: used.append("EMA")
    if rsi_up50 or rsi_dn50: used.append("RSI")
    if vort_bull or vort_bear: used.append("Vortex")
    if macd_bull or macd_bear: used.append("MACD")
    if stoch_bull or stoch_bear: used.append("Stoch")
    if bb_bull or bb_bear: used.append("BB")

    return {
        "direction": direction,
        "strength": abs(strength),
        "price": float(c.Close),
        "strategy": "+".join(used) if used else "EMA+RSI+Vortex"
    }

def best_timeframe_signal(ticker):
    # try 1m → 5m → fallback 15m
    for interval, period in [("1m", "1d"), ("5m", "5d"), ("15m", "1mo")]:
        try:
            df = fetch_df(ticker, interval, period)
            sig = score_from_df(df)
            if sig:
                return (sig, interval)
        except Exception as e:
            print(f"[ERROR] {ticker} {interval}: {e}")
    return (None, None)

def latest_price(ticker):
    # try 1m, fallback 5m or last close
    for interval in ["1m", "5m", "15m"]:
        try:
            df = yf.download(ticker, interval=interval, period="1d", progress=False)
            if df is None or df.empty:
                continue
            return float(df["Close"].iloc[-1])
        except Exception:
            continue
    return None

# ---------------- Pretty formatting ----------------
def format_signal_card(sig, expiry_minutes, note=""):
    pre = (
        "<pre>"
        "┏━━━━━━━━ SIGNAL ━━━━━━━━\n"
        f"┃ Pair:      {sig['pair']}\n"
        f"┃ Direction: {sig['direction']}\n"
        f"┃ Expiry:    {expiry_minutes}m\n"
        f"┃ Strategy:  {sig['strategy']} | TF: {sig.get('tf','?')}\n"
        "┗━━━━━━━━━━━━━━━━━━━━━━━━━"
        "</pre>"
    )
    if note:
        pre += f"\n⚠️ <i>{note}</i>"
    return pre

# ---------------- Session flow ----------------
def run_session():
    stylish_greeting()
    # Wait before first signal
    time.sleep(START_DELAY_SECONDS)

    candidates = []
    for yf_sym, nice in PAIRS:
        sig, tf = best_timeframe_signal(yf_sym)
        if sig:
            sig["yf"] = yf_sym
            sig["pair"] = nice
            sig["tf"] = tf
            candidates.append(sig)
        else:
            print(f"[INFO] No strong signal for {nice}")

    # --- Fallback: attempt a looser scan on 5m if nothing found ---
    if not candidates:
        print("[INFO] No strict candidates — performing fallback scan on 5m for all pairs.")
        for yf_sym, nice in PAIRS:
            df = fetch_df(yf_sym, "5m", "5d")
            if df is None:
                continue
            sig = score_from_df(df)
            if sig:
                sig["yf"] = yf_sym
                sig["pair"] = nice
                sig["tf"] = "5m"
                # mark fallback note in strategy if it's weak
                sig["strategy"] = sig.get("strategy", "") + " | fallback"
                candidates.append(sig)

    # --- If still no candidates: momentum fallback (guarantee signals) ---
    if not candidates:
        print("[WARN] Fallback scan failed — using momentum fallback to guarantee signals.")
        momentums = []
        for yf_sym, nice in PAIRS:
            df = fetch_df(yf_sym, "15m", "7d")
            if df is None or df.empty:
                continue
            # simple momentum: percent change over the fetched window
            try:
                first = df["Close"].iloc[0]
                last = df["Close"].iloc[-1]
                mom = (last - first) / first
                direction = "CALL 🔼" if mom > 0 else "PUT 🔽"
                strength = abs(mom)
                momentums.append({"yf": yf_sym, "pair": nice, "direction": direction, "strength": strength, "price": float(last), "strategy": "MomentumFallback", "tf": "15m"})
            except Exception as e:
                print("momentum calc error", e)
                continue
        # pick top by absolute momentum
        momentums.sort(key=lambda x: x["strength"], reverse=True)
        for m in momentums[:SIGNALS_PER_SESSION]:
            candidates.append(m)

    # sort and dedupe by pair, pick top N
    candidates.sort(key=lambda x: x["strength"], reverse=True)
    queue, used = [], set()
    for c in candidates:
        if c["pair"] in used:
            continue
        queue.append(c)
        used.add(c["pair"])
        if len(queue) >= SIGNALS_PER_SESSION:
            break

    if not queue:
        tg_send("⚠️ <b>Unable to produce any signals this session.</b>")
        tg_send(("<b>Morning session ends</b>" if SESSION.lower()=="morning" else "<b>Evening session ends</b>") + " ✅")
        return

    # Sequential send -> wait expiry -> post result -> wait AFTER_RESULT_DELAY
    for sig in queue:
        # Ensure sig has required keys (momentum fallback may differ)
        if "tf" not in sig:
            sig["tf"] = sig.get("tf","?")
        if "strategy" not in sig:
            sig["strategy"] = sig.get("strategy","Mixed")

        tg_send(format_signal_card(sig, int(EXPIRY_SECONDS/60), note="Auto-generated signal"))
        # capture entry price
        entry_price = latest_price(sig["yf"])
        # wait expiry
        time.sleep(EXPIRY_SECONDS)
        # get exit price
        exit_price = latest_price(sig["yf"])
        if entry_price is None or exit_price is None:
            tg_send("⚪ <b>Result:</b> NO_PRICE")
        else:
            # check win
            if ("CALL" in sig["direction"] and exit_price > entry_price) or \
               ("PUT" in sig["direction"] and exit_price < entry_price):
                tg_send("✅ <b>Win</b>\nCongratulation 🎊")
            else:
                tg_send("❌ <b>Lose</b>\nKeep studying and reviewing trades.")
        # wait before next
        time.sleep(AFTER_RESULT_DELAY)

    # End message
    tg_send(("<b>Morning session ends</b>" if SESSION.lower()=="morning" else "<b>Evening session ends</b>") + " ✅")

if __name__ == "__main__":
    run_session()
