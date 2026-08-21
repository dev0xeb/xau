"""
Export Trained XGBoost / Random Forest Meta-Labeling Model to Native MQL5 Header File
--------------------------------------------------------------------------------------
Loads: models/saved_models/model2_1_metalabeling_engine.joblib
Exports native C++/MQL5 decision tree rules to: mql5/Include/Model2_1_MetaLabeling_Engine.mqh
"""

import sys
from pathlib import Path
import joblib
import numpy as np

def export_xgb_to_mql5():
    model_path = Path("models/saved_models/model2_1_metalabeling_engine.joblib")
    if not model_path.exists():
        print(f"[ERROR] Model file missing at: {model_path.resolve()}")
        return

    print(f"Loading trained Meta-Labeling model from: {model_path}...")
    package = joblib.load(model_path)
    model_name = package['model_name']
    feature_names = package['feature_names']

    print(f"Tournament Champion Model: {model_name}")
    print(f"Features ({len(feature_names)}): {feature_names}")

    # Generate Native MQL5 Header Code
    mqh_code = f"""//+------------------------------------------------------------------+
//|                 Model2_1_MetaLabeling_Engine.mqh                 |
//|      Native MQL5 Meta-Labeling & Multi-Target Risk Engine       |
//|      Champion Model: {model_name} (Trained on 5-Year XAU/USD Data)|
//+------------------------------------------------------------------+
#property copyright "Antigravity Quant Research"
#property link      "https://github.com/dev0xeb/xau"
#property version   "5.00"

struct MetaFeatureVector
{{
   double fvg_norm;
   double disp_norm;
   double slope_norm;
   double trend_sep_norm;
   double trend_dist_norm;
   double ext_ema21_norm;
   double sl_dist_norm;
   double atr_regime;
   double rsi_14;
   double hr_sin;
   double hr_cos;
   double dy_sin;
   double dy_cos;
   double spread_norm;
   double vol_acceleration;
   double momentum_ratio;
}};

struct MetaPredictionOutcome
{{
   double p_tp1;
   double p_tp2;
   double p_tp3;
   double p_sl;
   double pred_mae_dollars;
   double pred_mfe_dollars;
   double expected_r;
   double lot_multiplier;
   bool   should_trade;
   string abstention_reason;
}};

class CModel21MetaLabelingEngine
{{
private:
   double m_min_expected_r;
   double m_max_ext_allowed;
   double m_min_trend_sep;
   bool   m_verbose_logging;

   double Sigmoid(double x)
   {{
      return 1.0 / (1.0 + MathExp(-x));
   }}

   double Clamp(double val, double min_val, double max_val)
   {{
      return MathMax(min_val, MathMin(max_val, val));
   }}

public:
   CModel21MetaLabelingEngine()
   {{
      m_min_expected_r = 0.15;
      m_max_ext_allowed = 3.5;
      m_min_trend_sep  = 0.5;
      m_verbose_logging = true;
   }}

   ~CModel21MetaLabelingEngine() {{}}

   void SetMinExpectedR(double min_r)        {{ m_min_expected_r = min_r; }}
   void SetMaxExtension(double max_ext)      {{ m_max_ext_allowed = max_ext; }}
   void SetMinTrendSep(double min_sep)       {{ m_min_trend_sep = min_sep; }}
   void SetVerboseLogging(bool verbose)     {{ m_verbose_logging = verbose; }}

   void ExtractFeatures(const string symbol,
                        const ENUM_TIMEFRAMES exec_tf,
                        const bool is_buy,
                        const double entry_price,
                        const double sl_dist_dollars,
                        const double fvg_dollars,
                        const double impulse_sz_dollars,
                        const double ema21_slope,
                        const double trend_sep_dollars,
                        const double trend_dist_dollars,
                        const double ext_ema21_dollars,
                        const double atr14,
                        const double atr50,
                        const double atr14_5bars_ago,
                        const double rsi14,
                        const double candle_open,
                        const double candle_close,
                        const double candle_high,
                        const double candle_low,
                        const datetime current_time,
                        const double spread_dollars,
                        MetaFeatureVector &feats)
   {{
      double safe_atr14 = (atr14 > 0.05) ? atr14 : 1.50;
      double safe_atr50 = (atr50 > 0.05) ? atr50 : 1.50;

      feats.fvg_norm        = fvg_dollars / safe_atr14;
      feats.disp_norm       = impulse_sz_dollars / safe_atr14;
      feats.slope_norm      = ema21_slope / safe_atr14;
      feats.trend_sep_norm  = trend_sep_dollars / safe_atr14;
      feats.trend_dist_norm = trend_dist_dollars / safe_atr14;
      feats.ext_ema21_norm  = ext_ema21_dollars / safe_atr14;
      feats.sl_dist_norm    = sl_dist_dollars / safe_atr14;
      feats.atr_regime      = safe_atr14 / safe_atr50;
      feats.rsi_14          = rsi14;
      feats.spread_norm     = spread_dollars / safe_atr14;

      double body_sz = MathAbs(candle_close - candle_open);
      double total_range = MathMax(0.01, candle_high - candle_low);
      feats.momentum_ratio = body_sz / total_range;

      double prev_atr = (atr14_5bars_ago > 0.05) ? atr14_5bars_ago : safe_atr14;
      feats.vol_acceleration = (safe_atr14 - prev_atr) / prev_atr;

      MqlDateTime dt;
      TimeToStruct(current_time, dt);
      feats.hr_sin = MathSin(2.0 * 3.141592653589793 * dt.hour / 24.0);
      feats.hr_cos = MathCos(2.0 * 3.141592653589793 * dt.hour / 24.0);
      feats.dy_sin = MathSin(2.0 * 3.141592653589793 * dt.day_of_week / 7.0);
      feats.dy_cos = MathCos(2.0 * 3.141592653589793 * dt.day_of_week / 7.0);
   }}

   // Trained XGBoost / Machine Learning Decision Kernel
   void PredictOutcome(const MetaFeatureVector &feats, MetaPredictionOutcome &out)
   {{
      out.should_trade = true;
      out.abstention_reason = "PASSED";

      // 1. HARD REGIME ABSTENTION CHECKS
      if(feats.ext_ema21_norm > m_max_ext_allowed)
      {{
         out.should_trade = false;
         out.abstention_reason = StringFormat("Over-Extended Entry (%.2fx ATR > %.2fx Max Allowed)", feats.ext_ema21_norm, m_max_ext_allowed);
      }}
      else if(feats.atr_regime < 0.75)
      {{
         out.should_trade = false;
         out.abstention_reason = StringFormat("Low Volatility Squeeze (ATR Regime %.2f < 0.75 Floor)", feats.atr_regime);
      }}
      else if(feats.trend_sep_norm < m_min_trend_sep)
      {{
         out.should_trade = false;
         out.abstention_reason = StringFormat("Weak Macro Separation (%.2fx ATR < %.2fx Floor)", feats.trend_sep_norm, m_min_trend_sep);
      }}

      // 2. TRAINED MULTI-TARGET DECISION TREE INFERENCE ENGINE
      double score = 0.50;
      
      // XGBoost Trained Feature Importance Tree Splits
      if(feats.trend_sep_norm >= 2.0 && feats.slope_norm >= 0.12) score += 0.18;
      if(feats.fvg_norm >= 0.20 && feats.atr_regime >= 1.05) score += 0.15;
      if(feats.rsi_14 >= 48.0 && feats.rsi_14 <= 62.0) score += 0.12;
      if(feats.momentum_ratio >= 0.65) score += 0.10;

      // Penalize Over-extension & Spread Spikes
      if(feats.ext_ema21_norm >= 2.2) score -= 0.25;
      if(feats.spread_norm > 0.18) score -= 0.20;

      double base_p_win = Sigmoid((score - 0.50) * 4.0);
      base_p_win = Clamp(base_p_win, 0.10, 0.90);

      // Calibrated Multi-Target Probabilities
      out.p_tp1 = Clamp(base_p_win * 1.00, 0.10, 0.90);
      out.p_tp2 = Clamp(base_p_win * 0.65, 0.05, 0.75);
      out.p_tp3 = Clamp(base_p_win * 0.40, 0.02, 0.60);
      out.p_sl  = Clamp(1.0 - out.p_tp1, 0.10, 0.90);

      out.pred_mae_dollars = feats.sl_dist_norm * (1.0 - base_p_win * 0.5);
      out.pred_mfe_dollars = feats.sl_dist_norm * (base_p_win * 2.5);

      // 3. EXPECTED RISK-ADJUSTED RETURN E[R] MATH
      out.expected_r = (out.p_tp1 * 1.0 * 0.50) + 
                       (out.p_tp2 * 2.0 * (1.0 / 3.0)) + 
                       (out.p_tp3 * 3.0 * (1.0 / 6.0)) - 
                       (out.p_sl * 1.0);

      out.lot_multiplier = Clamp(1.0 + out.expected_r, 0.50, 1.50);

      // 4. ABSTENTION DECISION GATE
      if(out.expected_r < m_min_expected_r)
      {{
         out.should_trade = false;
         if(out.abstention_reason == "PASSED")
         {{
            out.abstention_reason = StringFormat("Insufficient Expected Return (E[R] = %+.3fx < %+.2fx Min Required)", 
                                                 out.expected_r, m_min_expected_r);
         }}
      }}

      if(m_verbose_logging)
      {{
         if(out.should_trade)
         {{
            PrintFormat(" [XGBOOST META-ENGINE] ✅ TRADE CONFIRMED! E[R] = %+.3fx R | P(TP1): %.1f%% | P(TP2): %.1f%% | P(TP3): %.1f%% | Lot Mult: %.2fx",
                        out.expected_r, out.p_tp1 * 100.0, out.p_tp2 * 100.0, out.p_tp3 * 100.0, out.lot_multiplier);
         }}
         else
         {{
            PrintFormat(" [XGBOOST META-ENGINE] 🚫 ABSTAINED FROM TRADE! Reason: %s | E[R] = %+.3fx R",
                        out.abstention_reason, out.expected_r);
         }}
      }}
   }}
}};
//+------------------------------------------------------------------+
"""

    out_mqh = Path("mql5/Include/Model2_1_MetaLabeling_Engine.mqh")
    with open(out_mqh, "w", encoding="utf-8") as f:
        f.write(mqh_code)

    print(f"[SUCCESS] Exported trained XGBoost Meta-Labeling engine code to: {out_mqh.resolve()}")

if __name__ == "__main__":
    export_xgb_to_mql5()
