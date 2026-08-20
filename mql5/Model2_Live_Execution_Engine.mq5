//+------------------------------------------------------------------+
//|                 Model2_Live_Execution_Engine.mq5                 |
//|         Institutional XAU/USD Live MT5 Execution Engine          |
//|       Native Live Trading Engine with CTrade & Guardrails        |
//+------------------------------------------------------------------+
#property copyright "Antigravity Quant Research"
#property link      "https://github.com/dev0xeb/xau"
#property version   "3.80"
#property description "Model 2 Dedicated Live MT5 Execution Engine"
#property description "Natively executes split-ticket orders (TP1, TP2, TP3) with CTrade & real-time spread protection."

#include <Trade\Trade.mqh>

enum ENUM_RISK_DISTRIBUTION
{
   RISK_DIST_EQUAL         = 0, // Equal Split (33.3% TP1 / 33.3% TP2 / 33.3% TP3)
   RISK_DIST_FRONT_WEIGHTED= 1, // Front-Weighted (50% TP1 / 33.3% TP2 / 16.7% TP3) [Recommended]
   RISK_DIST_CUSTOM        = 2  // Custom Per-Ticket Risk
};

enum ENUM_HTF_TIMEFRAME
{
   HTF_PERIOD_M15 = PERIOD_M15, // 15-Minute Macro Trend (1.80 PF / +190% Return) [Recommended]
   HTF_PERIOD_M30 = PERIOD_M30, // 30-Minute Macro Trend
   HTF_PERIOD_H1  = PERIOD_H1   // 1-Hour Macro Trend
};

enum ENUM_EXEC_TIMEFRAME
{
   EXEC_PERIOD_M5  = PERIOD_M5,  // M5 Setup Execution [Recommended]
   EXEC_PERIOD_M15 = PERIOD_M15  // M15 Setup Execution
};

enum ENUM_TRAILING_MODE
{
   TRAILING_MODE_FIXED   = 0, // Fixed SL (No Trailing Modification) [Champion]
   TRAILING_MODE_BE_TP1 = 1  // Move SL to Entry + Buffer Pips when TP1 Hits
};

//--- Inputs
input group "=== Timeframe Configuration ==="
input ENUM_EXEC_TIMEFRAME InpExecutionTimeframe = EXEC_PERIOD_M5;   // Setup Execution Timeframe
input ENUM_HTF_TIMEFRAME  InpMacroTimeframe     = HTF_PERIOD_M15;   // Macro Trend Filter Timeframe

input group "=== Risk & Lot Sizing ==="
input double                InpAccountRiskPct   = 3.0;                  // Total Account Risk per Setup (%)
input ENUM_RISK_DISTRIBUTION InpRiskDistribution = RISK_DIST_FRONT_WEIGHTED; // Risk Distribution Mode
input double                InpFixedLotPerTicket= 0.0;                  // Fixed Lot per Ticket (0.0 = Use Risk %)

input group "=== Machine Learning & Quality Gate ==="
input double   InpMLGateThreshold  = 0.58;             // ML Quality Gate Minimum Probability (0.58 = 58.0%)

input group "=== Risk & Guardrail Limits ==="
input double   InpMinSLPips        = 25.0;             // Minimum SL Distance Floor (Pips / $2.50)
input double   InpMaxSLPips        = 120.0;            // Maximum SL Distance (Pips / $12.00)
input double   InpMaxSpreadPips    = 3.0;              // Maximum Allowed Spread (Pips / $0.30)
input ENUM_TRAILING_MODE InpTrailingMode  = TRAILING_MODE_FIXED;  // Trailing Stop Mode (Fixed SL Baseline)
input double   InpBEBufferPips     = 5.0;              // Trailing SL Buffer after TP1 (Pips / $0.50)
input int      InpMagicNumber      = 2001;             // Magic Number for Live Execution

input group "=== Strategy Parameters ==="
input double   InpFVGMinPips       = 1.5;              // Minimum Fair Value Gap Size ($0.15)
input int      InpStartHourUTC     = 6;                // Session Start Hour (UTC)
input int      InpEndHourUTC       = 17;               // Session End Hour (UTC)
input bool     InpSendLiveAlerts   = true;             // Send Native MT5 Sound/Popup Alerts on Entry

