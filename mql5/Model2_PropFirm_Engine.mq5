//+------------------------------------------------------------------+
//|                                     Model2_PropFirm_Engine.mq5   |
//|                    Model 2: M5 Scalp Hybrid (Prop Firm Engine)   |
//|                         Institutional XAU/USD Strategy Engine    |
//+------------------------------------------------------------------+
#property copyright "Antigravity Quant Research"
#property link      "https://github.com/dev0xeb/xau"
#property version   "3.50"
#property description "Model 2 Prop Firm Account Scalp Hybrid Engine (M5 Timeframe)"
#property description "Evaluates H1 Macro Trend, M5 FVG, M5 Liquidity Sweep, Closed EMA21, AND Daily VWAP Alignment."
#property description "Includes Stop Loss Root-Cause Diagnostic Analytics & Front-Weighted Burst Risk Allocation."

enum ENUM_RISK_DISTRIBUTION
{
   RISK_DIST_EQUAL         = 0, // Equal Split (33.3% TP1 / 33.3% TP2 / 33.3% TP3)
   RISK_DIST_FRONT_WEIGHTED= 1, // Front-Weighted (50% TP1 / 33.3% TP2 / 16.7% TP3) [Recommended]
   RISK_DIST_CUSTOM        = 2  // Custom Per-Ticket Risk (Use InpTP1RiskPct, InpTP2RiskPct, InpTP3RiskPct)
};

//--- Input Parameters
input group "=== Risk & Account Management ==="
input double                InpAccountRiskPct   = 3.0;                  // Total Account Risk per Setup (%)
input ENUM_RISK_DISTRIBUTION InpRiskDistribution = RISK_DIST_FRONT_WEIGHTED; // Risk Distribution Mode
input double                InpFixedLotPerTicket= 0.0;                  // Fixed Lot per Ticket (0.0 = Use Risk % / Set > 0 for Fixed Lots)

input group "=== Custom Ticket Risk % (Used if Mode = Custom) ==="
input double   InpTP1RiskPct       = 1.5;              // Custom Ticket 1 Risk (% of Balance)
input double   InpTP2RiskPct       = 1.0;              // Custom Ticket 2 Risk (% of Balance)
input double   InpTP3RiskPct       = 0.5;              // Custom Ticket 3 Risk (% of Balance)

input group "=== Risk & Guardrail Limits ==="
input double   InpMinSLPips        = 25.0;             // Minimum SL Distance Floor (Pips / $2.50)
input double   InpMaxSLPips        = 80.0;             // Maximum SL Distance (Pips / $8.00)
input double   InpMaxSpreadPips    = 3.0;              // Maximum Allowed Spread (Pips / $0.30 - Rejects Spread Spikes)
input int      InpTrailingMode     = 0;                // Trailing Stop Mode (0=Fixed, 1=BE on TP1, 2=TP1 on TP1, 3=TP1 on TP2, 4=BE on TP2)
input int      InpMagicNumber      = 2002;             // Magic Number (Prop Firm Engine)

input group "=== Strategy Parameters ==="
input double   InpFVGMinPips       = 1.5;              // Minimum Fair Value Gap Size ($0.15)
input int      InpStartHourUTC     = 6;                // Session Start Hour (UTC)
input int      InpEndHourUTC       = 17;               // Session End Hour (UTC)

input group "=== Visual Playback Settings ==="
input color    InpBuyColor         = clrMediumSpringGreen; // Buy Order Arrow Color
input color    InpSellColor        = clrOrangeRed;          // Sell Order Arrow Color

//--- Global Variables & Handles
int      h_h1_ema21, h_h1_ema50, h_m5_ema21;
datetime last_bar_time;

double   initial_balance = 0.0;
int      total_setups_count = 0;
int      total_tickets_count = 0;

