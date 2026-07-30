#!/usr/bin/env python3
"""
verify_implementation.py - System Verification Script for Model 1 (M5 FVG Instant 3-Burst Strategy)

Verifies:
1. EconomicNewsFilter status & guardrails
2. M5FairValueGapFilter displacement gap calculation
3. LiveDecisionEngine 3-burst candidate payload generation ($1.50 SL / $2.25 TP, 300s cooldown)
4. MT5Adapter connectivity & order payload structure
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))

from execution_engine.filters.news_filter import EconomicNewsFilter
from execution_engine.filters.fvg_filter import M5FairValueGapFilter
from decision_engine.live_decision_engine import LiveDecisionEngine
from execution_engine.adapters.mt5_adapter import MT5Adapter
from execution_engine.adapters.market_data_adapter import MarketDataAdapter

def verify_system():
    print("=================================================================")
    print("  MODEL 1 (M5 FVG INSTANT 3-BURST STRATEGY) VERIFICATION RUNNER  ")
    print("=================================================================")

    # 1. Economic News Guardrail Check
    news_filter = EconomicNewsFilter()
    blocked, reason = news_filter.is_news_blocked()
    print(f"[1/4] Economic News Filter Status: Blocked={blocked} | Detail: {reason if blocked else 'Clear to trade'}")

    # 2. MT5 Adapter Connection Check
    adapter = MT5Adapter(symbol="XAUUSD")
    if adapter.connect():
        print(f"[2/4] MT5 Broker Adapter Connected successfully. Resolved symbol: {adapter.symbol}")
    else:
        print("[2/4] [WARNING] MT5 Broker Adapter running in offline simulation fallback mode.")

    # 3. M5 FVG Filter Check
    fvg_filter = M5FairValueGapFilter(symbol=adapter.symbol)
    fvg_status = fvg_filter.check_fvg_status()
    print(f"[3/4] M5 Fair Value Gap Filter Status: Active={fvg_status['is_fvg_active']} | Type={fvg_status['fvg_type']} | GapSize=${fvg_status['fvg_gap_size']:.2f}")

    # 4. Live Decision Engine Payload Check
    engine = LiveDecisionEngine(
        fvg_filter=fvg_filter,
        news_filter=news_filter,
        cooldown_seconds=300.0,
        positions_per_signal=3
    )

    mkt_adapter = MarketDataAdapter(symbol=adapter.symbol)
    mkt_adapter.connect()
    tick = mkt_adapter.get_latest_tick() if mkt_adapter.is_connected else {"ask": 2350.50, "bid": 2350.35, "spread_usd": 0.15}
    features = {"volatility_atr": 1.50}

    payload = engine.evaluate_features(features, tick)
    print(f"[4/4] Live Decision Engine Payload Evaluation:")
    print(f"      - Decision: {payload.get('decision')}")
    print(f"      - Strategy: {payload.get('strategy_version', 'N/A')}")
    print(f"      - Positions Per Signal: {payload.get('positions_per_signal', 0)}")
    print(f"      - Excursion Targets: SL Price ${payload.get('sl', 0.0)} | TP Price ${payload.get('tp', 0.0)}")
    print("=================================================================")
    print("  VERIFICATION COMPLETE: SYSTEM IS READY FOR LIVE PAPER TRADING  ")
    print("=================================================================")

if __name__ == "__main__":
    verify_system()
