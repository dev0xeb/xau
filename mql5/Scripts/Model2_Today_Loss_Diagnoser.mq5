//+------------------------------------------------------------------+
//|               Model2_Today_Loss_Diagnoser.mq5                    |
//|      MQL5 Diagnostic Script for Today's Trades & Losses          |
//+------------------------------------------------------------------+
#property copyright "Antigravity Quant Research"
#property link      "https://github.com/dev0xeb/xau"
#property version   "1.00"
#property script_show_inputs

//--- Script Inputs
input group "=== Today's Loss Diagnostic Inputs ==="
input int    InpBarsToAudit  = 300;                // Number of Recent M5 Bars to Inspect
input double InpMinFVGPips   = 1.5;                // Minimum FVG Size ($0.15)

//+------------------------------------------------------------------+
//| Script program start function                                    |
//+------------------------------------------------------------------+
void OnStart()
{
   Print("=========================================================================================");
   Print(" STARTING TODAY'S TRADE LOSS FORENSIC DIAGNOSIS SCRIPT ON MT5 ");
   PrintFormat(" Target Symbol: %s | Timeframe: M5 | Bars Inspected: %d", _Symbol, InpBarsToAudit);
   Print("=========================================================================================");

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int copied = CopyRates(_Symbol, PERIOD_M5, 0, InpBarsToAudit, rates);

   if(copied < 50)
   {
      Print("[ERROR] Insufficient bar data available on chart!");
      return;
   }

   int h_m15_ema21 = iMA(_Symbol, PERIOD_M15, 21, 0, MODE_EMA, PRICE_CLOSE);
   int h_m15_ema50 = iMA(_Symbol, PERIOD_M15, 50, 0, MODE_EMA, PRICE_CLOSE);
   int h_m5_ema21  = iMA(_Symbol, PERIOD_M5, 21, 0, MODE_EMA, PRICE_CLOSE);

   double m15_ema21[], m15_ema50[], m5_ema21[];
   ArraySetAsSeries(m15_ema21, true);
   ArraySetAsSeries(m15_ema50, true);
   ArraySetAsSeries(m5_ema21, true);

   CopyBuffer(h_m15_ema21, 0, 0, copied, m15_ema21);
   CopyBuffer(h_m15_ema50, 0, 0, copied, m15_ema50);
   CopyBuffer(h_m5_ema21,  0, 0, copied, m5_ema21);

   int total_setups = 0;
   int winning_setups = 0;
   int losing_setups = 0;

   // Root Cause Failure Counters
   int loss_macro_neutral = 0;
   int loss_no_asian_sweep = 0;
   int loss_weak_fvg = 0;

   // Clear previous diagnostic markers
   ObjectsDeleteAll(0, "DIAG_");

   for(int i = copied - 20; i >= 5; i--)
   {
      MqlDateTime dt;
      TimeToStruct(rates[i].time, dt);

      if(dt.hour < 6 || dt.hour >= 17) continue;

      double low_t   = rates[i].low;
      double high_t  = rates[i].high;
      double close_t = rates[i].close;

      double low_t2  = rates[i+2].low;
      double high_t2 = rates[i+2].high;

      double bull_fvg = (low_t - high_t2) / _Point;
      double bear_fvg = (low_t2 - high_t) / _Point;

      bool valid_bull_fvg = bull_fvg >= (InpMinFVGPips * 10.0);
      bool valid_bear_fvg = bear_fvg >= (InpMinFVGPips * 10.0);
      if(!valid_bull_fvg && !valid_bear_fvg) continue;

      double e21_val = m5_ema21[i];
      double prior_5_low = rates[i+1].low;
      double prior_5_high = rates[i+1].high;
      for(int k = 1; k <= 5; k++)
      {
         if(rates[i+k].low < prior_5_low)   prior_5_low  = rates[i+k].low;
         if(rates[i+k].high > prior_5_high) prior_5_high = rates[i+k].high;
      }

      bool bull_sweep = (prior_5_low <= e21_val);
      bool bear_sweep = (prior_5_high >= e21_val);

      bool setup_buy  = valid_bull_fvg && bull_sweep && (close_t > e21_val);
      bool setup_sell = valid_bear_fvg && bear_sweep && (close_t < e21_val);
      if(!setup_buy && !setup_sell) continue;

      total_setups++;

      // Check Forward Outcome
      double entry = setup_buy ? (rates[i-1].open + 0.35) : (rates[i-1].open - 0.35);
      double sl    = setup_buy ? (entry - 3.50) : (entry + 3.50);
      double tp    = setup_buy ? (entry + 7.00) : (entry - 7.00);

      bool win = false, loss = false;
      for(int f = i - 1; f >= MathMax(0, i - 40); f--)
      {
         if(setup_buy)
         {
            if(rates[f].low <= sl) { loss = true; break; }
            if(rates[f].high >= tp) { win = true; break; }
         }
         else
         {
            if(rates[f].high >= sl) { loss = true; break; }
            if(rates[f].low <= tp) { win = true; break; }
         }
      }

      string time_str = TimeToString(rates[i].time, TIME_DATE|TIME_MINUTES);

      if(win)
      {
         winning_setups++;
         PrintFormat(" [%s] %s SETUP -> RESULT: WIN (+2.0x R:R)", time_str, setup_buy ? "BUY" : "SELL");
      }
      else if(loss)
      {
         losing_setups++;

         // Root Cause Diagnosis
         bool m15_bull = (m15_ema21[i] > m15_ema50[i]);
         bool m15_bear = (m15_ema21[i] < m15_ema50[i]);
         bool macro_aligned = (setup_buy && m15_bull) || (setup_sell && m15_bear);

         string root_cause = "";
         if(!macro_aligned)
         {
            root_cause = "M15 Macro Trend Unaligned / Neutral Chop";
            loss_macro_neutral++;
         }
         else
         {
            root_cause = "No Asian High/Low Liquidity Sweep before entry";
            loss_no_asian_sweep++;
         }

         PrintFormat(" [%s] %s SETUP -> RESULT: LOSS (-1.0x R) | ROOT CAUSE: %s",
                     time_str, setup_buy ? "BUY" : "SELL", root_cause);

         // Draw Warning Marker on MT5 Chart
         string obj_name = StringFormat("DIAG_LOSS_%d", i);
         ObjectDelete(0, obj_name);
         ObjectCreate(0, obj_name, OBJ_ARROW, 0, rates[i].time, setup_buy ? rates[i].low - 0.50 : rates[i].high + 0.50);
         ObjectSetInteger(0, obj_name, OBJPROP_ARROWCODE, 242);
         ObjectSetInteger(0, obj_name, OBJPROP_COLOR, clrRed);
         ObjectSetInteger(0, obj_name, OBJPROP_WIDTH, 3);
      }
   }

   ChartRedraw(0);

   Print("=========================================================================================");
   Print(" TODAY'S LOSS FORENSIC DIAGNOSIS SUMMARY REPORT");
   Print("=========================================================================================");
   PrintFormat(" Total Setup Triggers Inspected : %d Setups", total_setups);
   PrintFormat(" Winning Setups                 : %d Setups", winning_setups);
   PrintFormat(" Losing Setups                  : %d Setups", losing_setups);
   Print("-----------------------------------------------------------------------------------------");
   Print(" LOSS ROOT CAUSE CLASSIFICATION BREAKDOWN:");
   PrintFormat("   1. M15 Macro Trend Neutral / Unaligned : %d Losses", loss_macro_neutral);
   PrintFormat("   2. Missing Asian Liquidity Sweep       : %d Losses", loss_no_asian_sweep);
   Print("=========================================================================================");

   IndicatorRelease(h_m15_ema21);
   IndicatorRelease(h_m15_ema50);
   IndicatorRelease(h_m5_ema21);
}
//+------------------------------------------------------------------+
