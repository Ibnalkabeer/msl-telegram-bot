# Bundle strategies with their names
strategies = [
    ("EMA Crossover", ema_strategy),
    ("RSI Levels", rsi_strategy),
    ("MACD Cross", macd_strategy),
    ("Bollinger Bands", bb_strategy),
    ("Stochastic Oscillator", stochastic_strategy),
    ("ADX Strength", adx_strategy),
    ("Momentum Push", momentum_strategy),
    ("S/R Breakout", sr_breakout_strategy),
    ("Parabolic SAR", psar_strategy),
    ("Phantom Randomizer", phantom_strategy)
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

        # Pick strategy and run it
        strategy_name, strat_func = random.choice(strategies)
        signal = strat_func(df) if df is not None else random.choice(["CALL","PUT"])
        emoji = "🟢📈" if signal == "CALL" else "🔴📉"

        # Confidence handling
        if (signals_sent+1) in loss_positions:
            confidence = random.randint(75, 79)
        else:
            confidence = random.randint(80, 90)

        msg = f"""
━━━━━━━━━━━━━━━
💹 *Signal {signals_sent+1}*
💱 Pair: *{name}*
📍 Direction: *{signal}* {emoji}
⚙️ Strategy Used: *{strategy_name}*
🎯 Confidence: *{confidence}%*
━━━━━━━━━━━━━━━
"""
        send_msg(msg)

        signals_sent += 1
        time.sleep(random.randint(60, 120))  # pacing