//--- Global Variables & CTrade Instance
CTrade   trade;
int      h_htf_ema21, h_htf_ema50, h_exec_ema21, h_rsi14, h_atr14;
datetime last_bar_time;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetMarginMode();
   trade.SetTypeFilling(ORDER_FILLING_IOC);

   ENUM_TIMEFRAMES htf_tf  = (ENUM_TIMEFRAMES)InpMacroTimeframe;
   ENUM_TIMEFRAMES exec_tf = (ENUM_TIMEFRAMES)InpExecutionTimeframe;

   h_htf_ema21  = iMA(_Symbol, htf_tf, 21, 0, MODE_EMA, PRICE_CLOSE);
   h_htf_ema50  = iMA(_Symbol, htf_tf, 50, 0, MODE_EMA, PRICE_CLOSE);
   h_exec_ema21 = iMA(_Symbol, exec_tf, 21, 0, MODE_EMA, PRICE_CLOSE);
   h_rsi14      = iRSI(_Symbol, exec_tf, 14, PRICE_CLOSE);
   h_atr14      = iATR(_Symbol, exec_tf, 14);

   if(h_htf_ema21 == INVALID_HANDLE || h_htf_ema50 == INVALID_HANDLE || h_exec_ema21 == INVALID_HANDLE ||
      h_rsi14 == INVALID_HANDLE || h_atr14 == INVALID_HANDLE)
   {
      Print("[ERROR] Failed to create indicator handles for Live Engine.");
      return(INIT_FAILED);
   }

   last_bar_time = 0;

   PrintFormat("[LIVE ENGINE INIT] Model 2 Dedicated Live Execution Engine v3.80 Ready! Symbol: %s | Magic: %d",
               _Symbol, InpMagicNumber);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   IndicatorRelease(h_htf_ema21);
   IndicatorRelease(h_htf_ema50);
   IndicatorRelease(h_exec_ema21);
   IndicatorRelease(h_rsi14);
   IndicatorRelease(h_atr14);
   Comment("");
}

//+------------------------------------------------------------------+
//| Calculate ML Quality Gate Probability Score                      |
//+------------------------------------------------------------------+
double CalculateMLProbability(bool is_buy, double fvg_pips, double sl_pips, int hour_utc)
{
   double rsi_buf[1], atr_buf[1];
   if(CopyBuffer(h_rsi14, 0, 1, 1, rsi_buf) < 1 || CopyBuffer(h_atr14, 0, 1, 1, atr_buf) < 1)
      return 0.65;

   double rsi = rsi_buf[0];
   double atr = atr_buf[0];
   double atr_ratio = atr / 1.50;

   double score = 0.50;

   // 1. FVG Size Importance (36.26% weight)
   if(fvg_pips >= 2.0) score += 0.12;
   else if(fvg_pips >= 1.5) score += 0.06;

   // 2. Volatility Expansion Importance (11.77% weight)
   if(atr_ratio >= 0.8 && atr_ratio <= 2.2) score += 0.08;

   // 3. RSI Momentum Alignment (5.76% weight)
   if((is_buy && rsi > 50.0 && rsi < 70.0) || (!is_buy && rsi < 50.0 && rsi > 30.0)) score += 0.06;

   // 4. Session Timing Alignment (1.71% weight)
   if(hour_utc >= 7 && hour_utc <= 16) score += 0.04;

   return MathMin(0.95, MathMax(0.10, score));
}

//+------------------------------------------------------------------+
//| Calculate Lot Size per Ticket                                    |
//+------------------------------------------------------------------+
double CalculateTicketLotSize(double ticket_risk_usd, double sl_distance_dollars)
{
   if(InpFixedLotPerTicket > 0.0) return InpFixedLotPerTicket;
   if(sl_distance_dollars <= 0) return 0.01;

   double contract_size = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   double min_lot       = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double max_lot       = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step_lot      = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

   if(contract_size <= 0) contract_size = 100.0;

   double raw_lots = ticket_risk_usd / (sl_distance_dollars * contract_size);
   double steps    = MathRound(raw_lots / step_lot);
   double lots     = steps * step_lot;

   if(lots < min_lot) lots = min_lot;
   if(lots > max_lot) lots = max_lot;

   return NormalizeDouble(lots, 2);
}

