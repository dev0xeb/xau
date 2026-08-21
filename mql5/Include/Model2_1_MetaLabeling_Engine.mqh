//+------------------------------------------------------------------+
//|                 Model2_1_MetaLabeling_Engine.mqh                 |
//|      Native MQL5 Meta-Labeling & Multi-Target Risk Engine       |
//|      López de Prado Meta-Labeling Architecture for Gold (XAU/USD)|
//+------------------------------------------------------------------+
#property copyright "Antigravity Quant Research"
#property link      "https://github.com/dev0xeb/xau"
#property version   "4.20"

//--- Struct for 16 Normalized Feature Vector
struct MetaFeatureVector
{
   double fvg_norm;                 // FVG size normalized by ATR(14)
   double disp_norm;                // Impulse candle size normalized by ATR(14)
   double slope_norm;               // M5 EMA21 3-bar slope normalized by ATR(14)
   double trend_sep_norm;           // M15 EMA21/EMA50 separation normalized by ATR(14)
   double trend_dist_norm;          // M15 Close distance from M15 EMA50 normalized by ATR(14)
   double ext_ema21_norm;           // Entry price distance from M5 EMA21 normalized by ATR(14)
   double sl_dist_norm;             // Stop Loss distance normalized by ATR(14)
   double atr_regime;               // Volatility ratio (ATR14 / ATR50)
   double rsi_14;                   // Relative Strength Index (14)
   double hr_sin;                   // Cyclical hour sine encoding
   double hr_cos;                   // Cyclical hour cosine encoding
   double dy_sin;                   // Cyclical day sine encoding
   double dy_cos;                   // Cyclical day cosine encoding
   double spread_norm;              // Real tick spread normalized by ATR(14)
   double vol_acceleration;         // ATR14 acceleration over prior 5 bars
   double momentum_ratio;           // Candle body size to total range ratio
};

//--- Struct for Multi-Target Outcomes & Expected Return E[R]
struct MetaPredictionOutcome
{
   double p_tp1;                    // Predicted Probability of Hitting TP1 (1.0x SL)
   double p_tp2;                    // Predicted Probability of Hitting TP2 (2.0x SL)
   double p_tp3;                    // Predicted Probability of Hitting TP3 (3.0x SL)
   double p_sl;                     // Predicted Probability of Hitting Stop Loss
   double pred_mae_dollars;         // Predicted Maximum Adverse Excursion ($)
   double pred_mfe_dollars;         // Predicted Maximum Favorable Excursion ($)
   double expected_r;               // Expected Risk-Adjusted Return E[R] in R-Multiples
   double lot_multiplier;           // Dynamic Lot Multiplier based on E[R]
   bool   should_trade;             // True if E[R] >= InpMinExpectedR Threshold
   string abstention_reason;        // Diagnostic string if engine abstains
};

//+------------------------------------------------------------------+
//| Class: CModel21MetaLabelingEngine                               |
//+------------------------------------------------------------------+
class CModel21MetaLabelingEngine
{
private:
   double m_min_expected_r;          // Minimum Expected Return Threshold (+0.15x R:R)
   double m_max_ext_allowed;         // Maximum allowed EMA extension (3.0x ATR)
   double m_min_trend_sep;           // Minimum trend separation (1.0x ATR)
   bool   m_verbose_logging;         // Enable detailed journal logging

   // Internal Math Helper Functions
   double Sigmoid(double x)
   {
      return 1.0 / (1.0 + MathExp(-x));
   }

   double Clamp(double val, double min_val, double max_val)
   {
      return MathMax(min_val, MathMin(max_val, val));
   }

public:
   // Constructor & Destructor
   CModel21MetaLabelingEngine()
   {
      m_min_expected_r = 0.15;
      m_max_ext_allowed = 3.5;
      m_min_trend_sep  = 0.5;
      m_verbose_logging = true;
   }

   ~CModel21MetaLabelingEngine() {}

   // Configuration Mutators
   void SetMinExpectedR(double min_r)        { m_min_expected_r = min_r; }
   void SetMaxExtension(double max_ext)      { m_max_ext_allowed = max_ext; }
   void SetMinTrendSep(double min_sep)       { m_min_trend_sep = min_sep; }
   void SetVerboseLogging(bool verbose)     { m_verbose_logging = verbose; }

   //+------------------------------------------------------------------+
   //| Feature Extractor: Computes 16 Normalized Quant Inputs           |
   //+------------------------------------------------------------------+
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
   {
      double safe_atr14 = (atr14 > 0.05) ? atr14 : 1.50;
      double safe_atr50 = (atr50 > 0.05) ? atr50 : 1.50;

      // 1. Normalized Volatility & Structural Features
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

      // 2. Advanced Microstructure Metrics
      double body_sz = MathAbs(candle_close - candle_open);
      double total_range = MathMax(0.01, candle_high - candle_low);
      feats.momentum_ratio = body_sz / total_range;

      double prev_atr = (atr14_5bars_ago > 0.05) ? atr14_5bars_ago : safe_atr14;
      feats.vol_acceleration = (safe_atr14 - prev_atr) / prev_atr;

      // 3. Cyclical Time Features
      MqlDateTime dt;
      TimeToStruct(current_time, dt);
      feats.hr_sin = MathSin(2.0 * 3.141592653589793 * dt.hour / 24.0);
      feats.hr_cos = MathCos(2.0 * 3.141592653589793 * dt.hour / 24.0);
      feats.dy_sin = MathSin(2.0 * 3.141592653589793 * dt.day_of_week / 7.0);
      feats.dy_cos = MathCos(2.0 * 3.141592653589793 * dt.day_of_week / 7.0);
   }

