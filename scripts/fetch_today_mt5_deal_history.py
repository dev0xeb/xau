"""
Query MT5 deal history for today (Aug 17, 2026) to calculate exact PnL and trade outcomes 
for Personal Engine (Magic 2001) and Prop Firm Engine (Magic 2002).
"""

import sys
from datetime import datetime, timezone
import pandas as pd

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

def fetch_today_deals():
    if not MT5_AVAILABLE or not mt5.initialize():
        print("[ERROR] Could not initialize MetaTrader 5.")
        return

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    now = datetime.now(timezone.utc)

    deals = mt5.history_deals_get(today_start, now)
    if deals is None or len(deals) == 0:
        print("[INFO] No closed deal history found for today in MT5.")
        mt5.shutdown()
        return

    df_deals = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    df_deals['time'] = pd.to_datetime(df_deals['time'], unit='s', utc=True)

    print("=========================================================================================")
    print(" LIVE MT5 DEMO ACCOUNT DEAL HISTORY LOGS (TODAY: AUGUST 17, 2026)")
    print("=========================================================================================\n")

    account_info = mt5.account_info()
    if account_info:
        print(f" Account Login  : #{account_info.login} ({account_info.server})")
        print(f" Current Balance: ${account_info.balance:,.2f} USD")
        print(f" Current Equity : ${account_info.equity:,.2f} USD\n")

    # Filter by magic numbers
    pers_deals = df_deals[df_deals['magic'] == 2001]
    prop_deals = df_deals[df_deals['magic'] == 2002]

    pers_pnl = pers_deals['profit'].sum() + pers_deals['commission'].sum() + pers_deals['swap'].sum()
    prop_pnl = prop_deals['profit'].sum() + prop_deals['commission'].sum() + prop_deals['swap'].sum()

    print("-----------------------------------------------------------------------------------------")
    print(" TODAY'S DAILY PNL SUMMARY TABLE")
    print("-----------------------------------------------------------------------------------------")
    print(f" Personal Account Engine (Magic 2001): {len(pers_deals)} Deals | Net PnL: ${pers_pnl:+,.2f} USD")
    print(f" Prop Firm Engine       (Magic 2002): {len(prop_deals)} Deals | Net PnL: ${prop_pnl:+,.2f} USD")
    print("-----------------------------------------------------------------------------------------\n")

    print("DETAILED DEAL HISTORY FOR TODAY:")
    for idx, row in df_deals.iterrows():
        if row['magic'] in [2001, 2002]:
            engine = "PERSONAL (2001)" if row['magic'] == 2001 else "PROP FIRM (2002)"
            deal_type = "BUY" if row['type'] == 0 else "SELL"
            ts = row['time'].strftime('%H:%M:%S UTC')
            pnl = row['profit'] + row['commission'] + row['swap']
            print(f" [{ts}] Engine: {engine:15s} | Ticket: #{row['order']} | Deal: #{row['ticket']} | {deal_type:4s} {row['volume']:.2f} Lots @ ${row['price']:.2f} | PnL: ${pnl:+7.2f} | Comment: {row['comment']}")

    mt5.shutdown()

if __name__ == "__main__":
    fetch_today_deals()
