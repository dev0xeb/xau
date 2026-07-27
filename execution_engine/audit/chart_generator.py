#!/usr/bin/env python3
"""
chart_generator.py - Automatic Trade Chart Snapshot Generator

Generates publication-quality Matplotlib chart images (or HTML fallback) for entry & exit points:
- Saved to charts/YYYY-MM-DD/trade_XXXX_entry.png & trade_XXXX_exit.png
"""

import os
from datetime import datetime, timezone

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

class TradeChartGenerator:
    """Generates price action chart visual snapshots for trades."""

    def __init__(self, charts_dir: str = "charts"):
        self.charts_dir = charts_dir
        os.makedirs(self.charts_dir, exist_ok=True)

    def generate_entry_chart(
        self,
        trade_id: str,
        prices: list,
        entry_price: float,
        sl_price: float = None,
        tp_price: float = None
    ) -> str:
        """Generates trade entry chart snapshot."""
        now_dt = datetime.now(timezone.utc)
        date_folder = os.path.join(self.charts_dir, now_dt.strftime("%Y-%m-%d"))
        os.makedirs(date_folder, exist_ok=True)

        img_filename = f"{trade_id}_entry.png"
        img_path = os.path.join(date_folder, img_filename)

        if HAS_MATPLOTLIB and prices:
            try:
                fig, ax = plt.subplots(figsize=(8, 4))
                ax.plot(prices, color="#38bdf8", label="XAUUSD Price")
                ax.axhline(y=entry_price, color="#4ade80", linestyle="--", label=f"Entry (${entry_price:.2f})")
                if sl_price:
                    ax.axhline(y=sl_price, color="#f87171", linestyle=":", label=f"SL (${sl_price:.2f})")
                if tp_price:
                    ax.axhline(y=tp_price, color="#34d399", linestyle=":", label=f"TP (${tp_price:.2f})")

                ax.set_title(f"Trade Entry Snapshot — {trade_id}")
                ax.legend(loc="upper left")
                plt.tight_layout()
                plt.savefig(img_path)
                plt.close(fig)
                return img_path
            except Exception as e:
                print(f"[CHART WARN] Matplotlib render failed: {e}. Falling back to HTML.")

        # HTML fallback
        html_path = img_path.replace(".png", ".html")
        with open(html_path, "w") as f:
            f.write(f"<html><body><h2>Trade Entry Snapshot {trade_id}</h2><p>Entry: ${entry_price:.2f}</p></body></html>")
        return html_path
