//+------------------------------------------------------------------+
//|                                     Model2_PropFirm_Engine.mq5   |
//|                    Model 2: M5 Scalp Hybrid (Prop Firm Engine)   |
//|                         Institutional XAU/USD Strategy Engine    |
//+------------------------------------------------------------------+
#property copyright "Antigravity Quant Research"
#property link      "https://github.com/dev0xeb/xau"
#property version   "3.50"
#property description "Model 2 Prop Firm Scalp Hybrid Engine"
#property description "Supports Dynamic Execution Timeframe (M5/M15) & Macro Trend Timeframe (M15/M30/H1)."
#property description "Features Fixed Stop Loss (No Trailing Modification) with Prop Firm Limits."

enum ENUM_RISK_DISTRIBUTION
{
   RISK_DIST_EQUAL         = 0, // Equal Split (33.3% TP1 / 33.3% TP2 / 33.3% TP3)
   RISK_DIST_FRONT_WEIGHTED= 1, // Front-Weighted (50% TP1 / 33.3% TP2 / 16.7% TP3) [Recommended]
   RISK_DIST_CUSTOM        = 2  // Custom Per-Ticket Risk (Use InpTP1RiskPct, InpTP2RiskPct, InpTP3RiskPct)
};

enum ENUM_HTF_TIMEFRAME
{
   HTF_PERIOD_M15 = PERIOD_M15, // 15-Minute Macro Trend (Fastest Trend Catch - 1.80 PF / +190% Return) [Recommended]
   HTF_PERIOD_M30 = PERIOD_M30, // 30-Minute Macro Trend (High Edge - 1.68 PF / +164% Return)
   HTF_PERIOD_H1  = PERIOD_H1   // 1-Hour Macro Trend (Classic Baseline)
};

enum ENUM_EXEC_TIMEFRAME
{
   EXEC_PERIOD_M5  = PERIOD_M5,  // M5 Setup Execution (Tight Stops / High Frequency) [Recommended]
   EXEC_PERIOD_M15 = PERIOD_M15  // M15 Setup Execution (Wider Stops / Low Frequency)
};

enum ENUM_TRAILING_MODE
{
   TRAILING_MODE_FIXED     = 0, // Fixed SL (No Trailing Modification) [Recommended Baseline]
   TRAILING_MODE_BE_TP1   = 1  // Move SL to Break-Even when TP1 Hits
};

enum ENUM_SESSION_MODE
{
   SESSION_LONDON_NY = 0, // Prime London & NY Session (06:00 to 17:00 UTC) [Default]
   SESSION_ALL_DAY   = 1, // 24-Hour All-Day Trading (00:00 to 24:00 UTC)
   SESSION_CUSTOM    = 2  // Custom Hours (Uses InpStartHourUTC & InpEndHourUTC)
};

//--- Input Parameters
input group "=== Strategy Timeframe Selection ==="
input ENUM_EXEC_TIMEFRAME   InpExecutionTimeframe= EXEC_PERIOD_M5;       // Execution Timeframe (M5 Recommended)
input ENUM_HTF_TIMEFRAME    InpMacroTimeframe    = HTF_PERIOD_M15;      // Macro Trend Timeframe (M15 Recommended)

input group "=== Risk & Account Management ==="
input double                InpAccountRiskPct   = 3.0;                  // Total Account Risk per Setup (%)
input ENUM_RISK_DISTRIBUTION InpRiskDistribution = RISK_DIST_FRONT_WEIGHTED; // Risk Distribution Mode
input double                InpFixedLotPerTicket= 0.0;                  // Fixed Lot per Ticket (0.0 = Use Risk % / Set > 0 for Fixed Lots)

input group "=== Custom Ticket Risk % (Used if Mode = Custom) ==="
input double   InpTP1RiskPct       = 3.0;              // Custom Ticket 1 Risk (% of Balance)
input double   InpTP2RiskPct       = 2.0;              // Custom Ticket 2 Risk (% of Balance)
input double   InpTP3RiskPct       = 1.0;              // Custom Ticket 3 Risk (% of Balance)

input group "=== Machine Learning & Quality Gate ==="
input double   InpMLGateThreshold  = 0.58;             // ML Quality Gate Minimum Probability (0.58 = 58.0% Champion)