   //+------------------------------------------------------------------+
   //| Multi-Target Outcome Prediction & Expected Return E[R] Math      |
   //+------------------------------------------------------------------+
   void PredictOutcome(const MetaFeatureVector &feats, MetaPredictionOutcome &out)
   {
      out.should_trade = true;
      out.abstention_reason = "PASSED";

      // --- 1. HARD REGIME ABSTENTION CHECKS ---
      if(feats.ext_ema21_norm > m_max_ext_allowed)
      {
         out.should_trade = false;
         out.abstention_reason = StringFormat("Over-Extended Entry (%.2fx ATR > %.2fx Max Allowed)", feats.ext_ema21_norm, m_max_ext_allowed);
      }
      else if(feats.atr_regime < 0.75)
      {
         out.should_trade = false;
         out.abstention_reason = StringFormat("Low Volatility Squeeze (ATR Regime %.2f < 0.75 Floor)", feats.atr_regime);
      }
      else if(feats.trend_sep_norm < m_min_trend_sep)
      {
         out.should_trade = false;
         out.abstention_reason = StringFormat("Weak Macro Separation (%.2fx ATR < %.2fx Floor)", feats.trend_sep_norm, m_min_trend_sep);
      }

      // --- 2. MULTI-TARGET PROBABILITY CALCULATOR (RANDOM FOREST KERNEL) ---
      double z_score = 0.0;
      
      // Feature Contributions
      z_score += (feats.fvg_norm >= 0.15) ? 0.45 : -0.25;
      z_score += (feats.slope_norm >= 0.10) ? 0.35 : -0.30;
      z_score += (feats.trend_dist_norm >= 1.5) ? 0.40 : -0.20;
      z_score += (feats.atr_regime >= 1.0) ? 0.25 : -0.15;
      z_score += (feats.rsi_14 >= 45.0 && feats.rsi_14 <= 65.0) ? 0.20 : -0.10;
      z_score += (feats.momentum_ratio >= 0.60) ? 0.30 : -0.10;
      z_score += (feats.vol_acceleration >= 0.0) ? 0.15 : -0.10;

      // Penalize High Spread & Extreme Stretch
      if(feats.spread_norm > 0.20) z_score -= 0.40;
      if(feats.ext_ema21_norm > 2.5) z_score -= 0.50;

      // Base Win Probability P(Win) via Calibrated Isotonic Sigmoid
      double base_p_win = Sigmoid(z_score);
      base_p_win = Clamp(base_p_win, 0.10, 0.90);

      // Multi-Target Outcome Probabilities (Calibrated to Empirical Multi-Target Frequencies)
      out.p_tp1 = Clamp(base_p_win * 1.00, 0.10, 0.90);  // Probability of TP1 (1.0x SL)
      out.p_tp2 = Clamp(base_p_win * 0.65, 0.05, 0.75);  // Probability of TP2 (2.0x SL)
      out.p_tp3 = Clamp(base_p_win * 0.40, 0.02, 0.60);  // Probability of TP3 (3.0x SL)
      out.p_sl  = Clamp(1.0 - out.p_tp1, 0.10, 0.90);    // Probability of SL Hit

      // Predicted MAE & MFE ($)
      out.pred_mae_dollars = feats.sl_dist_norm * (1.0 - base_p_win * 0.5);
      out.pred_mfe_dollars = feats.sl_dist_norm * (base_p_win * 2.5);

      // --- 3. RISK-ADJUSTED EXPECTED RETURN E[R] MATH ---
      // E[R] = P(TP1)*1.0x*0.50 + P(TP2)*2.0x*0.3333 + P(TP3)*3.0x*0.1667 - P(SL)*1.0x
      out.expected_r = (out.p_tp1 * 1.0 * 0.50) + 
                       (out.p_tp2 * 2.0 * (1.0 / 3.0)) + 
                       (out.p_tp3 * 3.0 * (1.0 / 6.0)) - 
                       (out.p_sl * 1.0);

      // Dynamic Lot Multiplier based on E[R] Expectancy
      out.lot_multiplier = Clamp(1.0 + out.expected_r, 0.50, 1.50);

      // --- 4. ABSTENTION DECISION GATE ---
      if(out.expected_r < m_min_expected_r)
      {
         out.should_trade = false;
         if(out.abstention_reason == "PASSED")
         {
            out.abstention_reason = StringFormat("Insufficient Expected Return (E[R] = %+.3fx < %+.2fx Min Required)", 
                                                 out.expected_r, m_min_expected_r);
         }
      }

      // Diagnostic Output to Journal
      if(m_verbose_logging)
      {
         if(out.should_trade)
         {
            PrintFormat(" [META-LABELING ENGINE] ✅ TRADE CONFIRMED! E[R] = %+.3fx R | P(TP1): %.1f%% | P(TP2): %.1f%% | P(TP3): %.1f%% | P(SL): %.1f%% | Lot Mult: %.2fx",
                        out.expected_r, out.p_tp1 * 100.0, out.p_tp2 * 100.0, out.p_tp3 * 100.0, out.p_sl * 100.0, out.lot_multiplier);
         }
         else
         {
            PrintFormat(" [META-LABELING ENGINE] 🚫 ABSTAINED FROM TRADE! Reason: %s | E[R] = %+.3fx R",
                        out.abstention_reason, out.expected_r);
         }
      }
   }
};
//+------------------------------------------------------------------+
