//+------------------------------------------------------------------+
//|       Model2_5Year_Institutional_Strategy_Discoverer.mq5         |
//|   Ultra-Robust Pattern Discovery & Strategy Inefficiency Engine  |
//|  Discovers 5 Institutional Price Action Patterns & Draws on MT5  |
//+------------------------------------------------------------------+
#property copyright "Antigravity Quant Research"
#property link      "https://github.com/dev0xeb/xau"
#property version   "3.00"
#property script_show_inputs

//--- Script Inputs
input group "=== Pattern Discovery & Timeframe Inputs ==="
input ENUM_TIMEFRAMES InpResearchTimeframe = PERIOD_M5;            // Primary Research Timeframe (Default: M5)
input int             InpBarsToAnalyze     = 3000;                 // Number of Bars to Inspect & Draw Visually
input double          InpMinFVGPips        = 1.5;                  // FVG Size Floor ($0.15)
input double          InpTargetRR          = 2.0;                  // Target R:R for Strategy Discovery

input group "=== Visual Drawing & Analysis Toggles ==="
input bool            InpDrawPatterns      = true;                 // Draw Discovered Institutional Patterns
input bool            InpDrawInefficiencies= true;                 // Highlight Strategy Losses & Inefficiencies
input bool            InpDrawAsianRange    = true;                 // Draw Asian Session Range & Sweeps
input bool            InpDrawOrderBlocks   = true;                 // Draw Order Blocks & FVGs

//--- Structure for Pattern Metrics
struct PatternMetrics
{
   string name;
   int total_found;
   int wins;
   int losses;
   double gross_pips_profit;
   double gross_pips_loss;
};

//+------------------------------------------------------------------+
//| Helper: Draw Rectangle Object on MT5 Chart                       |
//+------------------------------------------------------------------+
void DrawBox(string name, datetime t1, double p1, datetime t2, double p2, color clr)
{
   ObjectDelete(0, name);
   ObjectCreate(0, name, OBJ_RECTANGLE, 0, t1, p1, t2, p2);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_SOLID);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 1);
   ObjectSetInteger(0, name, OBJPROP_FILL, true);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);
}

//+------------------------------------------------------------------+
//| Helper: Draw Arrow / Marker Object on MT5 Chart                  |
//+------------------------------------------------------------------+
void DrawMarker(string name, datetime t, double price, uchar arrow_code, color clr, string text="")
{
   ObjectDelete(0, name);
   ObjectCreate(0, name, OBJ_ARROW, 0, t, price);
   ObjectSetInteger(0, name, OBJPROP_ARROWCODE, arrow_code);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);

   if(StringLen(text) > 0)
   {
      string text_name = name + "_txt";
      ObjectDelete(0, text_name);
      ObjectCreate(0, text_name, OBJ_TEXT, 0, t, price);
      ObjectSetString(0, text_name, OBJPROP_TEXT, text);
      ObjectSetInteger(0, text_name, OBJPROP_COLOR, clr);
      ObjectSetInteger(0, text_name, OBJPROP_FONTSIZE, 8);
   }
}