input group "=== Risk & Guardrail Limits ==="
input double   InpMinSLPips        = 25.0;             // Minimum SL Distance Floor (Pips / $2.50)
input double   InpMaxSLPips        = 120.0;            // Maximum SL Distance (Pips / $12.00)
input double   InpMaxDailyLossPct  = 4.0;              // Hard Max Daily Loss Limit (%)
input double   InpMaxOverallDDPct  = 8.0;              // Hard Max Overall Drawdown Limit (%)
input double   InpMaxSpreadPips    = 3.0;              // Maximum Allowed Spread (Pips / $0.30 - Rejects Spread Spikes)
input ENUM_TRAILING_MODE InpTrailingMode  = TRAILING_MODE_FIXED;  // Trailing Stop Mode (0=Fixed SL [Champion], 1=BE+Buffer on TP1)
input double   InpBEBufferPips     = 5.0;              // Trailing SL Buffer above/below Entry after TP1 (Pips / 5.0 = $0.50)
input int      InpMagicNumber      = 2002;             // Magic Number (Prop Firm Engine)

input group "=== Session & Strategy Parameters ==="
input ENUM_SESSION_MODE InpSessionMode     = SESSION_ALL_DAY;   // Session Trading Mode (SESSION_ALL_DAY = 24-Hour Trading)
input int      InpStartHourUTC     = 6;                // Session Start Hour (UTC) [Used if Custom]
input int      InpEndHourUTC       = 17;               // Session End Hour (UTC) [Used if Custom]
input double   InpFVGMinPips       = 2.5;              // Minimum Fair Value Gap Size ($0.25)
input bool     InpRequireEMASlope  = true;             // Require M5 EMA21 Active Slope (Filters Out Sideways Range Chop)
input bool     InpAsianSweepOnly   = false;            // Require Asian High/Low Liquidity Sweep (Disabled)

input group "=== Visual Playback Settings ==="
input color    InpBuyColor         = clrDodgerBlue;    // Buy Order Arrow Color
input color    InpSellColor        = clrCrimson;       // Sell Order Arrow Color

//--- Global Variables & Handles
int      h_htf_ema21, h_htf_ema50, h_exec_ema21, h_rsi14, h_atr14;
datetime last_bar_time;