//+------------------------------------------------------------------+
//| Calculate Daily VWAP                                             |
//+------------------------------------------------------------------+
double CalculateDailyVWAP()
{
   MqlDateTime dt;
   TimeCurrent(dt);
   dt.hour = 0; dt.min = 0; dt.sec = 0;
   datetime start_of_day = StructToTime(dt);

   MqlRates day_rates[];
   int copied = CopyRates(_Symbol, PERIOD_M5, start_of_day, TimeCurrent(), day_rates);
   if(copied <= 0) return 0.0;

   double cum_tp_vol = 0.0;
   double cum_vol = 0.0;

   for(int i = 0; i < copied; i++)
   {
      double tp = (day_rates[i].high + day_rates[i].low + day_rates[i].close) / 3.0;
      double vol = (double)day_rates[i].tick_volume;
      cum_tp_vol += (tp * vol);
      cum_vol    += vol;
   }

   if(cum_vol <= 0) return 0.0;
   return (cum_tp_vol / cum_vol);
}

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   h_h1_ema21 = iMA(_Symbol, PERIOD_H1, 21, 0, MODE_EMA, PRICE_CLOSE);
   h_h1_ema50 = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
   h_m5_ema21 = iMA(_Symbol, PERIOD_M5, 21, 0, MODE_EMA, PRICE_CLOSE);

   if(h_h1_ema21 == INVALID_HANDLE || h_h1_ema50 == INVALID_HANDLE || h_m5_ema21 == INVALID_HANDLE)
   {
      Print("[ERROR] Failed to create indicator handles.");
      return(INIT_FAILED);
   }

   last_bar_time = 0;
   initial_balance = AccountInfoDouble(ACCOUNT_BALANCE);
   total_setups_count = 0;
   total_tickets_count = 0;

   PrintFormat("[INIT] Model 2 Prop Firm Engine initialized! Total Risk per Setup: %.1f%% | Distribution Mode: %s",
               InpAccountRiskPct, EnumToString(InpRiskDistribution));
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Manage Active Open Positions & Trailing SL                       |
//+------------------------------------------------------------------+
void ManageTrailingStops()
{
   if(InpTrailingMode == 0) return; // 0 = Fixed SL

   int total = PositionsTotal();
   double entry_price_level = 0.0;
   long pos_type = -1;

   int my_positions = 0;
   bool tp1_open = false;
   bool tp2_open = false;

   for(int i = total - 1; i >= 0; i--)
   {
      if(PositionGetSymbol(i) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
      {
         my_positions++;
         string comment = PositionGetString(POSITION_COMMENT);
         pos_type = PositionGetInteger(POSITION_TYPE);
         entry_price_level = PositionGetDouble(POSITION_PRICE_OPEN);

         if(StringFind(comment, "TP1") >= 0 || StringFind(comment, "_TP1") >= 0) tp1_open = true;
         if(StringFind(comment, "TP2") >= 0 || StringFind(comment, "_TP2") >= 0) tp2_open = true;
      }
   }

   // Modes 1 & 2: Trail on TP1 hit
   if((InpTrailingMode == 1 || InpTrailingMode == 2) && (my_positions > 0 && my_positions < 3 && !tp1_open))
   {
      double sl_dist_usd = 2.5;
      double new_sl = 0.0;

      if(pos_type == POSITION_TYPE_BUY)
      {
         new_sl = (InpTrailingMode == 1) ? (entry_price_level + 0.50) : (entry_price_level + sl_dist_usd);
      }
      else if(pos_type == POSITION_TYPE_SELL)
      {
         new_sl = (InpTrailingMode == 1) ? (entry_price_level - 0.50) : (entry_price_level - sl_dist_usd);
      }

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

   // Modes 3 & 4: Trail ON TP2 HIT (Ticket 3 only)
   if((InpTrailingMode == 3 || InpTrailingMode == 4) && (my_positions == 1 && !tp1_open && !tp2_open))
   {
      double sl_dist_usd = 2.5;
      double new_sl = 0.0;

      if(pos_type == POSITION_TYPE_BUY)
      {
         new_sl = (InpTrailingMode == 4) ? (entry_price_level + 0.50) : (entry_price_level + sl_dist_usd);
      }
      else if(pos_type == POSITION_TYPE_SELL)
      {
         new_sl = (InpTrailingMode == 4) ? (entry_price_level - 0.50) : (entry_price_level - sl_dist_usd);
      }

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
//| Diagnostic Engine: Analyze Stop Loss Root Causes                 |
//+------------------------------------------------------------------+
void AnalyzeStopLossReasons()
{
   if(!HistorySelect(0, TimeCurrent())) return;

   int total_deals = HistoryDealsTotal();
   int total_sl_hits = 0;

   int cat_spread_friction  = 0; // Quick stop-out within 1-2 bars / Spread noise
   int cat_reversal_whipsaw = 0; // Macro H1 momentum shift / Trend reversal
   int cat_post_tp_retrace  = 0; // Partial target hit first, then retraced to SL
   int cat_liquidity_sweep  = 0; // Deep structural sweep past swing level

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

      if(profit < 0)
      {
         total_sl_hits++;
         datetime exit_time  = (datetime)HistoryDealGetInteger(ticket, DEAL_TIME);
         ulong pos_id        = HistoryDealGetInteger(ticket, DEAL_POSITION_ID);
         double exit_price   = HistoryDealGetDouble(ticket, DEAL_PRICE);

         datetime entry_time = exit_time;
         double entry_price  = exit_price;
         long deal_type      = -1;

         for(int j = 0; j < total_deals; j++)
         {
            ulong t_in = HistoryDealGetTicket(j);
            if(t_in > 0 && HistoryDealGetInteger(t_in, DEAL_POSITION_ID) == pos_id && HistoryDealGetInteger(t_in, DEAL_ENTRY) == DEAL_ENTRY_IN)
            {
               entry_time = (datetime)HistoryDealGetInteger(t_in, DEAL_TIME);
               entry_price = HistoryDealGetDouble(t_in, DEAL_PRICE);
               deal_type   = HistoryDealGetInteger(t_in, DEAL_TYPE);
               break;
            }
         }

         int duration_sec = (int)(exit_time - entry_time);
         int duration_bars = duration_sec / 300; // M5 bars count

         double sl_dist_usd = MathAbs(entry_price - exit_price);

         if(duration_bars <= 2 && sl_dist_usd <= 2.8)
         {
            cat_spread_friction++;
         }
         else if(duration_bars > 12)
         {
            cat_reversal_whipsaw++;
         }
         else if(sl_dist_usd > 5.0)
         {
            cat_liquidity_sweep++;
         }
         else
         {
            cat_post_tp_retrace++;
         }
      }
   }

   if(total_sl_hits == 0) return;

   Print("-----------------------------------------------------------------------------------------");
   Print(" 🔍 STOP LOSS ROOT-CAUSE DIAGNOSTIC ANALYTICS REPORT");
   Print("-----------------------------------------------------------------------------------------");
   PrintFormat(" TOTAL STOP LOSS EVENTS ANALYZED: %d Tickets", total_sl_hits);
   PrintFormat(" 1. ⚡ Spread Spike / Tight Noise Stop-Outs : %d Tickets (%.1f%%)",
               cat_spread_friction, ((double)cat_spread_friction / total_sl_hits) * 100.0);
   PrintFormat(" 2. 🔄 H1 Trend Reversal / Momentum Shifts  : %d Tickets (%.1f%%)",
               cat_reversal_whipsaw, ((double)cat_reversal_whipsaw / total_sl_hits) * 100.0);
   PrintFormat(" 3. 🎯 Retracement / Post-Move Stop-Outs    : %d Tickets (%.1f%%)",
               cat_post_tp_retrace, ((double)cat_post_tp_retrace / total_sl_hits) * 100.0);
   PrintFormat(" 4. 🌊 Deep Liquidity Sweep Expansion Stops : %d Tickets (%.1f%%)",
               cat_liquidity_sweep, ((double)cat_liquidity_sweep / total_sl_hits) * 100.0);
   Print("-----------------------------------------------------------------------------------------");
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

   Print("=========================================================================================");
   Print(" PERFORMANCE & ANALYTICS SUMMARY REPORT: MODEL 2 (PROP FIRM ENGINE)");
   Print("=========================================================================================");
   PrintFormat(" Starting Account Balance : $%.2f USD", initial_balance);
   PrintFormat(" Final Account Balance    : $%.2f USD", end_balance);
   PrintFormat(" Total Net Profit ($)     : %s$%.2f USD (%s%.2f%% Return)", 
               net_profit >= 0 ? "+" : "-", MathAbs(net_profit), net_profit >= 0 ? "+" : "-", ret_pct);
   Print("-----------------------------------------------------------------------------------------");
   PrintFormat(" TOTAL SETUPS TRIGGERED   : %d Setups (%d Total Placed Tickets)", total_setups_count, total_tickets_count);
   PrintFormat(" CLOSED TICKETS ANALYZED  : %d Tickets", closed_tickets);
   PrintFormat("   - Winning Tickets      : %d Tickets (%.1f%% Win Rate)", winning_deals, win_rate);
   PrintFormat("   - Losing Tickets       : %d Tickets", losing_deals);
   Print("-----------------------------------------------------------------------------------------");
   Print(" TICKET TARGET HIT BREAKDOWN:");
   PrintFormat("   - TP1 Hits (1.0x SL)   : %d Tickets", tp1_count);
   PrintFormat("   - TP2 Hits (2.0x SL)   : %d Tickets", tp2_count);
   PrintFormat("   - TP3 Hits (3.0x SL)   : %d Tickets", tp3_count);
   PrintFormat("   - Stop Loss Hits (SL)  : %d Tickets", sl_count);
   Print("-----------------------------------------------------------------------------------------");
   PrintFormat(" PROFIT FACTOR           : %.2f", profit_factor);
   PrintFormat(" Gross Profit / Gross Loss: +$%.2f / -$%.2f", total_gross_profit, total_gross_loss);
   
   AnalyzeStopLossReasons();
   
   Print("=========================================================================================");
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   GeneratePerformanceAnalytics();
   IndicatorRelease(h_h1_ema21);
   IndicatorRelease(h_h1_ema50);
   IndicatorRelease(h_m5_ema21);
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
   if(dt.hour < InpStartHourUTC || dt.hour >= InpEndHourUTC)
   {
      Comment("MODEL 2 PROP FIRM ENGINE [OFF-SESSION]\nCurrent Time: ", dt.hour, ":", dt.min, " UTC");
      return;
   }

   if(HasOpenPositions())
   {
      Comment("MODEL 2 PROP FIRM ENGINE [POSITION ACTIVE]\nMonitoring open trade execution...");
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

   double h1_close[], h1_ema21[], h1_ema50[];
   ArraySetAsSeries(h1_close, true);
   ArraySetAsSeries(h1_ema21, true);
   ArraySetAsSeries(h1_ema50, true);

   if(CopyClose(_Symbol, PERIOD_H1, 1, 2, h1_close) < 2 ||
      CopyBuffer(h_h1_ema21, 0, 1, 2, h1_ema21) < 2 ||
      CopyBuffer(h_h1_ema50, 0, 1, 2, h1_ema50) < 2) return;

   bool h1_bull = (h1_close[0] > h1_ema21[0]) && (h1_ema21[0] > h1_ema50[0]);
   bool h1_bear = (h1_close[0] < h1_ema21[0]) && (h1_ema21[0] < h1_ema50[0]);

   string trend_str = h1_bull ? "BULLISH UPTREND" : (h1_bear ? "BEARISH DOWNTREND" : "NEUTRAL");
   double daily_vwap = CalculateDailyVWAP();

   Comment("MODEL 2 PROP FIRM ENGINE [ACTIVE]\nH1 Trend: ", trend_str, "\nDaily VWAP: $", DoubleToString(daily_vwap, 2));

   if(!h1_bull && !h1_bear) return;

   MqlRates m5_rates[];
   double m5_ema21[];
   ArraySetAsSeries(m5_rates, true);
   ArraySetAsSeries(m5_ema21, true);

   if(CopyRates(_Symbol, PERIOD_M5, 1, 10, m5_rates) < 10 ||
      CopyBuffer(h_m5_ema21, 0, 1, 10, m5_ema21) < 10) return;

   double low_1  = m5_rates[0].low;
   double high_1 = m5_rates[0].high;
   double close_1= m5_rates[0].close;

   double low_3  = m5_rates[2].low;
   double high_3 = m5_rates[2].high;

   double bull_fvg_pips = (low_1 - high_3) / _Point;
   double bear_fvg_pips = (low_3 - high_1) / _Point;

   bool bull_fvg = bull_fvg_pips >= (InpFVGMinPips * 10.0);
   bool bear_fvg = bear_fvg_pips >= (InpFVGMinPips * 10.0);

   double prior_5_low  = m5_rates[1].low;
   double prior_5_high = m5_rates[1].high;
   for(int k = 1; k <= 5; k++)
   {
      if(m5_rates[k].low < prior_5_low)   prior_5_low  = m5_rates[k].low;
      if(m5_rates[k].high > prior_5_high) prior_5_high = m5_rates[k].high;
   }

   double m5_e21_val = m5_ema21[0];
   bool bull_sweep = prior_5_low <= m5_e21_val;
   bool bear_sweep = prior_5_high >= m5_e21_val;

   bool vwap_bull = (daily_vwap > 0) ? (close_1 > daily_vwap) : true;
   bool vwap_bear = (daily_vwap > 0) ? (close_1 < daily_vwap) : true;

   bool base_buy  = h1_bull && bull_fvg && bull_sweep && (close_1 > m5_e21_val) && vwap_bull;
   bool base_sell = h1_bear && bear_fvg && bear_sweep && (close_1 < m5_e21_val) && vwap_bear;

   if(!base_buy && !base_sell) return;

   ENUM_ORDER_TYPE order_type = base_buy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   double entry_price = base_buy ? ask : bid;

   double recent_3_low  = MathMin(m5_rates[0].low, MathMin(m5_rates[1].low, m5_rates[2].low));
   double recent_3_high = MathMax(m5_rates[0].high, MathMax(m5_rates[1].high, m5_rates[2].high));

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
   PrintFormat("[PROP FIRM ENGINE SIGNAL #%d] %s @ $%.2f | SL: $%.2f | Lots: T1=%.2f, T2=%.2f, T3=%.2f",
               total_setups_count, base_buy ? "BUY" : "SELL", entry_price, sl_price, lot_t1, lot_t2, lot_t3);

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
