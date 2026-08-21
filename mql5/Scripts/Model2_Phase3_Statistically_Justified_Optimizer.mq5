//+------------------------------------------------------------------+
//|       Model2_Phase3_Statistically_Justified_Optimizer.mq5        |
//|      Phase 3 Statistically Justified Filter Verification Engine   |
//|      Evaluates Loss-to-Win Removal Ratios Across All Candidate   |
//|      Filters on Real MT5 Data                                    |
//+------------------------------------------------------------------+
#property copyright "Antigravity Quant Research"
#property link      "https://github.com/dev0xeb/xau"
#property version   "4.00"
#property script_show_inputs

//--- Inputs
input group "=== Phase 3 Filter Optimization Configuration ==="
input string InpInputCSVFilename  = "Phase1_Trade_Forensics.csv";  // Source CSV in MQL5\Files\
input double InpMinEfficiencyRatio = 3.0;                         // Minimum Loss-to-Win Removal Ratio to PASS (Default: 3.0x)

//--- Trade Record Struct
struct Phase3Record
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
   Print(" 🔬 STARTING PHASE 3 STATISTICALLY JUSTIFIED FILTER EVALUATION");
   PrintFormat(" Source CSV: MQL5\\Files\\%s | Required Efficiency Threshold: %.1fx", InpInputCSVFilename, InpMinEfficiencyRatio);
   Print("=========================================================================================");

   int file_handle = FileOpen(InpInputCSVFilename, FILE_READ|FILE_CSV|FILE_ANSI, ',');
   if(file_handle == INVALID_HANDLE)
   {
      PrintFormat("[ERROR] Could not open %s inside MQL5\\Files\\. Run Phase 1 Forensic Auditor first.", InpInputCSVFilename);
      return;
   }

   // Skip complete 31-token Header Line
   for(int h = 0; h < 31; h++) FileReadString(file_handle);

   Phase3Record records[];
   int total_trades = 0;
   int total_wins = 0;
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
      records[idx].is_loss = (records[idx].outcome == "LOSS");

      if(records[idx].is_win) total_wins++;
      else { records[idx].is_loss = true; total_losses++; }
   }

   FileClose(file_handle);

   double baseline_wr = (total_trades > 0) ? ((double)total_wins / total_trades) * 100.0 : 0.0;

   Print("-----------------------------------------------------------------------------------------");
   PrintFormat(" 📊 BASELINE STATS: %d Total Trades | %d Wins (%.1f%% Win Rate) | %d Losses",
               total_trades, total_wins, baseline_wr, total_losses);
   Print("-----------------------------------------------------------------------------------------");
   Print(" 🔬 EVALUATING CANDIDATE FILTERS BY LOSS-TO-WIN REMOVAL RATIO:");
   Print(" Filter Name                     | Wins Cut (%) | Losses Cut (%) | Efficiency Ratio | New Win Rate (%) | Verdict");
   Print(" ---------------------------------------------------------------------------------------------------------------");

   // Helper Function Simulation Routine inside OnStart
   EvaluateCandidateFilter("1. Exclude Extension Zone ($1.00-$6.00)", records, total_trades, total_wins, total_losses, 1);
   EvaluateCandidateFilter("2. Require Trend Separation >= $2.50", records, total_trades, total_wins, total_losses, 2);
   EvaluateCandidateFilter("3. Require FVG Displacement >= $0.25", records, total_trades, total_wins, total_losses, 3);
   EvaluateCandidateFilter("4. Require Active EMA21 Slope >= $0.20", records, total_trades, total_wins, total_losses, 4);
   EvaluateCandidateFilter("5. Restrict to London & NY (06:00-17:00)", records, total_trades, total_wins, total_losses, 5);
   EvaluateCandidateFilter("6. Require ATR Regime Ratio >= 1.00", records, total_trades, total_wins, total_losses, 6);

   Print("=========================================================================================");
   Print(" 🏆 PHASE 3 EVALUATION COMPLETED!");
   Print("=========================================================================================");
}

//+------------------------------------------------------------------+
//| Filter Evaluation Subroutine                                     |
//+------------------------------------------------------------------+
void EvaluateCandidateFilter(string filter_name, const Phase3Record &records[], int total_trades, int total_wins, int total_losses, int mode)
{
   int wins_removed = 0;
   int losses_removed = 0;
   int kept_wins = 0;
   int kept_losses = 0;

   for(int r = 0; r < total_trades; r++)
   {
      bool pass_filter = true;

      if(mode == 1) // Exclude EMA Extension Zone $1.00 - $6.00
      {
         if(records[r].ext_from_ema21 >= 1.00 && records[r].ext_from_ema21 <= 6.00)
            pass_filter = false;
      }
      else if(mode == 2) // Require Trend Separation >= $2.50
      {
         if(records[r].trend_strength < 2.50)
            pass_filter = false;
      }
      else if(mode == 3) // Require FVG Displacement >= $0.25 (25.0 pips)
      {
         if(records[r].fvg_size_pips < 25.0)
            pass_filter = false;
      }
      else if(mode == 4) // Require Active EMA21 Slope >= $0.20
      {
         if(records[r].ema21_slope < 0.20)
            pass_filter = false;
      }
      else if(mode == 5) // Restrict to London & NY (06:00 - 17:00 UTC)
      {
         if(records[r].hour_utc < 6 || records[r].hour_utc >= 17)
            pass_filter = false;
      }
      else if(mode == 6) // Require ATR Regime >= 1.00
      {
         if(records[r].atr_regime < 1.00)
            pass_filter = false;
      }

      if(!pass_filter)
      {
         if(records[r].is_win) wins_removed++;
         if(records[r].is_loss) losses_removed++;
      }
      else
      {
         if(records[r].is_win) kept_wins++;
         if(records[r].is_loss) kept_losses++;
      }
   }

   double win_cut_pct  = (total_wins > 0) ? ((double)wins_removed / total_wins) * 100.0 : 0.0;
   double loss_cut_pct = (total_losses > 0) ? ((double)losses_removed / total_losses) * 100.0 : 0.0;
   double ratio        = (win_cut_pct > 0) ? (loss_cut_pct / win_cut_pct) : (loss_cut_pct > 0 ? 99.9 : 0.0);

   int total_kept = kept_wins + kept_losses;
   double new_wr = (total_kept > 0) ? ((double)kept_wins / total_kept) * 100.0 : 0.0;

   string verdict = (ratio >= InpMinEfficiencyRatio) ? "✅ PASSED (STATISTICALLY JUSTIFIED)" : "❌ REJECTED (INEFFICIENT)";

   PrintFormat(" %-30s |  %4d (%4.1f%%) |   %5d (%5.1f%%) |      %5.2fx       |      %5.1f%%      | %s",
               filter_name, wins_removed, win_cut_pct, losses_removed, loss_cut_pct, ratio, new_wr, verdict);
}
//+------------------------------------------------------------------+
