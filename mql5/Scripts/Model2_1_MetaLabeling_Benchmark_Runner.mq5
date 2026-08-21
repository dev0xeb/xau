//+------------------------------------------------------------------+
//|          Model2_1_MetaLabeling_Benchmark_Runner.mq5             |
//|      Standalone MT5 Script to Run & Benchmark Model 2.1          |
//|      Native Meta-Labeling & Multi-Target Risk Engine             |
//+------------------------------------------------------------------+
#property copyright "Antigravity Quant Research"
#property link      "https://github.com/dev0xeb/xau"
#property version   "4.30"
#property script_show_inputs

#include <Model2_1_MetaLabeling_Engine.mqh>

//--- Inputs
input group "=== Model 2.1 Meta-Labeling Benchmark Configuration ==="
input ENUM_TIMEFRAMES InpExecutionTF   = PERIOD_M5;            // Execution Timeframe (Default: M5)
input int             InpBarsToScan    = 100000;               // Bars to Scan in MT5 History (~1 Year)
input double          InpMinExpectedR  = 0.15;                 // Minimum Expected Return E[R] Threshold (+0.15x R:R)
input double          InpMaxExtension  = 3.5;                  // Max Extension from EMA21 (in ATR multiples)

//+------------------------------------------------------------------+
//| Helper Function: Calculate ATR                                   |
//+------------------------------------------------------------------+
double GetATR(int index, const MqlRates &rates[], int period, int total)
{
   if(index + period >= total) return 1.50;
   double tr_sum = 0.0;
   for(int k = index; k < index + period; k++)
   {
      double tr1 = rates[k].high - rates[k].low;
      double tr2 = MathAbs(rates[k].high - rates[k+1].close);
      double tr3 = MathAbs(rates[k].low - rates[k+1].close);
      double tr = MathMax(tr1, MathMax(tr2, tr3));
      tr_sum += tr;
   }
   return tr_sum / (double)period;
}

//+------------------------------------------------------------------+
//| Helper Function: Calculate RSI                                   |
//+------------------------------------------------------------------+
double GetRSI(int index, const MqlRates &rates[], int total)
{
   if(index + 14 >= total) return 50.0;
   double gains = 0.0, losses = 0.0;
   for(int k = index; k < index + 14; k++)
   {
      double diff = rates[k].close - rates[k+1].close;
      if(diff > 0) gains += diff;
      else losses += MathAbs(diff);
   }
   double avg_gain = gains / 14.0;
   double avg_loss = losses / 14.0;
   if(avg_loss == 0.0) return 100.0;
   double rs = avg_gain / avg_loss;
   return 100.0 - (100.0 / (1.0 + rs));
}

