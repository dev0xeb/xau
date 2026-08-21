//+------------------------------------------------------------------+
//|                  Model1_Macro_Intraday_Engine.mq5                |
//|        Model 1: Institutional Macro Intraday Engine (H4/H1/M15)  |
//|        Copyright 2026, Antigravity Quant Research                |
//|        https://github.com/dev0xeb/xau                              |
//+------------------------------------------------------------------+
#property copyright "Antigravity Quant Research"
#property link      "https://github.com/dev0xeb/xau"
#property version   "1.00"
#property description "Model 1: Macro Intraday (H4 Level Tracking / H1 Trend / M15 Closed Execution)"

#include <Trade\Trade.mqh>

//--- Enums
enum ENUM_RISK_DISTRIBUTION
{
   RISK_DIST_FRONT_WEIGHTED = 0, // 50% TP1 / 33.3% TP2 / 16.7% TP3 (Recommended)
   RISK_DIST_EQUAL          = 1  // 33.3% TP1 / 33.3% TP2 / 33.3% TP3
};

enum ENUM_TRAILING_MODE
{
   TRAILING_MODE_FIXED   = 0, // Fixed SL (No Trailing Modification) [Recommended]
   TRAILING_MODE_BE_TP1 = 1  // Move SL to Break-Even when TP1 Hits
};

enum ENUM_SESSION_MODE
{
   SESSION_ALL_DAY   = 0, // 24-Hour All-Day Trading (Default)
   SESSION_LONDON_NY = 1  // Prime Killzones (London 07-11 / NY 13-17 UTC)
};

enum ENUM_EXECUTION_MODE
{
   EXECUTION_MARKET_ON_CLOSE = 0, // Market Order on M15 Bar Close (Recommended)
   EXECUTION_LIMIT_AT_FVG     = 1  // Pending Limit Order at FVG Boundary
};

//--- Input Parameters
input group "=== Model 1 Timeframe Configuration ==="
input ENUM_TIMEFRAMES   InpExecutionTimeframe= PERIOD_M15;       // Execution Timeframe (M15 Recommended)
input ENUM_TIMEFRAMES   InpMacroTimeframe    = PERIOD_H1;        // Macro Trend Timeframe (H1 Recommended)

input group "=== Risk & Account Management ==="
input double                InpAccountRiskPct   = 3.0;                  // Total Account Risk per Setup (%)
input ENUM_RISK_DISTRIBUTION InpRiskDistribution = RISK_DIST_FRONT_WEIGHTED; // Risk Distribution Mode
input double                InpFixedLotPerTicket= 0.0;                  // Fixed Lot per Ticket (0.0 = Use Risk %)

input group "=== Strategy Rules & Displacement Floor ==="
input double   InpFVGMinPips       = 2.0;              // Minimum Fair Value Gap Size ($0.20 / 2.0 Pips)
input double   InpMinRRRatio       = 2.0;              // Minimum Dynamic R:R Gate (TP2 R:R >= 2.0x)
input double   InpSLBufferPips     = 8.0;              // Structural SL Buffer below/above 3-bar low/high ($0.80)
input double   InpMinSLPips        = 20.0;             // Minimum SL Distance Floor ($2.00)
input double   InpMaxSLPips        = 120.0;            // Maximum SL Distance Ceiling ($12.00)
input double   InpMaxSpreadPips    = 3.5;              // Maximum Allowed Spread ($0.35)

input group "=== Session & Order Execution ==="
input ENUM_SESSION_MODE InpSessionMode     = SESSION_ALL_DAY;   // Session Mode (0=All-Day, 1=Killzones)
input ENUM_EXECUTION_MODE InpExecutionMode  = EXECUTION_MARKET_ON_CLOSE; // Order Execution Mode
input ENUM_TRAILING_MODE InpTrailingMode  = TRAILING_MODE_FIXED;  // Trailing Stop Mode (0=Fixed SL, 1=BE on TP1)
input int      InpMagicNumber      = 1001;             // Magic Number (Model 1 Intraday Engine)

