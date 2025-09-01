
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
    ("EURUSD=X","EUR/USD"),
    ("GBPUSD=X","GBP/USD"),
    ("USDJPY=X","USD/JPY"),
    ("AUDUSD=X","AUD/USD"),
    ("USDCHF=X","USD/CHF"),
    ("USDCAD=X","USD/CAD"),
    ("NZDUSD=X","NZD/USD"),
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
        })
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
    vi_plus = (sumVP / sumTR).fillna(method='bfill').fillna(1.0)
    vi_minus = (sumVM / sumTR).fillna(method='bfill').fillna(1.0)
    df = df.copy()
    df["vi_plus"] = vi_plus
    df["vi_minus"] = vi_minus
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
    return df.dropna()

def score_from_df(df):
    if df is None or len(df) < 15:
        return None
    c = df.iloc[-1]
    p = df.iloc[-2]

    ema_bull = (c.EMA9 > c.EMA21) and (p.EMA9 <= p.EMA21)
    ema_bear = (c.EMA9 < c.EMA21) and (p.EMA9 >= p.EMA21)
    rsi_up50 = (c.RSI14 > 50) and (p.RSI14 <= 50)
    rsi_dn50 = (c.RSI14 < 50) and (p.RSI14 >= 50)   # fixed bug (was p.EMA21)
    vort_bull = c.vi_plus > c.vi_minus
    vort_bear = c.vi_plus < c.vi_minus

    bull = int(ema_bull) + int(rsi_up50) + int(vort_bull)
    bear = int(ema_bear) + int(rsi_dn50) + int(vort_bear)

    gap = (c.EMA9 - c.EMA21) / max(abs(c.Close), 1e-9)
    vort_spread = (c.vi_plus - c.vi_minus)

    strength = (bull - bear) + (vort_spread * 0.3) + (gap * 200)
    direction = "CALL 🔼" if strength > 0 else "PUT 🔽"

    used = []
    if ema_bull or ema_bear: used.append("EMA")
    if rsi_up50 or rsi_dn50: used.append("RSI")
    if vort_bull or vort_bear: used.append("Vortex")

    return {
        "direction": direction,
        "strength": abs(float(strength)),
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
    try:
        df = yf.download(ticker, interval="1m", period="1d", progress=False)
        if df is None or df.empty:
            return None
        return float(df["Close"].iloc[-1])
    except Exception as e:
        print("latest price error", e)
        return None

# ---------------- Pretty formatting ----------------
def format_signal_card(sig, expiry_minutes):
    # Use <pre> to keep the box aligned in Telegram
    return (
        "<pre>"
        "┏━━━━━━━━ SIGNAL ━━━━━━━━\n"
        f"┃ Pair:      {sig['pair']}\n"
        f"┃ Direction: {sig['direction']}\n"
        f"┃ Expiry:    {expiry_minutes}m\n"
        f"┃ Strategy:  {sig['strategy']} | TF: {sig.get('tf','?')}\n"
        "┗━━━━━━━━━━━━━━━━━━━━━━━━━"
        "</pre>"
    )

# ---------------- Session flow (sequential) ----------------
def run_session():
    stylish_greeting()
    # Wait before first signal
    time.sleep(START_DELAY_SECONDS)

    # Build candidates
    candidates = []
    for yf_sym, nice in PAIRS:
        sig, tf = best_timeframe_signal(yf_sym)
        if sig:
            sig["yf"] = yf_sym
            sig["pair"] = nice
            sig["tf"] = tf
            candidates.append(sig)
        else:
            print(f"[INFO] No signal for {nice}")

    if not candidates:
        tg_send("⚠️ <b>No reliable signals found this session.</b>")
        tg_send(("<b>Morning session ends</b>" if SESSION.lower()=="morning" else "<b>Evening session ends</b>") + " ✅")
        return

    # Top N unique pairs
    candidates.sort(key=lambda x: x["strength"], reverse=True)
    queue, used = [], set()
    for c in candidates:
        if c["pair"] not in used:
            queue.append(c); used.add(c["pair"])
        if len(queue) >= SIGNALS_PER_SESSION:
            break

    # Sequential: send signal -> wait expiry -> send result -> wait 30s -> next
    for sig in queue:
        # Send card
        tg_send(format_signal_card(sig, int(EXPIRY_SECONDS/60)))
        # Capture entry
        entry_price = latest_price(sig["yf"])
        # Wait expiry
        time.sleep(EXPIRY_SECONDS)
        # Check result
        exit_price = latest_price(sig["yf"])
        if entry_price is None or exit_price is None:
            tg_send("⚪ <b>Result:</b> NO_PRICE")
        else:
            if ("CALL" in sig["direction"] and exit_price > entry_price) or \
               ("PUT"  in sig["direction"] and exit_price < entry_price):
                tg_send("✅ <b>Win</b>\nCongratulation 🎊")
            else:
                tg_send("❌ <b>Lose</b>\nKeep studying and reviewing trades.")
        # Pause before next signal
        time.sleep(AFTER_RESULT_DELAY)

    # End
    tg_send(("<b>Morning session ends</b>" if SESSION.lower()=="morning" else "<b>Evening session ends</b>") + " ✅")

if __name__ == "__main__":
    run_session()
