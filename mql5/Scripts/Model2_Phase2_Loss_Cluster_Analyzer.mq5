//+------------------------------------------------------------------+
//|             Model2_Phase2_Loss_Cluster_Analyzer.mq5              |
//|      Phase 2 Quantitative Loss Cluster Identification Engine      |
//|      Native MT5 Script Reading Phase1 CSV & Profiling 9 Dimensions |
//+------------------------------------------------------------------+
#property copyright "Antigravity Quant Research"
#property link      "https://github.com/dev0xeb/xau"
#property version   "3.95"
#property script_show_inputs

//--- Inputs
input group "=== Phase 2 Loss Cluster Analysis Configuration ==="
input string InpInputCSVFilename  = "Phase1_Trade_Forensics.csv";  // Source CSV in MQL5\Files\
input string InpOutputCSVFilename = "Phase2_Loss_Clusters.csv";    // Output CSV in MQL5\Files\

//--- Trade Record Struct
struct CSVTradeRecord
{
   int      trade_id;
   datetime timestamp;
   string   direction;
   double   entry_price;
   double   sl_price;
   double   tp1_price;
   double   tp2_price;
   double   tp3_price;
   string   outcome;
   string   loss_cause;
   double   mae_dollars;
   double   mae_pips;
   double   mfe_dollars;
   double   mfe_pips;
   double   fvg_size_pips;
   double   fvg_atr_ratio;
   int      fvg_age_bars;
   double   displacement_ratio;
   double   ema21_slope;
   double   ema21_ema50_sep;
   double   atr_regime;
   double   rsi_14;
   double   ml_prob;
   double   spread_pips;
   double   sl_dist_pips;
   string   session_name;
   int      hour_utc;
   string   day_name;
   double   trend_strength;
   double   ext_from_ema21;
   int      duration_bars;
   bool     is_win;
   bool     is_loss;
};