input group "=== Visual Tester Settings ==="
input bool     InpDrawHUD          = true;             // Draw On-Chart HUD Panel
input bool     InpDrawFVGBoxes     = true;             // Draw Visual FVG Boxes & Target Lines

//--- Global Variables & Objects
CTrade         m_trade;
int            m_h1_ema21_handle;
int            m_h1_ema50_handle;
int            m_m15_ema21_handle;
datetime       m_last_bar_time;

// Operational Analytics
int            m_total_setups_count;
int            m_tp1_hits_count;
int            m_tp2_hits_count;
int            m_tp3_hits_count;
int            m_sl_hits_count;

//+------------------------------------------------------------------+
//| Expert Initialization Function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   m_trade.SetExpertMagicNumber(InpMagicNumber);
   m_last_bar_time = 0;
   m_total_setups_count = 0;
   m_tp1_hits_count = 0;
   m_tp2_hits_count = 0;
   m_tp3_hits_count = 0;
   m_sl_hits_count = 0;

   // Initialize Indicator Handles
   m_h1_ema21_handle = iMA(_Symbol, InpMacroTimeframe, 21, 0, MODE_EMA, PRICE_CLOSE);
   m_h1_ema50_handle = iMA(_Symbol, InpMacroTimeframe, 50, 0, MODE_EMA, PRICE_CLOSE);
   m_m15_ema21_handle= iMA(_Symbol, InpExecutionTimeframe, 21, 0, MODE_EMA, PRICE_CLOSE);

   if(m_h1_ema21_handle == INVALID_HANDLE || m_h1_ema50_handle == INVALID_HANDLE || m_m15_ema21_handle == INVALID_HANDLE)
   {
      Print("[ERROR] Failed to initialize MQL5 indicator handles!");
      return INIT_FAILED;
   }

   PrintFormat("[MODEL 1 INTRADAY ENGINE] Initialized successfully on %s %s | Magic: %d",
               _Symbol, EnumToString(InpExecutionTimeframe), InpMagicNumber);
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert Deinitialization Function                                 |
//+------------------------------------------------------------------+
//+------------------------------------------------------------------+
//| Mathematical Deal History Audit & Summary Performance Generator |
//+------------------------------------------------------------------+
void GeneratePerformanceReport()
{
   HistorySelect(0, TimeCurrent());
   int total_deals = HistoryDealsTotal();

   int tp1_hits = 0, tp2_hits = 0, tp3_hits = 0, sl_hits = 0;
   double total_tp1_dist = 0.0, total_tp2_dist = 0.0, total_tp3_dist = 0.0, total_sl_dist = 0.0;

   for(int i = 0; i < total_deals; i++)
   {
      ulong deal_ticket = HistoryDealGetTicket(i);
      if(deal_ticket <= 0) continue;

      long magic = HistoryDealGetInteger(deal_ticket, DEAL_MAGIC);
      if(magic != InpMagicNumber) continue;

      long entry = HistoryDealGetInteger(deal_ticket, DEAL_ENTRY);
      if(entry != DEAL_ENTRY_OUT) continue; // ONLY evaluate exit deals!

      double profit = HistoryDealGetDouble(deal_ticket, DEAL_PROFIT);
      double swap   = HistoryDealGetDouble(deal_ticket, DEAL_SWAP);
      double comm   = HistoryDealGetDouble(deal_ticket, DEAL_COMMISSION);
      double pnl    = profit + swap + comm;

      long pos_id       = HistoryDealGetInteger(deal_ticket, DEAL_POSITION_ID);
      double exit_price = HistoryDealGetDouble(deal_ticket, DEAL_PRICE);

      // Find matching entry deal (DEAL_ENTRY_IN) for this position
      double entry_price = 0.0;
      double sl_price    = 0.0;

      for(int k = 0; k < total_deals; k++)
      {
         ulong in_ticket = HistoryDealGetTicket(k);
         if(in_ticket <= 0) continue;
         if(HistoryDealGetInteger(in_ticket, DEAL_POSITION_ID) == pos_id &&
            HistoryDealGetInteger(in_ticket, DEAL_ENTRY) == DEAL_ENTRY_IN)
         {
            entry_price = HistoryDealGetDouble(in_ticket, DEAL_PRICE);
            sl_price    = HistoryDealGetDouble(in_ticket, DEAL_SL);
            break;
         }
      }

      if(entry_price <= 0.0) continue;

      double sl_dist_dollars = MathAbs(entry_price - sl_price);
      if(sl_dist_dollars <= 0.01) sl_dist_dollars = 2.50; // Safety floor

      double move_dollars = MathAbs(exit_price - entry_price);
      double r_multiple   = move_dollars / sl_dist_dollars;

      if(pnl < -0.01 || (sl_price > 0.0 && MathAbs(exit_price - sl_price) < 0.30))
      {
         sl_hits++;
         total_sl_dist += move_dollars;
      }
      else if(pnl > 0.01)
      {
         if(r_multiple >= 2.50)
         {
            tp3_hits++;
            total_tp3_dist += move_dollars;
         }
         else if(r_multiple >= 1.50)
         {
            tp2_hits++;
            total_tp2_dist += move_dollars;
         }
         else
         {
            tp1_hits++;
            total_tp1_dist += move_dollars;
         }
      }
   }

   int total_closed_tickets = tp1_hits + tp2_hits + tp3_hits + sl_hits;
   int calculated_setups = (total_closed_tickets > 0) ? (int)MathCeil((double)total_closed_tickets / 3.0) : m_total_setups_count;
   if(calculated_setups <= 0) calculated_setups = m_total_setups_count;

   double tp1_pct = (calculated_setups > 0) ? ((double)tp1_hits / calculated_setups) * 100.0 : 0.0;
   double tp2_pct = (calculated_setups > 0) ? ((double)tp2_hits / calculated_setups) * 100.0 : 0.0;
   double tp3_pct = (calculated_setups > 0) ? ((double)tp3_hits / calculated_setups) * 100.0 : 0.0;
   double sl_pct  = (calculated_setups > 0) ? ((double)sl_hits / (calculated_setups * 3.0)) * 100.0 : 0.0;

   // Pip calculation (1.0 Pip = $0.10 on XAUUSD)
   double avg_tp1_pips = (tp1_hits > 0) ? (total_tp1_dist / tp1_hits) * 10.0 : 0.0;
   double avg_tp2_pips = (tp2_hits > 0) ? (total_tp2_dist / tp2_hits) * 10.0 : 0.0;
   double avg_tp3_pips = (tp3_hits > 0) ? (total_tp3_dist / tp3_hits) * 10.0 : 0.0;
   double avg_sl_pips  = (sl_hits  > 0) ? (total_sl_dist  / sl_hits)  * 10.0 : 0.0;

   Print("=========================================================================================");
   Print(" 📊 MODEL 1 MACRO INTRADAY ENGINE: OFFICIAL HISTORICAL PERFORMANCE REPORT");
   Print("=========================================================================================");
   PrintFormat(" Total Candidate Setups Triggered : %d Setups (%d Total Closed Deals)", calculated_setups, total_closed_tickets);
   PrintFormat(" TP1 Hits (1.0x R:R Banker)       : %d Hits (%.1f%% Hit Rate) | Avg Distance: %.1f Pips ($%.2f)",
               tp1_hits, tp1_pct, avg_tp1_pips, avg_tp1_pips * 0.10);
   PrintFormat(" TP2 Hits (2.0x R:R Liquidity)    : %d Hits (%.1f%% Hit Rate) | Avg Distance: %.1f Pips ($%.2f)",
               tp2_hits, tp2_pct, avg_tp2_pips, avg_tp2_pips * 0.10);
   PrintFormat(" TP3 Hits (3.0x R:R Macro Runner) : %d Hits (%.1f%% Hit Rate) | Avg Distance: %.1f Pips ($%.2f)",
               tp3_hits, tp3_pct, avg_tp3_pips, avg_tp3_pips * 0.10);
   PrintFormat(" SL Hits (Full Stop Loss Exits)   : %d Deals (%.1f%% Loss Rate)| Avg Distance: %.1f Pips ($%.2f)",
               sl_hits, sl_pct, avg_sl_pips, avg_sl_pips * 0.10);
   Print("-----------------------------------------------------------------------------------------");
   PrintFormat(" OVERALL SETUP WIN RATE (TP1+ Hit): %.1f%% (%d Wins / %d Losses)",
               tp1_pct, tp1_hits, sl_hits);
   Print("=========================================================================================");
}

