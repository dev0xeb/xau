//+------------------------------------------------------------------+
//| MQL5 Helper to match Exit Deal to Entry Comment (TP1/TP2/TP3)    |
//+------------------------------------------------------------------+

string GetEntryCommentForPosition(ulong position_id)
{
   int total_deals = HistoryDealsTotal();
   for(int i = 0; i < total_deals; i++)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket <= 0) continue;
      if(HistoryDealGetInteger(ticket, DEAL_POSITION_ID) == position_id)
      {
         long entry_type = HistoryDealGetInteger(ticket, DEAL_ENTRY);
         if(entry_type == DEAL_ENTRY_IN)
         {
            return HistoryDealGetString(ticket, DEAL_COMMENT);
         }
      }
   }
   return "";
}