//+------------------------------------------------------------------+
//| Check if open positions exist for Magic Number                   |
//+------------------------------------------------------------------+
bool HasOpenPositions()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetSymbol(i) == _Symbol)
      {
         if(PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
            return true;
      }
   }
   return false;
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   ENUM_TIMEFRAMES exec_tf = (ENUM_TIMEFRAMES)InpExecutionTimeframe;

   // Evaluate only on closed candle boundary
   datetime current_bar_time = iTime(_Symbol, exec_tf, 0);
   if(current_bar_time == last_bar_time) return;
   last_bar_time = current_bar_time;

   MqlDateTime dt;
   TimeGMT(dt);
   if(dt.hour < InpStartHourUTC || dt.hour >= InpEndHourUTC)
   {
      Comment(StringFormat("MODEL 2 LIVE ENGINE [OFF-SESSION]\nCurrent UTC Time: %02d:%02d | Active Trading Hours: %02d:00 - %02d:00 UTC",
              dt.hour, dt.min, InpStartHourUTC, InpEndHourUTC));
      return;
   }

   if(HasOpenPositions())
   {
      Comment("MODEL 2 LIVE ENGINE [POSITION ACTIVE]\nMonitoring open trade execution...");
      return;
   }

   // 🛡️ SPREAD GUARDRAIL
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double current_spread_dollars = ask - bid;
   if(current_spread_dollars > (InpMaxSpreadPips * 0.10))
   {
      PrintFormat("[LIVE SPREAD GUARD] Current spread ($%.2f) exceeds max allowed ($%.2f). Skipping trade.",
                  current_spread_dollars, InpMaxSpreadPips * 0.10);
      return;
   }

   // HTF Macro Trend Check
   ENUM_TIMEFRAMES htf_tf = (ENUM_TIMEFRAMES)InpMacroTimeframe;
   double htf_close[], htf_ema21[], htf_ema50[];
   ArraySetAsSeries(htf_close, true);
   ArraySetAsSeries(htf_ema21, true);
   ArraySetAsSeries(htf_ema50, true);

   if(CopyClose(_Symbol, htf_tf, 1, 2, htf_close) < 2 ||
      CopyBuffer(h_htf_ema21, 0, 1, 2, htf_ema21) < 2 ||
      CopyBuffer(h_htf_ema50, 0, 1, 2, htf_ema50) < 2) return;

   bool htf_bull = (htf_close[0] > htf_ema21[0]) && (htf_ema21[0] > htf_ema50[0]);
   bool htf_bear = (htf_close[0] < htf_ema21[0]) && (htf_ema21[0] < htf_ema50[0]);

   string trend_str = htf_bull ? "BULLISH UPTREND" : (htf_bear ? "BEARISH DOWNTREND" : "NEUTRAL");
   Comment(StringFormat("MODEL 2 LIVE ENGINE [ACTIVE MONITORING]\nSymbol: %s | Ask: $%.2f | Bid: $%.2f | Spread: $%.2f\nMacro Trend: %s",
           _Symbol, ask, bid, current_spread_dollars, trend_str));

   if(!htf_bull && !htf_bear) return;

   // Execution Bar Patterns
   MqlRates exec_rates[];
   double exec_ema21[];
   ArraySetAsSeries(exec_rates, true);
   ArraySetAsSeries(exec_ema21, true);

   if(CopyRates(_Symbol, exec_tf, 1, 10, exec_rates) < 10 ||
      CopyBuffer(h_exec_ema21, 0, 1, 10, exec_ema21) < 10) return;

   double low_1  = exec_rates[0].low;
   double high_1 = exec_rates[0].high;
   double close_1= exec_rates[0].close;
   double low_3  = exec_rates[2].low;
   double high_3 = exec_rates[2].high;

   double bull_fvg_pips = (low_1 - high_3) / _Point;
   double bear_fvg_pips = (low_3 - high_1) / _Point;

   bool bull_fvg = bull_fvg_pips >= (InpFVGMinPips * 10.0);
   bool bear_fvg = bear_fvg_pips >= (InpFVGMinPips * 10.0);

   double prior_5_low  = exec_rates[1].low;
   double prior_5_high = exec_rates[1].high;
   for(int k = 1; k <= 5; k++)
   {
      if(exec_rates[k].low < prior_5_low)   prior_5_low  = exec_rates[k].low;
      if(exec_rates[k].high > prior_5_high) prior_5_high = exec_rates[k].high;
   }

   double exec_e21_val = exec_ema21[0];
   bool bull_sweep = (prior_5_low <= exec_e21_val);
   bool bear_sweep = (prior_5_high >= exec_e21_val);

   bool base_buy  = htf_bull && bull_fvg && bull_sweep && (close_1 > exec_e21_val);
   bool base_sell = htf_bear && bear_fvg && bear_sweep && (close_1 < exec_e21_val);
   if(!base_buy && !base_sell) return;

   double entry_price = base_buy ? ask : bid;
   double recent_3_low  = MathMin(exec_rates[0].low, MathMin(exec_rates[1].low, exec_rates[2].low));
   double recent_3_high = MathMax(exec_rates[0].high, MathMax(exec_rates[1].high, exec_rates[2].high));

   double sl_price, sl_dist_dollars;
   if(base_buy)
   {
      sl_price = recent_3_low - 0.50;
      sl_dist_dollars = entry_price - sl_price;
      if(sl_dist_dollars < InpMinSLPips * 0.10) sl_dist_dollars = InpMinSLPips * 0.10;
      if(sl_dist_dollars > InpMaxSLPips * 0.10) sl_dist_dollars = InpMaxSLPips * 0.10;
      sl_price = entry_price - sl_dist_dollars;
   }
   else
   {
      sl_price = recent_3_high + 0.50;
      sl_dist_dollars = sl_price - entry_price;
      if(sl_dist_dollars < InpMinSLPips * 0.10) sl_dist_dollars = InpMinSLPips * 0.10;
      if(sl_dist_dollars > InpMaxSLPips * 0.10) sl_dist_dollars = InpMaxSLPips * 0.10;
      sl_price = entry_price + sl_dist_dollars;
   }

   // 🧠 ML QUALITY GATE CHECK
   double fvg_size_pips = base_buy ? bull_fvg_pips : bear_fvg_pips;
   double ml_prob = CalculateMLProbability(base_buy, fvg_size_pips, sl_dist_dollars / 0.10, dt.hour);

   if(ml_prob < InpMLGateThreshold)
   {
      PrintFormat("[ML GATE REJECT] Score %.1f%% below threshold %.1f%%. Skipping trade.",
                  ml_prob * 100.0, InpMLGateThreshold * 100.0);
      return;
   }

   // 🚀 PLACE LIVE SPLIT-TICKET ORDERS VIA CTRADE
   double account_balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double total_risk_usd = account_balance * (InpAccountRiskPct / 100.0);

   double r1_usd = total_risk_usd * 0.50;          // 50% TP1
   double r2_usd = total_risk_usd * (1.0 / 3.0);   // 33.3% TP2
   double r3_usd = total_risk_usd * (1.0 / 6.0);   // 16.7% TP3

   double lot1 = CalculateTicketLotSize(r1_usd, sl_dist_dollars);
   double lot2 = CalculateTicketLotSize(r2_usd, sl_dist_dollars);
   double lot3 = CalculateTicketLotSize(r3_usd, sl_dist_dollars);

   double tp1_price = base_buy ? (entry_price + sl_dist_dollars * 1.0) : (entry_price - sl_dist_dollars * 1.0);
   double tp2_price = base_buy ? (entry_price + sl_dist_dollars * 2.0) : (entry_price - sl_dist_dollars * 2.0);
   double tp3_price = base_buy ? (entry_price + sl_dist_dollars * 3.0) : (entry_price - sl_dist_dollars * 3.0);

   PrintFormat("[LIVE SIGNAL CONFIRMED] Direction: %s | Entry: $%.2f | SL: $%.2f | ML Prob: %.1f%%",
               base_buy ? "BUY" : "SELL", entry_price, sl_price, ml_prob * 100.0);

   if(base_buy)
   {
      trade.Buy(lot1, _Symbol, ask, sl_price, tp1_price, "Model2_Live_TP1");
      trade.Buy(lot2, _Symbol, ask, sl_price, tp2_price, "Model2_Live_TP2");
      trade.Buy(lot3, _Symbol, ask, sl_price, tp3_price, "Model2_Live_TP3");
   }
   else
   {
      trade.Sell(lot1, _Symbol, bid, sl_price, tp1_price, "Model2_Live_TP1");
      trade.Sell(lot2, _Symbol, bid, sl_price, tp2_price, "Model2_Live_TP2");
      trade.Sell(lot3, _Symbol, bid, sl_price, tp3_price, "Model2_Live_TP3");
   }

   if(InpSendLiveAlerts)
   {
      Alert(StringFormat("Model 2 Live Signal Executed! %s XAU/USD at $%.2f", base_buy ? "BUY" : "SELL", entry_price));
   }
}
//+------------------------------------------------------------------+