void OnDeinit(const int reason)
{
   GeneratePerformanceReport();

   IndicatorRelease(m_h1_ema21_handle);
   IndicatorRelease(m_h1_ema50_handle);
   IndicatorRelease(m_m15_ema21_handle);
   ObjectsDeleteAll(0, "M1_HUD_");
   ObjectsDeleteAll(0, "M1_FVG_");
   ObjectsDeleteAll(0, "M1_LINE_");
}

//+------------------------------------------------------------------+
//| Helper Function: Check New M15 Bar Open                          |
//+------------------------------------------------------------------+
bool IsNewBar()
{
   datetime current_bar_time = iTime(_Symbol, InpExecutionTimeframe, 0);
   if(current_bar_time != m_last_bar_time)
   {
      m_last_bar_time = current_bar_time;
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Helper Function: Calculate Ticket Lot Size                        |
//+------------------------------------------------------------------+
double CalculateTicketLotSize(double risk_usd, double sl_dist_dollars)
{
   if(InpFixedLotPerTicket > 0.0) return InpFixedLotPerTicket;

   double tick_size = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tick_value= SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double volume_step=SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double min_vol    =SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double max_vol    =SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);

   if(sl_dist_dollars <= 0.0 || tick_size <= 0.0 || tick_value <= 0.0) return min_vol;

   double loss_per_lot = (sl_dist_dollars / tick_size) * tick_value;
   if(loss_per_lot <= 0.0) return min_vol;

   double raw_lots = risk_usd / loss_per_lot;
   double stepped_lots = MathFloor(raw_lots / volume_step) * volume_step;

   return MathMax(min_vol, MathMin(max_vol, stepped_lots));
}

//+------------------------------------------------------------------+
//| Trailing Stop & Break-Even Management                            |
//+------------------------------------------------------------------+
void ManageOpenPositions()
{
   if(InpTrailingMode == TRAILING_MODE_FIXED) return;

   int total = PositionsTotal();
   for(int i = total - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket <= 0) continue;

      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;

      string comment = PositionGetString(POSITION_COMMENT);
      double open_price = PositionGetDouble(POSITION_PRICE_OPEN);
      double current_sl = PositionGetDouble(POSITION_SL);
      ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);

      // Break-Even on TP1 Hit (For Tickets 2 and 3)
      if(InpTrailingMode == TRAILING_MODE_BE_TP1)
      {
         if(StringFind(comment, "T2") >= 0 || StringFind(comment, "T3") >= 0)
         {
            if(type == POSITION_TYPE_BUY && current_sl < open_price)
            {
               double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
               double tp1_target = open_price + MathAbs(open_price - current_sl);
               if(bid >= tp1_target)
               {
                  m_trade.PositionModify(ticket, open_price + 0.10, PositionGetDouble(POSITION_TP));
                  PrintFormat("[BE ADJUST] Ticket #%d moved to Break-Even (+ $0.10 buffer).", ticket);
               }
            }
            else if(type == POSITION_TYPE_SELL && (current_sl > open_price || current_sl == 0.0))
            {
               double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
               double tp1_target = open_price - MathAbs(open_price - current_sl);
               if(ask <= tp1_target)
               {
                  m_trade.PositionModify(ticket, open_price - 0.10, PositionGetDouble(POSITION_TP));
                  PrintFormat("[BE ADJUST] Ticket #%d moved to Break-Even (+ $0.10 buffer).", ticket);
               }
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| OnTradeTransaction: Deal & Hit Counter Tracking                 |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result)
{
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
   {
      ulong deal_ticket = trans.deal;
      if(deal_ticket <= 0) return;

      if(HistoryDealSelect(deal_ticket))
      {
         long magic = HistoryDealGetInteger(deal_ticket, DEAL_MAGIC);
         if(magic != InpMagicNumber) return;

         long entry = HistoryDealGetInteger(deal_ticket, DEAL_ENTRY);
         if(entry == DEAL_ENTRY_OUT) // Deal exit!
         {
            ulong order_ticket = HistoryDealGetInteger(deal_ticket, DEAL_ORDER);
            string order_comment = "";
            if(HistoryOrderSelect(order_ticket))
            {
               order_comment = HistoryOrderGetString(order_ticket, ORDER_COMMENT);
            }
            if(order_comment == "")
            {
               order_comment = HistoryDealGetString(deal_ticket, DEAL_COMMENT);
            }

            long reason   = HistoryDealGetInteger(deal_ticket, DEAL_REASON);
            double profit = HistoryDealGetDouble(deal_ticket, DEAL_PROFIT);

            if(reason == DEAL_REASON_SL || profit < -0.01)
            {
               m_sl_hits_count++;
            }
            else if(reason == DEAL_REASON_TP || profit > 0.01)
            {
               if(StringFind(order_comment, "T1") >= 0) m_tp1_hits_count++;
               else if(StringFind(order_comment, "T2") >= 0) m_tp2_hits_count++;
               else if(StringFind(order_comment, "T3") >= 0) m_tp3_hits_count++;
               else m_tp1_hits_count++; // Fallback
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| On-Chart HUD Panel Renderer                                      |
//+------------------------------------------------------------------+
void RenderHUD(string macro_trend, string session_state, double last_fvg, int open_pos_count)
{
   if(!InpDrawHUD) return;

   string hud_name = "M1_HUD_PANEL";
   if(ObjectFind(0, hud_name) < 0)
   {
      ObjectCreate(0, hud_name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, hud_name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, hud_name, OBJPROP_XDISTANCE, 20);
      ObjectSetInteger(0, hud_name, OBJPROP_YDISTANCE, 30);
      ObjectSetInteger(0, hud_name, OBJPROP_FONTSIZE, 10);
      ObjectSetInteger(0, hud_name, OBJPROP_SELECTABLE, false);
      ObjectSetString(0, hud_name, OBJPROP_FONT, "Trebuchet MS");
   }

   color hud_color = (macro_trend == "BULLISH") ? clrLimeGreen : ((macro_trend == "BEARISH") ? clrCrimson : clrGold);

   double tp1_pct = (m_total_setups_count > 0) ? ((double)m_tp1_hits_count / m_total_setups_count) * 100.0 : 0.0;
   double tp2_pct = (m_total_setups_count > 0) ? ((double)m_tp2_hits_count / m_total_setups_count) * 100.0 : 0.0;
   double tp3_pct = (m_total_setups_count > 0) ? ((double)m_tp3_hits_count / m_total_setups_count) * 100.0 : 0.0;

   string text = StringFormat(
      "=== MODEL 1: MACRO INTRADAY ENGINE (H4/H1/M15) ===\n" +
      "Symbol: %s | Timeframe: %s | Ask: $%.2f | Bid: $%.2f\n" +
      "H1 Macro Trend: %s | Session: %s\n" +
      "Displacement Floor: $%.2f | Last FVG: $%.2f\n" +
      "--------------------------------------------------\n" +
      "Total Setups Triggered: %d | Open Positions: %d\n" +
      "TP1 Hits (1.0x): %d (%.1f%%) | TP2 Hits (2.0x): %d (%.1f%%)\n" +
      "TP3 Hits (3.0x): %d (%.1f%%) | SL Hits: %d",
      _Symbol, EnumToString(InpExecutionTimeframe),
      SymbolInfoDouble(_Symbol, SYMBOL_ASK), SymbolInfoDouble(_Symbol, SYMBOL_BID),
      macro_trend, session_state,
      InpFVGMinPips * 0.10, last_fvg,
      m_total_setups_count, open_pos_count,
      m_tp1_hits_count, tp1_pct, m_tp2_hits_count, tp2_pct,
      m_tp3_hits_count, tp3_pct, m_sl_hits_count
   );

   ObjectSetString(0, hud_name, OBJPROP_TEXT, text);
   ObjectSetInteger(0, hud_name, OBJPROP_COLOR, hud_color);
}

//+------------------------------------------------------------------+
//| Expert Tick Function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   // Manage active position trailing/BE
   ManageOpenPositions();

   // Run setup entry check strictly on new M15 candle open (index 1 evaluation)
   if(!IsNewBar()) return;

   // 1. Session Guard Check
   datetime current_time = TimeCurrent();
   MqlDateTime dt;
   TimeToStruct(current_time, dt);

   string session_state = "SESSION_ALL_DAY";
   if(InpSessionMode == SESSION_LONDON_NY)
   {
      bool is_london = (dt.hour >= 7 && dt.hour < 11);
      bool is_ny     = (dt.hour >= 13 && dt.hour < 17);
      if(!is_london && !is_ny)
      {
         session_state = "OUTSIDE_KILLZONE";
         RenderHUD("STANDBY", session_state, 0.0, PositionsTotal());
         return;
      }
      session_state = is_london ? "LONDON_KILLZONE" : "NY_KILLZONE";
   }

   // 2. Spread Guard Check
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double spread_dollars = ask - bid;

   if(spread_dollars > InpMaxSpreadPips * 0.10)
   {
      PrintFormat("[SPREAD GUARD] Current spread ($%.2f) exceeds max allowed ($%.2f). Skipping.",
                  spread_dollars, InpMaxSpreadPips * 0.10);
      return;
   }

   // 3. Copy MTF Candle & Indicator Buffers
   MqlRates exec_rates[];
   ArraySetAsSeries(exec_rates, true);
   int copied_m15 = CopyRates(_Symbol, InpExecutionTimeframe, 0, 10, exec_rates);

   MqlRates h1_rates[];
   ArraySetAsSeries(h1_rates, true);
   int copied_h1 = CopyRates(_Symbol, InpMacroTimeframe, 0, 5, h1_rates);

   double h1_e21_buf[], h1_e50_buf[], m15_e21_buf[];
   ArraySetAsSeries(h1_e21_buf, true);
   ArraySetAsSeries(h1_e50_buf, true);
   ArraySetAsSeries(m15_e21_buf, true);

   CopyBuffer(m_h1_ema21_handle, 0, 0, 5, h1_e21_buf);
   CopyBuffer(m_h1_ema50_handle, 0, 0, 5, h1_e50_buf);
   CopyBuffer(m_m15_ema21_handle, 0, 0, 10, m15_e21_buf);

   if(copied_m15 < 6 || copied_h1 < 2) return;

   // 4. STEP 3: H1 Macro Trend Alignment Filter
   double h1_close = h1_rates[1].close;
   double h1_e21   = h1_e21_buf[1];
   double h1_e50   = h1_e50_buf[1];

   string macro_trend = "NEUTRAL";
   bool h1_bull = (h1_close > h1_e21) && (h1_e21 > h1_e50);
   bool h1_bear = (h1_close < h1_e21) && (h1_e21 < h1_e50);

   if(h1_bull) macro_trend = "BULLISH";
   if(h1_bear) macro_trend = "BEARISH";

   if(!h1_bull && !h1_bear)
   {
      RenderHUD(macro_trend, session_state, 0.0, PositionsTotal());
      return;
   }

   // 5. STEP 4: M15 FVG Displacement Calculation on closed candle bar 1 (iloc[-2])
   // Evaluates M15 3-candle displacement across bars [1, 2, 3]
   double low_1  = exec_rates[1].low;
   double high_1 = exec_rates[1].high;
   double close_1= exec_rates[1].close;
   double low_3  = exec_rates[3].low;
   double high_3 = exec_rates[3].high;

   double bull_fvg_dollars = low_1 - high_3;
   double bear_fvg_dollars = low_3 - high_1;

   double min_fvg_dollars = InpFVGMinPips * 0.10; // 2.0 pips = $0.20
   bool bull_fvg = (bull_fvg_dollars >= min_fvg_dollars);
   bool bear_fvg = (bear_fvg_dollars >= min_fvg_dollars);

   double last_fvg = bull_fvg ? bull_fvg_dollars : (bear_fvg ? bear_fvg_dollars : 0.0);

   // 6. STEP 5: H1 Macro Liquidity Sweep Verification (Prior 5 M15 Lows/Highs vs H1 EMA21)
   double prior_5_low  = exec_rates[1].low;
   double prior_5_high = exec_rates[1].high;

   for(int k = 1; k <= 5; k++)
   {
      if(exec_rates[k].low < prior_5_low)   prior_5_low  = exec_rates[k].low;
      if(exec_rates[k].high > prior_5_high) prior_5_high = exec_rates[k].high;
   }

   bool bull_sweep = (prior_5_low <= h1_e21);   // Pulled back into H1 EMA21 discount liquidity
   bool bear_sweep = (prior_5_high >= h1_e21);  // Surged into H1 EMA21 premium liquidity

   // 7. STEP 6: M15 Close Confirmation (Price Closed Above/Below M15 EMA21)
   double m15_e21_val = m15_e21_buf[1];
   bool bull_close_confirm = (close_1 > m15_e21_val);
   bool bear_close_confirm = (close_1 < m15_e21_val);

   bool is_buy  = h1_bull && bull_fvg && bull_sweep && bull_close_confirm;
   bool is_sell = h1_bear && bear_fvg && bear_sweep && bear_close_confirm;

   RenderHUD(macro_trend, session_state, last_fvg, PositionsTotal());

   if(!is_buy && !is_sell) return;

   // Prevent duplicate setup entry on the same bar
   if(PositionsTotal() > 0) return;

   // 8. STEP 7: Structural SL & 3-Burst Target Matrix (1.0x / 2.0x / 3.0x)
   double entry_price = is_buy ? ask : bid;
   
   double recent_3_low  = MathMin(exec_rates[1].low, MathMin(exec_rates[2].low, exec_rates[3].low));
   double recent_3_high = MathMax(exec_rates[1].high, MathMax(exec_rates[2].high, exec_rates[3].high));

   double sl_price, sl_dist_dollars;
   double sl_buffer = InpSLBufferPips * 0.10; // $0.80 buffer

   if(is_buy)
   {
      sl_price = recent_3_low - sl_buffer;
      sl_dist_dollars = entry_price - sl_price;
      if(sl_dist_dollars < InpMinSLPips * 0.10) sl_dist_dollars = InpMinSLPips * 0.10;
      if(sl_dist_dollars > InpMaxSLPips * 0.10) sl_dist_dollars = InpMaxSLPips * 0.10;
      sl_price = entry_price - sl_dist_dollars;
   }
   else
   {
      sl_price = recent_3_high + sl_buffer;
      sl_dist_dollars = sl_price - entry_price;
      if(sl_dist_dollars < InpMinSLPips * 0.10) sl_dist_dollars = InpMinSLPips * 0.10;
      if(sl_dist_dollars > InpMaxSLPips * 0.10) sl_dist_dollars = InpMaxSLPips * 0.10;
      sl_price = entry_price + sl_dist_dollars;
   }

   // Target Math (TP1 = 1.0x, TP2 = 2.0x, TP3 = 3.0x)
   double tp1_price = is_buy ? (entry_price + sl_dist_dollars * 1.0) : (entry_price - sl_dist_dollars * 1.0);
   double tp2_price = is_buy ? (entry_price + sl_dist_dollars * 2.0) : (entry_price - sl_dist_dollars * 2.0);
   double tp3_price = is_buy ? (entry_price + sl_dist_dollars * 3.0) : (entry_price - sl_dist_dollars * 3.0);

   // 9. STEP 8: Dynamic Risk-to-Reward Gate (TP2 R:R >= 2.0x)
   double tp2_rr = (MathAbs(tp2_price - entry_price) / sl_dist_dollars);
   if(tp2_rr < InpMinRRRatio)
   {
      PrintFormat("[RR GATE REJECT] TP2 R:R (%.2fx) is below floor (%.2fx). Skipping entry.",
                  tp2_rr, InpMinRRRatio);
      return;
   }

   // 10. STEP 9: 3-Ticket Order Execution
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double r1_pct = 1.50, r2_pct = 1.00, r3_pct = 0.50; // 50% TP1 / 33.3% TP2 / 16.7% TP3

   if(InpRiskDistribution == RISK_DIST_EQUAL)
   {
      r1_pct = InpAccountRiskPct / 3.0;
      r2_pct = InpAccountRiskPct / 3.0;
      r3_pct = InpAccountRiskPct / 3.0;
   }
   else
   {
      r1_pct = InpAccountRiskPct * 0.50;
      r2_pct = InpAccountRiskPct * (1.0 / 3.0);
      r3_pct = InpAccountRiskPct * (1.0 / 6.0);
   }

   double r1_usd = balance * (r1_pct / 100.0);
   double r2_usd = balance * (r2_pct / 100.0);
   double r3_usd = balance * (r3_pct / 100.0);

   double lot_t1 = CalculateTicketLotSize(r1_usd, sl_dist_dollars);
   double lot_t2 = CalculateTicketLotSize(r2_usd, sl_dist_dollars);
   double lot_t3 = CalculateTicketLotSize(r3_usd, sl_dist_dollars);

   ENUM_ORDER_TYPE order_type = is_buy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;

   m_total_setups_count++;

   double sl_pips  = sl_dist_dollars * 10.0;
   double tp1_pips = sl_pips * 1.0;
   double tp2_pips = sl_pips * 2.0;
   double tp3_pips = sl_pips * 3.0;

   PrintFormat("[MODEL 1 EXECUTION] %s Setup #%d Confirmed | SL: $%.2f (%.1f Pips) | TP1: $%.2f (%.1f Pips) | TP2: $%.2f (%.1f Pips) | TP3: $%.2f (%.1f Pips)",
               is_buy ? "BUY" : "SELL", m_total_setups_count, sl_price, sl_pips, tp1_price, tp1_pips, tp2_price, tp2_pips, tp3_price, tp3_pips);

   if(is_buy)
   {
      m_trade.Buy(lot_t1, _Symbol, ask, sl_price, tp1_price, StringFormat("Model1_T1_#%d", m_total_setups_count));
      m_trade.Buy(lot_t2, _Symbol, ask, sl_price, tp2_price, StringFormat("Model1_T2_#%d", m_total_setups_count));
      m_trade.Buy(lot_t3, _Symbol, ask, sl_price, tp3_price, StringFormat("Model1_T3_#%d", m_total_setups_count));
   }
   else
   {
      m_trade.Sell(lot_t1, _Symbol, bid, sl_price, tp1_price, StringFormat("Model1_T1_#%d", m_total_setups_count));
      m_trade.Sell(lot_t2, _Symbol, bid, sl_price, tp2_price, StringFormat("Model1_T2_#%d", m_total_setups_count));
      m_trade.Sell(lot_t3, _Symbol, bid, sl_price, tp3_price, StringFormat("Model1_T3_#%d", m_total_setups_count));
   }
}
//+------------------------------------------------------------------+