//+------------------------------------------------------------------+
//| Main Script OnStart Function                                     |
//+------------------------------------------------------------------+
void OnStart()
{
   Print("=========================================================================================");
   Print(" 🔬 RUNNING MODEL 2.1 META-LABELING & MULTI-TARGET BENCHMARK IN MT5");
   PrintFormat(" Symbol: %s | Timeframe: %s | Bars Requested: %d | Min E[R]: %+.2fx R",
               _Symbol, EnumToString(InpExecutionTF), InpBarsToScan, InpMinExpectedR);
   Print("=========================================================================================");

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int total_bars = CopyRates(_Symbol, InpExecutionTF, 0, InpBarsToScan, rates);

   if(total_bars < 500)
   {
      PrintFormat("[ERROR] Insufficient bars loaded in MT5 history (%d bars).", total_bars);
      return;
   }

   // Copy M15 Data for Macro Trend
   MqlRates m15_rates[];
   ArraySetAsSeries(m15_rates, true);
   int total_m15 = CopyRates(_Symbol, PERIOD_M15, 0, (int)(InpBarsToScan / 3) + 500, m15_rates);

   // Handles
   int h_m15_e21 = iMA(_Symbol, PERIOD_M15, 21, 0, MODE_EMA, PRICE_CLOSE);
   int h_m15_e50 = iMA(_Symbol, PERIOD_M15, 50, 0, MODE_EMA, PRICE_CLOSE);
   int h_m5_e21  = iMA(_Symbol, InpExecutionTF, 21, 0, MODE_EMA, PRICE_CLOSE);

   double m15_e21_buf[], m15_e50_buf[], m5_e21_buf[];
   ArraySetAsSeries(m15_e21_buf, true);
   ArraySetAsSeries(m15_e50_buf, true);
   ArraySetAsSeries(m5_e21_buf, true);

   CopyBuffer(h_m15_e21, 0, 0, total_m15, m15_e21_buf);
   CopyBuffer(h_m15_e50, 0, 0, total_m15, m15_e50_buf);
   CopyBuffer(h_m5_e21, 0, 0, total_bars, m5_e21_buf);

   // Instantiate Native Meta-Labeling Engine
   CModel21MetaLabelingEngine meta_engine;
   meta_engine.SetMinExpectedR(InpMinExpectedR);
   meta_engine.SetMaxExtension(InpMaxExtension);
   meta_engine.SetVerboseLogging(false); // Silent mode for fast backtesting

   int candidates_count = 0;
   int baseline_wins = 0, baseline_losses = 0;

   int meta_approved_count = 0;
   int meta_wins = 0, meta_losses = 0;
   int meta_abstained_count = 0;
   int abstained_losses_saved = 0, abstained_wins_lost = 0;

   double sum_expected_r = 0.0;

   PrintFormat(" Processing %d M5 bars through Model 2.1 Meta-Labeling Engine...", total_bars);

   for(int i = total_bars - 100; i >= 100; i--)
   {
      datetime t = rates[i].time;
      int m15_idx = iBarShift(_Symbol, PERIOD_M15, t, false);
      if(m15_idx < 0 || m15_idx >= total_m15) continue;

      double m15_close = m15_rates[m15_idx].close;
      double m15_e21   = m15_e21_buf[m15_idx];
      double m15_e50   = m15_e50_buf[m15_idx];

      bool m15_bull = (m15_close > m15_e21) && (m15_e21 > m15_e50);
      bool m15_bear = (m15_close < m15_e21) && (m15_e21 < m15_e50);

      if(!m15_bull && !m15_bear) continue;

      // M5 FVG Check
      double low_1  = rates[i].low;
      double high_1 = rates[i].high;
      double close_1= rates[i].close;
      double low_3  = rates[i+2].low;
      double high_3 = rates[i+2].high;

      double bull_fvg_size = low_1 - high_3;
      double bear_fvg_size = low_3 - high_1;

      bool bull_fvg = bull_fvg_size >= 0.15;
      bool bear_fvg = bear_fvg_size >= 0.15;

      // EMA21 Sweep Check
      double prior_5_low  = rates[i+1].low;
      double prior_5_high = rates[i+1].high;
      for(int k = 1; k <= 5; k++)
      {
         if(rates[i+k].low < prior_5_low)   prior_5_low  = rates[i+k].low;
         if(rates[i+k].high > prior_5_high) prior_5_high = rates[i+k].high;
      }

      double m5_e21_val = m5_e21_buf[i];
      bool bull_sweep = (prior_5_low <= m5_e21_val);
      bool bear_sweep = (prior_5_high >= m5_e21_val);

      bool is_buy  = m15_bull && bull_fvg && bull_sweep && (close_1 > m5_e21_val);
      bool is_sell = m15_bear && bear_fvg && bear_sweep && (close_1 < m5_e21_val);

      if(!is_buy && !is_sell) continue;

      candidates_count++;

      // Entry Setup
      int entry_idx = i - 1;
      datetime entry_time = rates[entry_idx].time;
      double entry_price = rates[entry_idx].open;

      // Structural SL
      double sl_price, sl_dist_dollars;
      if(is_buy)
      {
         double recent_3_low = MathMin(rates[i].low, MathMin(rates[i+1].low, rates[i+2].low));
         sl_price = recent_3_low - 0.50;
         sl_dist_dollars = entry_price - sl_price;
         if(sl_dist_dollars < 2.50) sl_dist_dollars = 2.50;
         if(sl_dist_dollars > 12.00) sl_dist_dollars = 12.00;
         sl_price = entry_price - sl_dist_dollars;
      }
      else
      {
         double recent_3_high = MathMax(rates[i].high, MathMax(rates[i+1].high, rates[i+2].high));
         sl_price = recent_3_high + 0.50;
         sl_dist_dollars = sl_price - entry_price;
         if(sl_dist_dollars < 2.50) sl_dist_dollars = 2.50;
         if(sl_dist_dollars > 12.00) sl_dist_dollars = 12.00;
         sl_price = entry_price + sl_dist_dollars;
      }

      double tp1_price = is_buy ? (entry_price + sl_dist_dollars * 1.0) : (entry_price - sl_dist_dollars * 1.0);

      // Bar-by-bar Forward Simulation
      bool hit_sl = false, hit_tp1 = false;
      for(int f = entry_idx; f >= MathMax(0, entry_idx - 120); f--)
      {
         double b_high = rates[f].high;
         double b_low  = rates[f].low;

         if(is_buy)
         {
            if(b_low <= sl_price) { hit_sl = true; break; }
            if(b_high >= tp1_price) { hit_tp1 = true; break; }
         }
         else
         {
            if(b_high >= sl_price) { hit_sl = true; break; }
            if(b_low <= tp1_price) { hit_tp1 = true; break; }
         }
      }

      bool trade_won = hit_tp1 && !hit_sl;
      if(trade_won) baseline_wins++;
      else baseline_losses++;

      // --- RUN NATIVE MQL5 META-LABELING INFERENCE ---
      double fvg_dollars      = is_buy ? bull_fvg_size : bear_fvg_size;
      double impulse_sz       = (rates[i+1].high - rates[i+1].low);
      double ema21_slope      = is_buy ? (m5_e21_buf[i] - m5_e21_buf[i+3]) : (m5_e21_buf[i+3] - m5_e21_buf[i]);
      double trend_sep        = MathAbs(m15_e21 - m15_e50);
      double trend_dist       = MathAbs(m15_close - m15_e50);
      double ext_ema21        = MathAbs(entry_price - m5_e21_val);
      double atr14_val        = GetATR(i, rates, 14, total_bars);
      double atr50_val        = GetATR(i, rates, 50, total_bars);
      double atr14_prev       = GetATR(i+5, rates, 14, total_bars);
      double rsi14_val        = GetRSI(i, rates, total_bars);

      MetaFeatureVector feats;
      meta_engine.ExtractFeatures(_Symbol, InpExecutionTF, is_buy, entry_price, sl_dist_dollars,
                                 fvg_dollars, impulse_sz, ema21_slope, trend_sep, trend_dist,
                                 ext_ema21, atr14_val, atr50_val, atr14_prev, rsi14_val,
                                 rates[i].open, rates[i].close, rates[i].high, rates[i].low,
                                 entry_time, 0.15, feats);

      MetaPredictionOutcome pred;
      meta_engine.PredictOutcome(feats, pred);

      sum_expected_r += pred.expected_r;

      if(pred.should_trade)
      {
         meta_approved_count++;
         if(trade_won) meta_wins++;
         else meta_losses++;
      }
      else
      {
         meta_abstained_count++;
         if(!trade_won) abstained_losses_saved++;
         else abstained_wins_lost++;
      }
   }

   double base_wr = (candidates_count > 0) ? ((double)baseline_wins / candidates_count) * 100.0 : 0.0;
   double meta_wr = (meta_approved_count > 0) ? ((double)meta_wins / meta_approved_count) * 100.0 : 0.0;
   double avg_expected_r = (candidates_count > 0) ? (sum_expected_r / candidates_count) : 0.0;

   Print("-----------------------------------------------------------------------------------------");
   Print(" 🏆 MODEL 2.1 META-LABELING NATIVE MQL5 BENCHMARK RESULTS:");
   Print("-----------------------------------------------------------------------------------------");
   PrintFormat(" Total Candidate Setups Generated  : %d Candidates", candidates_count);
   PrintFormat(" Baseline Strategy Win Rate        : %.1f%% (%d Wins / %d Losses)", base_wr, baseline_wins, baseline_losses);
   Print("-----------------------------------------------------------------------------------------");
   PrintFormat(" 🧠 META-LABELING APPROVED TRADES   : %d Trades (%.1f%% Approved)", meta_approved_count, (candidates_count > 0) ? ((double)meta_approved_count/candidates_count)*100.0 : 0.0);
   PrintFormat(" 🟢 META-LABELING APPROVED WIN RATE : %.1f%% (%d Wins / %d Losses)", meta_wr, meta_wins, meta_losses);
   PrintFormat(" 📈 WIN RATE IMPROVEMENT            : %+.1f%% Win Rate Increase!", meta_wr - base_wr);
   Print("-----------------------------------------------------------------------------------------");
   PrintFormat(" 🚫 ABSTENTION ENGINE EFFICIENCY    : %d Trades Blocked", meta_abstained_count);
   PrintFormat("   - Toxic Losses Saved             : %d Losses Eliminated! (%.1f%% of All Losses)", abstained_losses_saved, (baseline_losses > 0) ? ((double)abstained_losses_saved/baseline_losses)*100.0 : 0.0);
   PrintFormat("   - Wins Sacrificed                : %d Wins", abstained_wins_lost);
   PrintFormat("   - Loss-to-Win Removal Ratio      : %.2fx (Eliminated %.1fx more losses than wins!)",
               (abstained_wins_lost > 0) ? (((double)abstained_losses_saved/baseline_losses) / ((double)abstained_wins_lost/baseline_wins)) : 99.9);
   Print("-----------------------------------------------------------------------------------------");
   PrintFormat(" 📊 AVERAGE EXPECTED RETURN E[R]     : %+.3fx Risk-Adjusted R:R per Setup", avg_expected_r);
   Print("=========================================================================================");

   IndicatorRelease(h_m15_e21);
   IndicatorRelease(h_m15_e50);
   IndicatorRelease(h_m5_e21);
}
//+------------------------------------------------------------------+
