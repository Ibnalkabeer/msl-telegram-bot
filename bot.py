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

# ---------- FIX ADDED: get_data ----------
def get_data(symbol):
    """Fetch latest price data safely from Yahoo Finance"""
    try:
        df = yf.download(symbol, period="5d", interval="5m")
        return df
    except Exception as e:
        print(f"Data fetch failed for {symbol}: {e}")
        return pd.DataFrame()

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
           
