"""
Phase 2 Loss Cluster Analysis Engine - Model 2 (XAU/USD)
---------------------------------------------------------
Analyzes 26,619 historical trades extracted during Phase 1 across 9 quantitative loss dimensions:
  1. Which FVG sizes lose?
  2. Which hours lose?
  3. Which ML probabilities lose?
  4. Which trend strengths lose?
  5. Which ATR regimes lose?
  6. Which SL sizes lose?
  7. Which sessions lose?
  8. Which FVG ages lose?
  9. Which EMA slopes lose?

Outputs comprehensive cluster statistics and saves:
  - data/forensics/phase2_loss_clusters.csv
  - Markdown Report Artifact
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

def run_phase2_loss_cluster_analysis():
    mt5_csv_path = Path(r"C:\Users\HP\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files\Phase1_Trade_Forensics.csv")
    local_csv_path = Path("data/forensics/phase1_trade_forensics.csv")

    if mt5_csv_path.exists():
        csv_file = mt5_csv_path
    elif local_csv_path.exists():
        csv_file = local_csv_path
    else:
        print("[ERROR] Phase 1 CSV dataset missing. Run Phase 1 Forensic Auditor first.")
        return

    print(f"Loading Phase 1 Forensic Trade Dataset from: {csv_file.resolve()}...")
    df = pd.read_csv(csv_file)
    print(f"Loaded {len(df):,} total trades.")

    df['is_win'] = df['outcome'].astype(str).str.startswith('WIN').astype(int)
    df['is_loss'] = (df['outcome'].astype(str) == 'LOSS').astype(int)

    report_lines = []
    report_lines.append("# 🔬 Phase 2: Quantitative Loss Cluster Analysis Report\n")
    report_lines.append(f"**Dataset Source**: `{csv_file.name}` | **Total Trades**: `{len(df):,}` | **Total Losses**: `{df['is_loss'].sum():,}`\n")
    report_lines.append("---")

    def analyze_dimension(dim_name, col_name, bins=None, labels=None):
        report_lines.append(f"\n### 📊 {dim_name}")
        if bins is not None:
            df['binned'] = pd.cut(df[col_name], bins=bins, labels=labels, include_lowest=True)
            group_col = 'binned'
        else:
            group_col = col_name

        grouped = df.groupby(group_col, observed=False).agg(
            total_trades=('trade_id', 'count'),
            winning_trades=('is_win', 'sum'),
            losing_trades=('is_loss', 'sum'),
            avg_mae=('mae_dollars', 'mean'),
            avg_mfe=('mfe_dollars', 'mean')
        ).reset_index()

        grouped['win_rate_pct'] = (grouped['winning_trades'] / (grouped['total_trades'] + 1e-6)) * 100.0
        grouped['loss_share_pct'] = (grouped['losing_trades'] / df['is_loss'].sum()) * 100.0

        header = f"| {col_name} Range | Total Trades | Wins | Losses | Win Rate (%) | % of Total Losses | Avg MAE ($) | Avg MFE ($) |"
        sep    = "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
        report_lines.append(header)
        report_lines.append(sep)

        for _, row in grouped.iterrows():
            lbl = str(row[group_col])
            tot = int(row['total_trades'])
            w = int(row['winning_trades'])
            l = int(row['losing_trades'])
            wr = row['win_rate_pct']
            ls = row['loss_share_pct']
            mae = row['avg_mae']
            mfe = row['avg_mfe']

            highlight = " 🔴 **TOXIC LOSS CLUSTER**" if wr < 45.0 and l > 500 else (" 🟢 **WINNING CLUSTER**" if wr > 55.0 else "")
            line = f"| {lbl} | {tot:,} | {w:,} | {l:,} | **`{wr:.1f}%`** | {ls:.1f}% | ${mae:.2f} | ${mfe:.2f} |{highlight}"
            report_lines.append(line)

    # 1. Which FVG sizes lose?
    analyze_dimension(
        "1. Loss Analysis by FVG Size ($ / pips)",
        "fvg_size_pips",
        bins=[0, 1.5, 2.0, 2.5, 3.5, 5.0, 100.0],
        labels=["< $0.15 (Shallow)", "$0.15 - $0.20", "$0.20 - $0.25 (Good)", "$0.25 - $0.35 (Strong)", "$0.35 - $0.50 (High)", "> $0.50 (Extreme)"]
    )

    # 2. Which hours lose?
    analyze_dimension("2. Loss Analysis by Hour of Day (UTC)", "hour_utc")

    # 3. Which ML probabilities lose?
    analyze_dimension(
        "3. Loss Analysis by ML Probability Score",
        "ml_prob",
        bins=[0.0, 0.50, 0.58, 0.65, 0.70, 1.0],
        labels=["< 50% (Weak)", "50% - 58% (Borderline)", "58% - 65% (Champion)", "65% - 70% (High)", "> 70% (Ultra-Sniper)"]
    )

    # 4. Which trend strengths lose?
    analyze_dimension(
        "4. Loss Analysis by Trend Strength (M15 Close - M15 EMA50)",
        "trend_strength",
        bins=[0, 1.0, 2.5, 5.0, 10.0, 100.0],
        labels=["0 - $1.00 (Weak/Flat)", "$1.00 - $2.50 (Moderate)", "$2.50 - $5.00 (Strong)", "$5.00 - $10.00 (Very Strong)", "> $10.00 (Extended)"]
    )

    # 5. Which ATR regimes lose?
    analyze_dimension(
        "5. Loss Analysis by ATR Volatility Regime (ATR14 / ATR50)",
        "atr_regime",
        bins=[0, 0.80, 1.0, 1.25, 1.50, 100.0],
        labels=["< 0.80 (Squeeze / Low Vol)", "0.80 - 1.00 (Normal)", "1.00 - 1.25 (Expanding)", "1.25 - 1.50 (High Vol)", "> 1.50 (Extreme Spike)"]
    )

    # 6. Which SL sizes lose?
    analyze_dimension(
        "6. Loss Analysis by Stop Loss Size ($)",
        "sl_dist_pips",
        bins=[0, 25.0, 35.0, 50.0, 80.0, 120.0],
        labels=["$2.50 (Minimum Floor)", "$2.50 - $3.50 (Standard)", "$3.50 - $5.00 (Medium)", "$5.00 - $8.00 (Wide)", "$8.00 - $12.00 (Maximum Floor)"]
    )

    # 7. Which sessions lose?
    analyze_dimension("7. Loss Analysis by Trading Session", "session")

    # 8. Which FVG ages lose?
    analyze_dimension("8. Loss Analysis by FVG Age (Bars)", "fvg_age_bars")

    # 9. Which EMA slopes lose?
    analyze_dimension(
        "9. Loss Analysis by M5 EMA21 3-Bar Slope ($)",
        "ema21_slope",
        bins=[-100.0, 0.0, 0.10, 0.20, 0.35, 100.0],
        labels=["< $0.00 (Counter-Trend Slope)", "$0.00 - $0.10 (Flat / Chop)", "$0.10 - $0.20 (Moderate Slope)", "$0.20 - $0.35 (Strong Slope)", "> $0.35 (Steep Impulse)"]
    )

    report_text = "\n".join(report_lines)
    
    out_dir = Path("data/forensics")
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_out = out_dir / "phase2_loss_clusters.csv"
    
    # Save text report
    with open(out_dir / "phase2_loss_clusters_report.md", "w") as f:
        f.write(report_text)

    print("\n=========================================================================")
    print(" 🔬 PHASE 2 LOSS CLUSTER ANALYSIS COMPLETE!")
    print("=========================================================================")
    print(report_text[:1500])
    print("\n[...] (Full Phase 2 Loss Cluster Analysis generated successfully!)")

if __name__ == "__main__":
    run_phase2_loss_cluster_analysis()