//+------------------------------------------------------------------+
//| Script program start function                                    |
//+------------------------------------------------------------------+
void OnStart()
{
   Print("=========================================================================================");
   Print(" STARTING ULTRA-ROBUST INSTITUTIONAL PATTERN DISCOVERY ENGINE ");
   PrintFormat(" Target Symbol: %s | Timeframe: %s | Bars: %d", _Symbol, EnumToString(InpResearchTimeframe), InpBarsToAnalyze);
   Print("=========================================================================================");

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int copied = CopyRates(_Symbol, InpResearchTimeframe, 0, InpBarsToAnalyze, rates);

   if(copied < 100)
   {
      Print("[ERROR] Insufficient bar history copied from MT5!");
      return;
   }

   int h_ema21 = iMA(_Symbol, InpResearchTimeframe, 21, 0, MODE_EMA, PRICE_CLOSE);
   int h_atr14 = iATR(_Symbol, InpResearchTimeframe, 14);

   double ema21[], atr14[];
   ArraySetAsSeries(ema21, true);
   ArraySetAsSeries(atr14, true);

   CopyBuffer(h_ema21, 0, 0, copied, ema21);
   CopyBuffer(h_atr14, 0, 0, copied, atr14);

   // Initialize 5 Institutional Pattern Discovery Counters
   PatternMetrics patterns[5];
   patterns[0].name = "1. Asian Liquidity Sweep Reversal (ICT Turtle Soup)";
   patterns[1].name = "2. Order Block + FVG Confluence";
   patterns[2].name = "3. Discount Equilibrium Retracement (50%-61.8%)";
   patterns[3].name = "4. Volatility Expansion Impulse (Range > 2.0x ATR)";
   patterns[4].name = "5. Current Strategy Baseline (M5 Exec / EMA Sweep)";

   for(int p = 0; p < 5; p++)
   {
      patterns[p].total_found = 0;
      patterns[p].wins = 0;
      patterns[p].losses = 0;
      patterns[p].gross_pips_profit = 0.0;
      patterns[p].gross_pips_loss = 0.0;
   }

   datetime current_day = 0;
   datetime asian_start_time = 0, asian_end_time = 0;
   double asian_high = 0.0, asian_low = 999999.0;

   // Clear old drawing objects
   ObjectsDeleteAll(0, "DISCOV_");

   for(int i = copied - 25; i >= 10; i--)
   {
      MqlDateTime dt;
      TimeToStruct(rates[i].time, dt);

      // Track Asian Session Range (00:00 - 06:00 UTC)
      datetime day_floor = rates[i].time - (rates[i].time % 86400);
      if(day_floor != current_day)
      {
         if(InpDrawAsianRange && asian_high > 0.0 && asian_low < 900000.0 && asian_start_time > 0)
         {
            string box_name = StringFormat("DISCOV_ASIAN_BOX_%d", (int)current_day);
            DrawBox(box_name, asian_start_time, asian_high, asian_end_time, asian_low, C'20,40,70');
         }

         current_day = day_floor;
         asian_high = 0.0;
         asian_low  = 999999.0;
         asian_start_time = 0;
         asian_end_time = 0;
      }

      if(dt.hour >= 0 && dt.hour < 6)
      {
         if(asian_start_time == 0) asian_start_time = rates[i].time;
         asian_end_time = rates[i].time;
         if(rates[i].high > asian_high) asian_high = rates[i].high;
         if(rates[i].low < asian_low)   asian_low  = rates[i].low;
      }

      double low_t   = rates[i].low;
      double high_t  = rates[i].high;
      double close_t = rates[i].close;
      double open_t  = rates[i].open;

      double low_t2  = rates[i+2].low;
      double high_t2 = rates[i+2].high;

      double bull_fvg = (low_t - high_t2) / _Point;
      double bear_fvg = (low_t2 - high_t) / _Point;

      bool valid_bull_fvg = bull_fvg >= (InpMinFVGPips * 10.0);
      bool valid_bear_fvg = bear_fvg >= (InpMinFVGPips * 10.0);

      // -------------------------------------------------------------------
      // PATTERN DISCOVERY LOGIC Across 5 Institutional Strategies
      // -------------------------------------------------------------------
      
      // Pattern 1: Asian Liquidity Sweep Reversal
      bool p1_buy  = (dt.hour >= 6 && dt.hour <= 16) && (asian_low < 900000.0) && (rates[i+1].low <= asian_low) && (close_t > open_t);
      bool p1_sell = (dt.hour >= 6 && dt.hour <= 16) && (asian_high > 0.0)    && (rates[i+1].high >= asian_high) && (close_t < open_t);

      // Pattern 2: OB + FVG Confluence
      bool p2_buy  = valid_bull_fvg && (rates[i+3].close < rates[i+3].open); // Order block before FVG
      bool p2_sell = valid_bear_fvg && (rates[i+3].close > rates[i+3].open);

      // Pattern 3: Discount Equilibrium Retracement
      double swing_high_10 = rates[i+1].high, swing_low_10 = rates[i+1].low;
      for(int s = 1; s <= 10; s++)
      {
         if(rates[i+s].high > swing_high_10) swing_high_10 = rates[i+s].high;
         if(rates[i+s].low < swing_low_10)   swing_low_10  = rates[i+s].low;
      }
      double eq_price = (swing_high_10 + swing_low_10) / 2.0;
      bool p3_buy  = (close_t < eq_price) && (close_t > open_t) && (low_t <= swing_low_10 + 0.50);
      bool p3_sell = (close_t > eq_price) && (close_t < open_t) && (high_t >= swing_high_10 - 0.50);

      // Pattern 4: Volatility Expansion Impulse
      double candle_range = (high_t - low_t);
      bool p4_buy  = (candle_range > 2.0 * atr14[i]) && (close_t > open_t);
      bool p4_sell = (candle_range > 2.0 * atr14[i]) && (close_t < open_t);

      // Pattern 5: Baseline Strategy
      double e21_val = ema21[i];
      bool p5_buy  = valid_bull_fvg && (rates[i+1].low <= e21_val) && (close_t > e21_val);
      bool p5_sell = valid_bear_fvg && (rates[i+1].high >= e21_val) && (close_t < e21_val);

      // Forward Simulation Loop for Patterns
      bool setup_triggers[5] = {p1_buy || p1_sell, p2_buy || p2_sell, p3_buy || p3_sell, p4_buy || p4_sell, p5_buy || p5_sell};
      bool is_buy_flags[5]   = {p1_buy, p2_buy, p3_buy, p4_buy, p5_buy};

      for(int p = 0; p < 5; p++)
      {
         if(!setup_triggers[p]) continue;

         patterns[p].total_found++;
         bool is_buy = is_buy_flags[p];

         double entry = is_buy ? (rates[i-1].open + 0.35) : (rates[i-1].open - 0.35);
         double sl_dist = 3.50;
         double sl = is_buy ? (entry - sl_dist) : (entry + sl_dist);
         double tp = is_buy ? (entry + sl_dist * InpTargetRR) : (entry - sl_dist * InpTargetRR);

         bool win = false, loss = false;
         for(int f = i - 1; f >= MathMax(0, i - 50); f--)
         {
            if(is_buy)
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

         if(win)
         {
            patterns[p].wins++;
            patterns[p].gross_pips_profit += (sl_dist * InpTargetRR / _Point);
         }
         else if(loss)
         {
            patterns[p].losses++;
            patterns[p].gross_pips_loss += (sl_dist / _Point);

            // Draw Visual Inefficiency Marker for Baseline Strategy Losses
            if(p == 4 && InpDrawInefficiencies)
            {
               string marker_name = StringFormat("DISCOV_INEFFICIENCY_%d", i);
               DrawMarker(marker_name, rates[i].time, is_buy ? rates[i].low - 0.50 : rates[i].high + 0.50, 162, clrOrangeRed, "INEFFICIENCY [LOSS]");
            }
         }
      }

      // Draw Visual Boxes for Patterns
      if(InpDrawPatterns && InpDrawOrderBlocks)
      {
         if(valid_bull_fvg)
         {
            string fvg_name = StringFormat("DISCOV_BULL_FVG_%d", i);
            DrawBox(fvg_name, rates[i+2].time, high_t2, rates[i].time, low_t, C'0,80,40');
         }
         else if(valid_bear_fvg)
         {
            string fvg_name = StringFormat("DISCOV_BEAR_FVG_%d", i);
            DrawBox(fvg_name, rates[i+2].time, low_t2, rates[i].time, high_t, C'80,20,20');
         }
      }
   }

   ChartRedraw(0);

   // Print Discovery Report to MT5 Log
   Print("=========================================================================================");
   PrintFormat(" 🏆 ULTRA-ROBUST INSTITUTIONAL STRATEGY DISCOVERY MATRIX (TF: %s)", EnumToString(InpResearchTimeframe));
   Print("=========================================================================================");

   for(int p = 0; p < 5; p++)
   {
      int total = patterns[p].total_found;
      double win_rate = (total > 0) ? ((double)patterns[p].wins / total) * 100.0 : 0.0;
      double pf = (patterns[p].gross_pips_loss > 0) ? (patterns[p].gross_pips_profit / patterns[p].gross_pips_loss) : 0.0;

      PrintFormat(" Strategy Pattern: %s", patterns[p].name);
      PrintFormat("   - Setups Found: %d | Wins: %d | Losses: %d", total, patterns[p].wins, patterns[p].losses);
      PrintFormat("   - Win Rate (%): %.1f%% | Profit Factor: %.2f\n", win_rate, pf);
   }
   Print("=========================================================================================");

   IndicatorRelease(h_ema21);
   IndicatorRelease(h_atr14);
}
//+------------------------------------------------------------------+