//+------------------------------------------------------------------+
//| Main Script Function                                             |
//+------------------------------------------------------------------+
void OnStart()
{
   Print("=========================================================================================");
   Print(" 🔬 STARTING PHASE 2 QUANTITATIVE LOSS CLUSTER ANALYSIS IN MT5");
   PrintFormat(" Reading CSV File: MQL5\\Files\\%s", InpInputCSVFilename);
   Print("=========================================================================================");

   int file_handle = FileOpen(InpInputCSVFilename, FILE_READ|FILE_CSV|FILE_ANSI, ',');
   if(file_handle == INVALID_HANDLE)
   {
      PrintFormat("[ERROR] Could not open %s inside MQL5\\Files\\. Run Phase 1 Forensic Auditor script first.", InpInputCSVFilename);
      return;
   }

   // Skip complete 31-token Header Line
   for(int h = 0; h < 31; h++) FileReadString(file_handle);

   CSVTradeRecord records[];
   int total_trades = 0;
   int total_losses = 0;

   while(!FileIsEnding(file_handle))
   {
      string line_id = FileReadString(file_handle);
      if(line_id == "" || line_id == "trade_id") continue;

      total_trades++;
      ArrayResize(records, total_trades);
      int idx = total_trades - 1;

      records[idx].trade_id            = (int)StringToInteger(line_id);
      records[idx].timestamp           = StringToTime(FileReadString(file_handle));
      records[idx].direction           = FileReadString(file_handle);
      records[idx].entry_price         = StringToDouble(FileReadString(file_handle));
      records[idx].sl_price            = StringToDouble(FileReadString(file_handle));
      records[idx].tp1_price           = StringToDouble(FileReadString(file_handle));
      records[idx].tp2_price           = StringToDouble(FileReadString(file_handle));
      records[idx].tp3_price           = StringToDouble(FileReadString(file_handle));
      records[idx].outcome             = FileReadString(file_handle);
      records[idx].loss_cause          = FileReadString(file_handle);
      records[idx].mae_dollars         = StringToDouble(FileReadString(file_handle));
      records[idx].mae_pips            = StringToDouble(FileReadString(file_handle));
      records[idx].mfe_dollars         = StringToDouble(FileReadString(file_handle));
      records[idx].mfe_pips            = StringToDouble(FileReadString(file_handle));
      records[idx].fvg_size_pips       = StringToDouble(FileReadString(file_handle));
      records[idx].fvg_atr_ratio       = StringToDouble(FileReadString(file_handle));
      records[idx].fvg_age_bars        = (int)StringToInteger(FileReadString(file_handle));
      records[idx].displacement_ratio  = StringToDouble(FileReadString(file_handle));
      records[idx].ema21_slope         = StringToDouble(FileReadString(file_handle));
      records[idx].ema21_ema50_sep     = StringToDouble(FileReadString(file_handle));
      records[idx].atr_regime          = StringToDouble(FileReadString(file_handle));
      records[idx].rsi_14              = StringToDouble(FileReadString(file_handle));
      records[idx].ml_prob             = StringToDouble(FileReadString(file_handle));
      records[idx].spread_pips         = StringToDouble(FileReadString(file_handle));
      records[idx].sl_dist_pips        = StringToDouble(FileReadString(file_handle));
      records[idx].session_name        = FileReadString(file_handle);
      records[idx].hour_utc            = (int)StringToInteger(FileReadString(file_handle));
      records[idx].day_name            = FileReadString(file_handle);
      records[idx].trend_strength      = StringToDouble(FileReadString(file_handle));
      records[idx].ext_from_ema21      = StringToDouble(FileReadString(file_handle));
      records[idx].duration_bars       = (int)StringToInteger(FileReadString(file_handle));

      records[idx].is_win  = (StringFind(records[idx].outcome, "WIN") >= 0);
      records[idx].is_loss = (records[idx].outcome == "LOSS" || !records[idx].is_win);

      if(records[idx].is_loss) total_losses++;
   }

   FileClose(file_handle);

   PrintFormat(" Dataset Loaded Successfully: %d Trades Loaded (%d Wins / %d Losses).",
               total_trades, total_trades - total_losses, total_losses);

   // --- 1. WHICH FVG SIZES LOSE?
   Print("-----------------------------------------------------------------------------------------");
   Print(" 📊 1. LOSS ANALYSIS BY FVG SIZE ($ / pips):");
   Print("   FVG Range        | Trades | Wins  | Losses | Win Rate (%) | % Total Losses | Cluster Tag");
   Print("   --------------------------------------------------------------------------------------");
   
   double fvg_floors[6] = {0.0, 15.0, 20.0, 25.0, 35.0, 50.0};
   double fvg_caps[6]   = {15.0, 20.0, 25.0, 35.0, 50.0, 9999.0};
   string fvg_labels[6] = {"< $0.15 (Shallow)", "$0.15 - $0.20", "$0.20 - $0.25", "$0.25 - $0.35", "$0.35 - $0.50", "> $0.50 (Extreme)"};

   for(int b = 0; b < 6; b++)
   {
      int b_trades = 0, b_wins = 0, b_losses = 0;
      for(int r = 0; r < total_trades; r++)
      {
         if(records[r].fvg_size_pips >= fvg_floors[b] && records[r].fvg_size_pips < fvg_caps[b])
         {
            b_trades++;
            if(records[r].is_win) b_wins++;
            if(records[r].is_loss) b_losses++;
         }
      }
      double wr = (b_trades > 0) ? ((double)b_wins / b_trades) * 100.0 : 0.0;
      double ls = (total_losses > 0) ? ((double)b_losses / total_losses) * 100.0 : 0.0;
      string tag = (wr < 46.0 && b_losses > 300) ? "🔴 TOXIC LOSS CLUSTER" : ((wr > 54.0) ? "🟢 WINNING CLUSTER" : "");
      PrintFormat("   %-16s | %6d | %5d | %6d |    %5.1f%%   |     %5.1f%%    | %s",
                  fvg_labels[b], b_trades, b_wins, b_losses, wr, ls, tag);
   }

   // --- 2. WHICH HOURS LOSE?
   Print("-----------------------------------------------------------------------------------------");
   Print(" 📊 2. LOSS ANALYSIS BY HOUR OF DAY (UTC):");
   Print("   Hour (UTC)       | Trades | Wins  | Losses | Win Rate (%) | % Total Losses | Cluster Tag");
   Print("   --------------------------------------------------------------------------------------");
   for(int h = 0; h < 24; h++)
   {
      int b_trades = 0, b_wins = 0, b_losses = 0;
      for(int r = 0; r < total_trades; r++)
      {
         if(records[r].hour_utc == h)
         {
            b_trades++;
            if(records[r].is_win) b_wins++;
            if(records[r].is_loss) b_losses++;
         }
      }
      double wr = (b_trades > 0) ? ((double)b_wins / b_trades) * 100.0 : 0.0;
      double ls = (total_losses > 0) ? ((double)b_losses / total_losses) * 100.0 : 0.0;
      string tag = (wr < 46.0 && b_losses > 300) ? "🔴 TOXIC LOSS CLUSTER" : ((wr > 54.0) ? "🟢 WINNING CLUSTER" : "");
      PrintFormat("   Hour %02d:00 UTC     | %6d | %5d | %6d |    %5.1f%%   |     %5.1f%%    | %s",
                  h, b_trades, b_wins, b_losses, wr, ls, tag);
   }

   // --- 3. WHICH SESSIONS LOSE?
   Print("-----------------------------------------------------------------------------------------");
   Print(" 📊 3. LOSS ANALYSIS BY TRADING SESSION:");
   Print("   Session Name     | Trades | Wins  | Losses | Win Rate (%) | % Total Losses | Cluster Tag");
   Print("   --------------------------------------------------------------------------------------");
   string sessions[4] = {"Asian", "London", "New York", "Late Off-Session"};
   for(int s = 0; s < 4; s++)
   {
      int b_trades = 0, b_wins = 0, b_losses = 0;
      for(int r = 0; r < total_trades; r++)
      {
         if(records[r].session_name == sessions[s])
         {
            b_trades++;
            if(records[r].is_win) b_wins++;
            if(records[r].is_loss) b_losses++;
         }
      }
      double wr = (b_trades > 0) ? ((double)b_wins / b_trades) * 100.0 : 0.0;
      double ls = (total_losses > 0) ? ((double)b_losses / total_losses) * 100.0 : 0.0;
      string tag = (wr < 46.0 && b_losses > 500) ? "🔴 TOXIC LOSS CLUSTER" : ((wr > 54.0) ? "🟢 WINNING CLUSTER" : "");
      PrintFormat("   %-16s | %6d | %5d | %6d |    %5.1f%%   |     %5.1f%%    | %s",
                  sessions[s], b_trades, b_wins, b_losses, wr, ls, tag);
   }

   // --- 4. WHICH EMA SLOPES LOSE?
   Print("-----------------------------------------------------------------------------------------");
   Print(" 📊 4. LOSS ANALYSIS BY M5 EMA21 3-BAR SLOPE ($):");
   Print("   EMA21 Slope ($)  | Trades | Wins  | Losses | Win Rate (%) | % Total Losses | Cluster Tag");
   Print("   --------------------------------------------------------------------------------------");
   double slope_floors[5] = {-100.0, 0.0, 0.10, 0.20, 0.35};
   double slope_caps[5]   = {0.0, 0.10, 0.20, 0.35, 100.0};
   string slope_labels[5] = {"< $0.00 (Counter)", "$0.00 - $0.10 (Flat)", "$0.10 - $0.20 (Mod)", "$0.20 - $0.35 (Strong)", "> $0.35 (Steep)"};

   for(int b = 0; b < 5; b++)
   {
      int b_trades = 0, b_wins = 0, b_losses = 0;
      for(int r = 0; r < total_trades; r++)
      {
         if(records[r].ema21_slope >= slope_floors[b] && records[r].ema21_slope < slope_caps[b])
         {
            b_trades++;
            if(records[r].is_win) b_wins++;
            if(records[r].is_loss) b_losses++;
         }
      }
      double wr = (b_trades > 0) ? ((double)b_wins / b_trades) * 100.0 : 0.0;
      double ls = (total_losses > 0) ? ((double)b_losses / total_losses) * 100.0 : 0.0;
      string tag = (wr < 46.0 && b_losses > 300) ? "🔴 TOXIC LOSS CLUSTER" : ((wr > 54.0) ? "🟢 WINNING CLUSTER" : "");
      PrintFormat("   %-16s | %6d | %5d | %6d |    %5.1f%%   |     %5.1f%%    | %s",
                  slope_labels[b], b_trades, b_wins, b_losses, wr, ls, tag);
   }

   // --- 5. WHICH EXTENSIONS FROM EMA21 LOSE?
   Print("-----------------------------------------------------------------------------------------");
   Print(" 📊 5. LOSS ANALYSIS BY EXTENSION FROM M5 EMA21 ($):");
   Print("   Extension ($)    | Trades | Wins  | Losses | Win Rate (%) | % Total Losses | Cluster Tag");
   Print("   --------------------------------------------------------------------------------------");
   double ext_floors[5] = {0.0, 1.0, 2.5, 4.0, 6.0};
   double ext_caps[5]   = {1.0, 2.5, 4.0, 6.0, 100.0};
   string ext_labels[5] = {"$0.00 - $1.00", "$1.00 - $2.50", "$2.50 - $4.00", "$4.00 - $6.00", "> $6.00 (Over-extended)"};

   for(int b = 0; b < 5; b++)
   {
      int b_trades = 0, b_wins = 0, b_losses = 0;
      for(int r = 0; r < total_trades; r++)
      {
         if(records[r].ext_from_ema21 >= ext_floors[b] && records[r].ext_from_ema21 < ext_caps[b])
         {
            b_trades++;
            if(records[r].is_win) b_wins++;
            if(records[r].is_loss) b_losses++;
         }
      }
      double wr = (b_trades > 0) ? ((double)b_wins / b_trades) * 100.0 : 0.0;
      double ls = (total_losses > 0) ? ((double)b_losses / total_losses) * 100.0 : 0.0;
      string tag = (wr < 46.0 && b_losses > 300) ? "🔴 TOXIC LOSS CLUSTER" : ((wr > 54.0) ? "🟢 WINNING CLUSTER" : "");
      PrintFormat("   %-16s | %6d | %5d | %6d |    %5.1f%%   |     %5.1f%%    | %s",
                  ext_labels[b], b_trades, b_wins, b_losses, wr, ls, tag);
   }

   // --- 6. WHICH ATR REGIMES LOSE?
   Print("-----------------------------------------------------------------------------------------");
   Print(" 📊 6. LOSS ANALYSIS BY ATR VOLATILITY REGIME (ATR14 / ATR50):");
   Print("   ATR Regime Ratio | Trades | Wins  | Losses | Win Rate (%) | % Total Losses | Cluster Tag");
   Print("   --------------------------------------------------------------------------------------");
   double atr_floors[5] = {0.0, 0.80, 1.00, 1.25, 1.50};
   double atr_caps[5]   = {0.80, 1.00, 1.25, 1.50, 100.0};
   string atr_labels[5] = {"< 0.80 (Squeeze)", "0.80 - 1.00 (Normal)", "1.00 - 1.25 (Expanding)", "1.25 - 1.50 (High Vol)", "> 1.50 (Extreme)"};

   for(int b = 0; b < 5; b++)
   {
      int b_trades = 0, b_wins = 0, b_losses = 0;
      for(int r = 0; r < total_trades; r++)
      {
         if(records[r].atr_regime >= atr_floors[b] && records[r].atr_regime < atr_caps[b])
         {
            b_trades++;
            if(records[r].is_win) b_wins++;
            if(records[r].is_loss) b_losses++;
         }
      }
      double wr = (b_trades > 0) ? ((double)b_wins / b_trades) * 100.0 : 0.0;
      double ls = (total_losses > 0) ? ((double)b_losses / total_losses) * 100.0 : 0.0;
      string tag = (wr < 46.0 && b_losses > 300) ? "🔴 TOXIC LOSS CLUSTER" : ((wr > 54.0) ? "🟢 WINNING CLUSTER" : "");
      PrintFormat("   %-16s | %6d | %5d | %6d |    %5.1f%%   |     %5.1f%%    | %s",
                  atr_labels[b], b_trades, b_wins, b_losses, wr, ls, tag);
   }

   // --- 7. WHICH SL SIZES LOSE?
   Print("-----------------------------------------------------------------------------------------");
   Print(" 📊 7. LOSS ANALYSIS BY STOP LOSS SIZE ($ / pips):");
   Print("   SL Size ($)      | Trades | Wins  | Losses | Win Rate (%) | % Total Losses | Cluster Tag");
   Print("   --------------------------------------------------------------------------------------");
   double sl_floors[5] = {0.0, 25.0, 35.0, 50.0, 80.0};
   double sl_caps[5]   = {25.0, 35.0, 50.0, 80.0, 9999.0};
   string sl_labels[5] = {"$2.50 (Min Floor)", "$2.50 - $3.50", "$3.50 - $5.00", "$5.00 - $8.00", "> $8.00 (Wide)"};

   for(int b = 0; b < 5; b++)
   {
      int b_trades = 0, b_wins = 0, b_losses = 0;
      for(int r = 0; r < total_trades; r++)
      {
         if(records[r].sl_dist_pips >= sl_floors[b] && records[r].sl_dist_pips < sl_caps[b])
         {
            b_trades++;
            if(records[r].is_win) b_wins++;
            if(records[r].is_loss) b_losses++;
         }
      }
      double wr = (b_trades > 0) ? ((double)b_wins / b_trades) * 100.0 : 0.0;
      double ls = (total_losses > 0) ? ((double)b_losses / total_losses) * 100.0 : 0.0;
      string tag = (wr < 46.0 && b_losses > 300) ? "🔴 TOXIC LOSS CLUSTER" : ((wr > 54.0) ? "🟢 WINNING CLUSTER" : "");
      PrintFormat("   %-16s | %6d | %5d | %6d |    %5.1f%%   |     %5.1f%%    | %s",
                  sl_labels[b], b_trades, b_wins, b_losses, wr, ls, tag);
   }

   // --- 8. WHICH TREND STRENGTHS LOSE?
   Print("-----------------------------------------------------------------------------------------");
   Print(" 📊 8. LOSS ANALYSIS BY TREND STRENGTH (M15 Close - M15 EMA50):");
   Print("   Trend Dist ($)   | Trades | Wins  | Losses | Win Rate (%) | % Total Losses | Cluster Tag");
   Print("   --------------------------------------------------------------------------------------");
   double tr_floors[5] = {0.0, 1.0, 2.5, 5.0, 10.0};
   double tr_caps[5]   = {1.0, 2.5, 5.0, 10.0, 9999.0};
   string tr_labels[5] = {"$0.00 - $1.00 (Flat)", "$1.00 - $2.50 (Mod)", "$2.50 - $5.00 (Strong)", "$5.00 - $10.00 (Very Strong)", "> $10.00 (Extended)"};

   for(int b = 0; b < 5; b++)
   {
      int b_trades = 0, b_wins = 0, b_losses = 0;
      for(int r = 0; r < total_trades; r++)
      {
         if(records[r].trend_strength >= tr_floors[b] && records[r].trend_strength < tr_caps[b])
         {
            b_trades++;
            if(records[r].is_win) b_wins++;
            if(records[r].is_loss) b_losses++;
         }
      }
      double wr = (b_trades > 0) ? ((double)b_wins / b_trades) * 100.0 : 0.0;
      double ls = (total_losses > 0) ? ((double)b_losses / total_losses) * 100.0 : 0.0;
      string tag = (wr < 46.0 && b_losses > 300) ? "🔴 TOXIC LOSS CLUSTER" : ((wr > 54.0) ? "🟢 WINNING CLUSTER" : "");
      PrintFormat("   %-16s | %6d | %5d | %6d |    %5.1f%%   |     %5.1f%%    | %s",
                  tr_labels[b], b_trades, b_wins, b_losses, wr, ls, tag);
   }

   Print("=========================================================================================");
   Print(" 🔬 PHASE 2 LOSS CLUSTER ANALYSIS COMPLETED SUCCESSFULLY!");
   Print("=========================================================================================");
}
//+------------------------------------------------------------------+