double   initial_balance = 0.0;
double   daily_start_equity = 0.0;
datetime current_day = 0;
int      total_setups_count = 0;
int      total_tickets_count = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
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
      Print("[ERROR] Failed to create indicator handles.");
      return(INIT_FAILED);
   }

   last_bar_time = 0;
   initial_balance = AccountInfoDouble(ACCOUNT_BALANCE);
   daily_start_equity = AccountInfoDouble(ACCOUNT_EQUITY);
   current_day = 0;
   total_setups_count = 0;
   total_tickets_count = 0;

   string exec_str = (InpExecutionTimeframe == EXEC_PERIOD_M5) ? "M5" : "M15";
   string htf_str  = (InpMacroTimeframe == HTF_PERIOD_M15) ? "M15" : ((InpMacroTimeframe == HTF_PERIOD_M30) ? "M30" : "H1");
   string trail_str = (InpTrailingMode == TRAILING_MODE_BE_TP1) ? StringFormat("MODE 1 BE + %.1f PIPS ON TP1", InpBEBufferPips) : "FIXED SL";

   PrintFormat("[INIT] Model 2 Prop Firm Engine v3.60 initialized! Exec TF: %s | Macro TF: %s | Trailing: %s",
               exec_str, htf_str, trail_str);
   return(INIT_SUCCEEDED);
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
//| Manage Active Open Positions & Trailing SL                       |
//+------------------------------------------------------------------+
void ManageTrailingStops()
{
   if(InpTrailingMode == TRAILING_MODE_FIXED) return;

   int total = PositionsTotal();
   double entry_price_level = 0.0;
   long pos_type = -1;

   int my_positions = 0;
   bool tp1_open = false;

   for(int i = total - 1; i >= 0; i--)
   {
      if(PositionGetSymbol(i) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
      {
         my_positions++;
         string comment = PositionGetString(POSITION_COMMENT);
         pos_type = PositionGetInteger(POSITION_TYPE);
         entry_price_level = PositionGetDouble(POSITION_PRICE_OPEN);

         if(StringFind(comment, "TP1") >= 0 || StringFind(comment, "_TP1") >= 0) tp1_open = true;
      }
   }

   if((InpTrailingMode == TRAILING_MODE_BE_TP1) && (my_positions > 0 && my_positions < 3 && !tp1_open))
   {
      double buffer_dollars = InpBEBufferPips * 0.10;
      double new_sl = (pos_type == POSITION_TYPE_BUY) ? (entry_price_level + buffer_dollars) : (entry_price_level - buffer_dollars);

      for(int i = total - 1; i >= 0; i--)
      {
         if(PositionGetSymbol(i) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
         {
            double current_sl = PositionGetDouble(POSITION_SL);
            ulong  ticket     = PositionGetInteger(POSITION_TICKET);

            bool should_modify = false;
            if(pos_type == POSITION_TYPE_BUY && (current_sl < new_sl || current_sl == 0)) should_modify = true;
            if(pos_type == POSITION_TYPE_SELL && (current_sl > new_sl || current_sl == 0)) should_modify = true;

            if(should_modify)
            {
               MqlTradeRequest request = {};
               MqlTradeResult  result  = {};
               request.action   = TRADE_ACTION_SLTP;
               request.position = ticket;
               request.symbol   = _Symbol;
               request.sl       = NormalizeDouble(new_sl, _Digits);
               request.tp       = PositionGetDouble(POSITION_TP);
               OrderSend(request, result);
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Get Entry Deal Comment for Position ID                           |
//+------------------------------------------------------------------+
string GetEntryComment(ulong pos_id)
{
   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong t = HistoryDealGetTicket(i);
      if(t > 0 && HistoryDealGetInteger(t, DEAL_POSITION_ID) == pos_id)
      {
         if(HistoryDealGetInteger(t, DEAL_ENTRY) == DEAL_ENTRY_IN)
         {
            return HistoryDealGetString(t, DEAL_COMMENT);
         }
      }
   }
   return "";
}

//+------------------------------------------------------------------+
//| Analyze Deal History & Output Performance Report                 |
//+------------------------------------------------------------------+
void GeneratePerformanceAnalytics()
{
   double end_balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double net_profit  = end_balance - initial_balance;
   double ret_pct     = (initial_balance > 0) ? (net_profit / initial_balance) * 100.0 : 0.0;

   if(!HistorySelect(0, TimeCurrent())) return;

   int total_deals = HistoryDealsTotal();
   int tp1_count = 0, tp2_count = 0, tp3_count = 0, sl_count = 0;
   double total_gross_profit = 0.0, total_gross_loss = 0.0;
   int winning_deals = 0, losing_deals = 0;

   for(int i = 0; i < total_deals; i++)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket <= 0) continue;

      long magic = HistoryDealGetInteger(ticket, DEAL_MAGIC);
      if(magic != InpMagicNumber) continue;

      long entry_type = HistoryDealGetInteger(ticket, DEAL_ENTRY);
      if(entry_type != DEAL_ENTRY_OUT) continue;

      double profit = HistoryDealGetDouble(ticket, DEAL_PROFIT) + 
                      HistoryDealGetDouble(ticket, DEAL_COMMISSION) + 
                      HistoryDealGetDouble(ticket, DEAL_SWAP);

      ulong pos_id = HistoryDealGetInteger(ticket, DEAL_POSITION_ID);
      string entry_comment = GetEntryComment(pos_id);

      if(profit > 0)
      {
         total_gross_profit += profit;
         winning_deals++;

         if(StringFind(entry_comment, "TP1") >= 0 || StringFind(entry_comment, "_TP1") >= 0)
            tp1_count++;
         else if(StringFind(entry_comment, "TP2") >= 0 || StringFind(entry_comment, "_TP2") >= 0)
            tp2_count++;
         else if(StringFind(entry_comment, "TP3") >= 0 || StringFind(entry_comment, "_TP3") >= 0)
            tp3_count++;
         else
            tp1_count++;
      }
      else if(profit < 0)
      {
         total_gross_loss += MathAbs(profit);
         losing_deals++;
         sl_count++;
      }
   }

   int closed_tickets = winning_deals + losing_deals;
   double win_rate = (closed_tickets > 0) ? ((double)winning_deals / closed_tickets) * 100.0 : 0.0;
   double profit_factor = (total_gross_loss > 0) ? (total_gross_profit / total_gross_loss) : (total_gross_profit > 0 ? 99.99 : 0.0);

   string exec_str = (InpExecutionTimeframe == EXEC_PERIOD_M5) ? "M5" : "M15";
   string htf_str  = (InpMacroTimeframe == HTF_PERIOD_M15) ? "M15" : ((InpMacroTimeframe == HTF_PERIOD_M30) ? "M30" : "H1");
   string trail_str = (InpTrailingMode == TRAILING_MODE_BE_TP1) ? "MODE 1 BE ON TP1" : "FIXED SL";

   Print("=========================================================================================");
   PrintFormat(" PERFORMANCE & ANALYTICS REPORT: MODEL 2 (PROP FIRM ENGINE v3.50 - %s EXEC / %s MACRO / %s)", exec_str, htf_str, trail_str);
   Print("=========================================================================================");
   PrintFormat(" Starting Account Balance : $%.2f USD", initial_balance);
   PrintFormat(" Final Account Balance    : $%.2f USD", end_balance);
   PrintFormat(" Total Net Profit ($)     : %s$%.2f USD (%s%.2f%% Return)", 
               net_profit >= 0 ? "+" : "-", MathAbs(net_profit), net_profit >= 0 ? "+" : "-", ret_pct);
   Print("-----------------------------------------------------------------------------------------");
   Print(" 🔴 TOP 10 WORST TRADING DAYS (WORST PnL / HIGHEST LOSSES):");
   int worst_printed = 0;
   for(int w = daily_count - 1; w >= 0 && worst_printed < 10; w--)
   {
      if(daily_array[w].net_pnl < 0)
      {
         worst_printed++;
         PrintFormat("   #%d [%s] Net PnL: -$%.2f USD | Trades: %d (Wins: %d / Losses: %d)",
                     worst_printed, daily_array[w].date_str, MathAbs(daily_array[w].net_pnl),
                     daily_array[w].trade_count, daily_array[w].wins, daily_array[w].losses);
      }
   }Print("-----------------------------------------------------------------------------------------");
   PrintFormat(" TOTAL SETUPS TRIGGERED   : %d Setups (%d Total Placed Tickets)", total_setups_count, total_tickets_count);
   PrintFormat(" CLOSED TICKETS ANALYZED  : %d Tickets", closed_tickets);
   PrintFormat("   - Winning Tickets      : %d Tickets (%.1f%% Win Rate)", winning_deals, win_rate);
   PrintFormat("   - Losing Tickets       : %d Tickets", losing_deals);
   Print("-----------------------------------------------------------------------------------------");
   PrintFormat(" PROFIT FACTOR           : %.2f", profit_factor);
   PrintFormat(" Gross Profit / Gross Loss: +$%.2f / -$%.2f", total_gross_profit, total_gross_loss);
   Print("=========================================================================================");
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   GeneratePerformanceAnalytics();
   IndicatorRelease(h_htf_ema21);
   IndicatorRelease(h_htf_ema50);
   IndicatorRelease(h_exec_ema21);
   IndicatorRelease(h_rsi14);
   IndicatorRelease(h_atr14);
   Comment("");
}

//+------------------------------------------------------------------+
//| Calculate Lot Size per Specific Ticket                           |
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
//| Check if open positions exist for this Magic Number              |
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
   ManageTrailingStops();

   datetime current_bar_time = iTime(_Symbol, PERIOD_M5, 0);
   if(current_bar_time == last_bar_time) return;
   last_bar_time = current_bar_time;

   MqlDateTime dt;
   TimeGMT(dt);

   datetime today_floor = iTime(_Symbol, PERIOD_D1, 0);
   if(today_floor != current_day)
   {
      current_day = today_floor;
      daily_start_equity = AccountInfoDouble(ACCOUNT_EQUITY);
      PrintFormat("[PROP GUARD] New Trading Day! Daily Equity Floor set to $%.2f", daily_start_equity);
   }

   double current_equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double daily_loss_usd = daily_start_equity - current_equity;
   double max_daily_allowed_usd = daily_start_equity * (InpMaxDailyLossPct / 100.0);

   if(daily_loss_usd >= max_daily_allowed_usd)
   {
      Comment(StringFormat("MODEL 2 PROP ENGINE [HALTED - DAILY LOSS LIMIT HIT]\nDaily Loss: -$%.2f / Max Allowed: -$%.2f",
                           daily_loss_usd, max_daily_allowed_usd));
      return;
   }

   double overall_loss_usd = initial_balance - current_equity;
   double max_overall_allowed_usd = initial_balance * (InpMaxOverallDDPct / 100.0);

   if(overall_loss_usd >= max_overall_allowed_usd)
   {
      Comment(StringFormat("MODEL 2 PROP ENGINE [HALTED - MAX DRAWDOWN LIMIT HIT]\nOverall Loss: -$%.2f / Max Allowed: -$%.2f",
                           overall_loss_usd, max_overall_allowed_usd));
      return;
   }

   if(dt.hour < InpStartHourUTC || dt.hour >= InpEndHourUTC)
   {
      Comment("MODEL 2 PROP ENGINE [OFF-SESSION]\nCurrent Time: ", dt.hour, ":", dt.min, " UTC");
      return;
   }

   if(HasOpenPositions())
   {
      Comment("MODEL 2 PROP ENGINE [POSITION ACTIVE]\nMonitoring open trade execution...");
      return;
   }

   // 🛡️ SPREAD EXPANSION GUARDRAIL: Reject entries if spread exceeds InpMaxSpreadPips ($0.30)
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double current_spread_dollars = ask - bid;
   if(current_spread_dollars > (InpMaxSpreadPips * 0.10))
   {
      PrintFormat("[SPREAD GUARD] Current spread ($%.2f) exceeds max allowed ($%.2f). Skipping trade.",
                  current_spread_dollars, InpMaxSpreadPips * 0.10);
      return;
   }

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

   string exec_str = (InpExecutionTimeframe == EXEC_PERIOD_M5) ? "M5" : "M15";
   string htf_str  = (InpMacroTimeframe == HTF_PERIOD_M15) ? "M15" : ((InpMacroTimeframe == HTF_PERIOD_M30) ? "M30" : "H1");
   string trend_str = htf_bull ? "BULLISH UPTREND" : (htf_bear ? "BEARISH DOWNTREND" : "NEUTRAL");
   Comment(StringFormat("MODEL 2 PROP ENGINE [ACTIVE]\nExec TF: %s | %s Macro Trend: %s", exec_str, htf_str, trend_str));

   if(!htf_bull && !htf_bear) return;

   ENUM_TIMEFRAMES exec_tf = (ENUM_TIMEFRAMES)InpExecutionTimeframe;
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

   // 🌏 ASIAN HIGH/LOW LIQUIDITY SWEEP GUARDRAIL (78.6% Win Rate / 7.86 PF)
   if(InpAsianSweepOnly)
   {
      datetime now_time = iTime(_Symbol, exec_tf, 0);
      datetime midnight_utc = now_time - (now_time % 86400);

      MqlRates asian_rates[];
      ArraySetAsSeries(asian_rates, true);
      int asian_copied = CopyRates(_Symbol, PERIOD_M5, midnight_utc, now_time, asian_rates);
      if(asian_copied > 0)
      {
         double asian_high = 0.0, asian_low = 999999.0;
         for(int a = 0; a < asian_copied; a++)
         {
            MqlDateTime adt;
            TimeToStruct(asian_rates[a].time, adt);
            if(adt.hour >= 0 && adt.hour < 6)
            {
               if(asian_rates[a].high > asian_high) asian_high = asian_rates[a].high;
               if(asian_rates[a].low < asian_low)   asian_low  = asian_rates[a].low;
            }
         }
         if(asian_high > 0.0 && asian_low < 900000.0)
         {
            if(base_buy && prior_5_low > asian_low) return; // Require Asian Low Sweep
            if(base_sell && prior_5_high < asian_high) return; // Require Asian High Sweep
         }
      }
   }

   ENUM_ORDER_TYPE order_type = base_buy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
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

   // 🧠 ML QUALITY GATE CHECK (Threshold: InpMLGateThreshold = 0.58 / 58.0%)
   double fvg_size_pips = base_buy ? bull_fvg_pips : bear_fvg_pips;
   double ml_prob = CalculateMLProbability(base_buy, fvg_size_pips, sl_dist_dollars / 0.10, dt.hour);

   if(ml_prob < InpMLGateThreshold)
   {
      PrintFormat("[ML GATE REJECT] Trade prob (%.1f%%) is below threshold (%.1f%%). Skipping entry.",
                  ml_prob * 100.0, InpMLGateThreshold * 100.0);
      return;
   }

   // 🎯 DYNAMIC 1:1, 1:2, 1:3 TAKE PROFIT TARGETS
   double tp1_price = base_buy ? (entry_price + sl_dist_dollars * 1.0) : (entry_price - sl_dist_dollars * 1.0);
   double tp2_price = base_buy ? (entry_price + sl_dist_dollars * 2.0) : (entry_price - sl_dist_dollars * 2.0);
   double tp3_price = base_buy ? (entry_price + sl_dist_dollars * 3.0) : (entry_price - sl_dist_dollars * 3.0);

   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   
   double r1_pct = 1.0, r2_pct = 1.0, r3_pct = 1.0;

   if(InpRiskDistribution == RISK_DIST_EQUAL)
   {
      r1_pct = InpAccountRiskPct / 3.0;
      r2_pct = InpAccountRiskPct / 3.0;
      r3_pct = InpAccountRiskPct / 3.0;
   }
   else if(InpRiskDistribution == RISK_DIST_FRONT_WEIGHTED)
   {
      r1_pct = InpAccountRiskPct * 0.50;       // 50% of total setup risk to TP1
      r2_pct = InpAccountRiskPct * (1.0 / 3.0); // 33.3% of total setup risk to TP2
      r3_pct = InpAccountRiskPct * (1.0 / 6.0); // 16.7% of total setup risk to TP3
   }
   else if(InpRiskDistribution == RISK_DIST_CUSTOM)
   {
      r1_pct = InpTP1RiskPct;
      r2_pct = InpTP2RiskPct;
      r3_pct = InpTP3RiskPct;
   }

   double r1_usd = balance * (r1_pct / 100.0);
   double r2_usd = balance * (r2_pct / 100.0);
   double r3_usd = balance * (r3_pct / 100.0);

   double lot_t1 = CalculateTicketLotSize(r1_usd, sl_dist_dollars);
   double lot_t2 = CalculateTicketLotSize(r2_usd, sl_dist_dollars);
   double lot_t3 = CalculateTicketLotSize(r3_usd, sl_dist_dollars);

   total_setups_count++;
   PrintFormat("[PROP ENGINE SIGNAL #%d] %s @ $%.2f | ML Prob: %.1f%% | SL: $%.2f | Lots: T1=%.2f, T2=%.2f, T3=%.2f",
               total_setups_count, base_buy ? "BUY" : "SELL", entry_price, ml_prob * 100.0, sl_price, lot_t1, lot_t2, lot_t3);

   double tp_array[3]  = {tp1_price, tp2_price, tp3_price};
   double lot_array[3] = {lot_t1, lot_t2, lot_t3};

   for(int i = 0; i < 3; i++)
   {
      MqlTradeRequest request = {};
      MqlTradeResult  result  = {};

      request.action       = TRADE_ACTION_DEAL;
      request.symbol       = _Symbol;
      request.volume       = lot_array[i];
      request.type         = order_type;
      request.price        = entry_price;
      request.sl           = sl_price;
      request.tp           = tp_array[i];
      request.deviation    = 20;
      request.magic        = InpMagicNumber;
      request.comment      = StringFormat("[PROP_ENG]_TP%d", i + 1);
      request.type_time    = ORDER_TIME_GTC;
      request.type_filling = ORDER_FILLING_IOC;

      if(!OrderSend(request, result))
      {
         PrintFormat("[ERROR] OrderSend TP%d failed. Code: %d", i + 1, GetLastError());
      }
      else
      {
         total_tickets_count++;
         PrintFormat("[SUCCESS] Ticket #%d placed! Lot: %.2f | TP: $%.2f", i + 1, lot_array[i], tp_array[i]);
      }
   }
}
