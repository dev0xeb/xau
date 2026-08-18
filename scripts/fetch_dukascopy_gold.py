"""
Script to test fetching Gold M5 candles from online sources (Dukascopy / Yahoo / Stooq / MT5)
for August 10 to August 14, 2026.
"""

import sys
import struct
import lzma
import urllib.request
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

def fetch_dukascopy_ticks(date_obj, hour):
    # Dukascopy URL pattern for XAUUSD ticks
    url = f"https://datafeed.dukascopy.com/datafeed/XAUUSD/{date_obj.year}/{date_obj.month - 1:02d}/{date_obj.day:02d}/{hour:02d}h_ticks.bi5"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            data = response.read()
            if not data:
                return pd.DataFrame()
            decompressed = lzma.decompress(data)
            # Each tick record is 20 bytes: time (int32 ms), ask (int32), bid (int32), ask_vol (float32), bid_vol (float32)
            n_ticks = len(decompressed) // 20
            ticks = []
            base_time = datetime(date_obj.year, date_obj.month, date_obj.day, hour, 0, 0, tzinfo=timezone.utc)
            for i in range(n_ticks):
                t_ms, ask, bid, ask_v, bid_v = struct.unpack('>IIIff', decompressed[i*20:(i+1)*20])
                tick_time = base_time + timedelta(milliseconds=t_ms)
                # Dukascopy XAUUSD point scale is 1000
                ticks.append({
                    'timestamp': tick_time,
                    'ask': ask / 1000.0,
                    'bid': bid / 1000.0,
                    'price': (ask + bid) / 2000.0,
                    'volume': ask_v + bid_v
                })
            return pd.DataFrame(ticks)
    except Exception as e:
        return pd.DataFrame()

def test_fetch_week():
    print("Testing Dukascopy tick downloader for XAUUSD (Aug 10 - Aug 14, 2026)...")
    all_ticks = []
    # Test for Aug 11, 2026
    test_date = datetime(2026, 8, 11, tzinfo=timezone.utc)
    for h in range(6, 17):
        df_h = fetch_dukascopy_ticks(test_date, h)
        if not df_h.empty:
            all_ticks.append(df_h)
            print(f" Hour {h:02d}: {len(df_h)} ticks downloaded!")
    
    if all_ticks:
        df_all = pd.concat(all_ticks, ignore_index=True)
        print("Total ticks downloaded for Aug 11:", len(df_all))
        # Resample to 5m OHLC
        df_all.set_index('timestamp', inplace=True)
        df_5m = df_all['price'].resample('5min').ohlc().dropna().reset_index()
        print("Resampled to 5m OHLC:")
        print(df_5m.head())

if __name__ == "__main__":
    test_fetch_week()
