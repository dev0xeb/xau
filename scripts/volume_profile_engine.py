"""
Volume Profile Engine for XAU/USD (Gold).

Calculates Auction Market Theory Volume Profile Metrics:
- Session VAH (Value Area High - 70% Volume Upper Limit)
- Session VAL (Value Area Low - 70% Volume Lower Limit)
- Session POC (Point of Control - Price with Max Volume)
- High Volume Nodes (HVNs - Consolidation / Resistance Clusters)
- Low Volume Nodes (LVNs - Thin Liquidity / Fast Displacement Corridors)
"""

import numpy as np
import pandas as pd

class VolumeProfileEngine:
    def __init__(self, bin_size=0.20, va_pct=0.70):
        """
        :param bin_size: Price resolution bin in dollars (e.g., $0.20 on XAU/USD).
        :param va_pct: Value area percentage (standard 0.70 = 70% volume).
        """
        self.bin_size = bin_size
        self.va_pct = va_pct

    def compute_profile(self, prices_high, prices_low, prices_close, volumes=None):
        """
        Computes the volume profile across a array of candles.
        If tick volumes are not available, uses bar range volatility as proxy.
        """
        if len(prices_close) == 0:
            return None

        if volumes is None or len(volumes) == 0 or np.all(volumes == 0):
            # Volume proxy based on bar range volatility
            bar_ranges = np.maximum(prices_high - prices_low, 0.10)
            volumes = bar_ranges * 1000.0

        min_p = np.min(prices_low)
        max_p = np.max(prices_high)

        min_bin = np.floor(min_p / self.bin_size) * self.bin_size
        max_bin = np.ceil(max_p / self.bin_size) * self.bin_size + self.bin_size
        bins = np.arange(min_bin, max_bin, self.bin_size)

        bin_volumes = np.zeros(len(bins) - 1)

        # Distribute bar volume across price bins touched by each bar
        for h, l, v in zip(prices_high, prices_low, volumes):
            idx_start = max(0, int(np.floor((l - min_bin) / self.bin_size)))
            idx_end = min(len(bin_volumes) - 1, int(np.floor((h - min_bin) / self.bin_size)))
            n_bins = max(1, idx_end - idx_start + 1)
            vol_per_bin = v / n_bins
            bin_volumes[idx_start : idx_end + 1] += vol_per_bin

        bin_centers = bins[:-1] + self.bin_size / 2.0
        total_volume = np.sum(bin_volumes)

        if total_volume == 0:
            return None

        # 1. Point of Control (POC)
        poc_idx = np.argmax(bin_volumes)
        poc_price = bin_centers[poc_idx]

        # 2. Value Area (70% Volume expansion around POC)
        target_va_vol = total_volume * self.va_pct
        accumulated_vol = bin_volumes[poc_idx]
        va_indices = {poc_idx}

        up_ptr = poc_idx + 1
        dn_ptr = poc_idx - 1

        while accumulated_vol < target_va_vol and (up_ptr < len(bin_volumes) or dn_ptr >= 0):
            up_vol = bin_volumes[up_ptr] if up_ptr < len(bin_volumes) else -1
            dn_vol = bin_volumes[dn_ptr] if dn_ptr >= 0 else -1

            if up_vol >= dn_vol and up_vol >= 0:
                accumulated_vol += up_vol
                va_indices.add(up_ptr)
                up_ptr += 1
            elif dn_vol > up_vol and dn_vol >= 0:
                accumulated_vol += dn_vol
                va_indices.add(dn_ptr)
                dn_ptr -= 1
            else:
                break

        va_prices = bin_centers[list(va_indices)]
        vah = np.max(va_prices)
        val = np.min(va_prices)

        # 3. High Volume Nodes (HVNs) and Low Volume Nodes (LVNs)
        vol_75th = np.percentile(bin_volumes, 75)
        vol_25th = np.percentile(bin_volumes, 25)

        hvn_prices = bin_centers[bin_volumes >= vol_75th]
        lvn_prices = bin_centers[bin_volumes <= vol_25th]

        return {
            "poc": poc_price,
            "vah": vah,
            "val": val,
            "hvn_prices": hvn_prices,
            "lvn_prices": lvn_prices,
            "bin_centers": bin_centers,
            "bin_volumes": bin_volumes,
            "total_volume": total_volume
        }

if __name__ == "__main__":
    print("[INIT] Volume Profile Engine compiled successfully.")
