//+------------------------------------------------------------------+
//|                                                 TradeManager.mqh |
//|                     Copyright 2026, TG Capital EA Development    |
//+------------------------------------------------------------------+
#property strict

#include <Trade\Trade.mqh>
#include "Logger.mqh"
#include "BrokerInfo.mqh"

class CTradeManager
  {
private:
   CTrade       m_trade;
   ulong        m_magic_number;
   string       m_comment;
   CBrokerInfo* m_broker_info;
   CLogger*     m_logger;

public:
   CTradeManager(CBrokerInfo* broker_info, const ulong magic_number = 777999,
                 const string comment = "TGCapital_Trident_v2", CLogger* logger = NULL)
     : m_broker_info(broker_info), m_magic_number(magic_number), m_comment(comment), m_logger(logger)
     {
      m_trade.SetExpertMagicNumber(m_magic_number);
      m_trade.SetDeviationInPoints(10);
     }

   // Set auto filling mode according to broker support
   void ConfigureFillingMode(const string symbol)
     {
      ENUM_ORDER_TYPE_FILLING filling = m_broker_info.GetExecutionFillingMode(symbol);
      m_trade.SetTypeFilling(filling);
     }

   // Count open positions for symbol
   int CountPositions(const string symbol)
     {
      int count = 0;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         ulong ticket = PositionGetTicket(i);
         if(ticket > 0)
           {
            if(PositionGetString(POSITION_SYMBOL) == symbol && PositionGetInteger(POSITION_MAGIC) == m_magic_number)
               count++;
           }
        }
      return count;
     }

   // Count active pending orders for symbol
   int CountPendingOrders(const string symbol)
     {
      int count = 0;
      for(int i = OrdersTotal() - 1; i >= 0; i--)
        {
         ulong ticket = OrderGetTicket(i);
         if(ticket > 0)
           {
            if(OrderGetString(ORDER_SYMBOL) == symbol && OrderGetInteger(ORDER_MAGIC) == m_magic_number)
               count++;
           }
        }
      return count;
     }

   // Place BUY LIMIT pending order at FVG Top
   ulong PlaceBuyLimitOrder(const string symbol, const double entry_price, const double stop_loss, const double lots, const datetime expiration)
     {
      if(CountPositions(symbol) > 0 || CountPendingOrders(symbol) > 0)
        {
         if(m_logger)
            m_logger.Info(StringFormat("[%s] Pending order or open position already exists. Skipping order placement.", symbol));
         return 0;
        }

      ConfigureFillingMode(symbol);

      double norm_entry = CUtilities::NormalizePrice(symbol, entry_price);
      double norm_sl    = CUtilities::NormalizePrice(symbol, stop_loss);

      if(!m_trade.BuyLimit(lots, norm_entry, symbol, norm_sl, 0.0, ORDER_TIME_SPECIFIED, expiration, m_comment))
        {
         if(m_logger)
            m_logger.Error(StringFormat("[%s] BuyLimit failed: %d - %s", symbol, m_trade.ResultRetcode(), m_trade.ResultRetcodeDescription()));
         return 0;
        }

      ulong ticket = m_trade.ResultOrder();
      if(m_logger)
         m_logger.Info(StringFormat("[%s] Placed BUY LIMIT order #%I64u | Entry: %.5f | SL: %.5f | Lots: %.2f",
                                     symbol, ticket, norm_entry, norm_sl, lots));

      return ticket;
     }

   // Cancel all pending orders for symbol
   bool CancelPendingOrders(const string symbol, const string reason = "")
     {
      bool success = true;
      for(int i = OrdersTotal() - 1; i >= 0; i--)
        {
         ulong ticket = OrderGetTicket(i);
         if(ticket > 0)
           {
            if(OrderGetString(ORDER_SYMBOL) == symbol && OrderGetInteger(ORDER_MAGIC) == m_magic_number)
              {
               if(!m_trade.OrderDelete(ticket))
                 {
                  if(m_logger)
                     m_logger.Error(StringFormat("[%s] Failed to cancel pending order #%I64u: %s", symbol, ticket, m_trade.ResultRetcodeDescription()));
                  success = false;
                 }
               else
                 {
                  if(m_logger)
                     m_logger.Info(StringFormat("[%s] Cancelled pending order #%I64u (%s)", symbol, ticket, reason));
                 }
              }
           }
        }
      return success;
     }

   // Close open positions for symbol when Daily EMA stack breaks
   bool ClosePositions(const string symbol, const string reason = "")
     {
      bool success = true;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         ulong ticket = PositionGetTicket(i);
         if(ticket > 0)
           {
            if(PositionGetString(POSITION_SYMBOL) == symbol && PositionGetInteger(POSITION_MAGIC) == m_magic_number)
              {
               if(!m_trade.PositionClose(ticket))
                 {
                  if(m_logger)
                     m_logger.Error(StringFormat("[%s] Failed to close position #%I64u: %s", symbol, ticket, m_trade.ResultRetcodeDescription()));
                  success = false;
                 }
               else
                 {
                  if(m_logger)
                     m_logger.Info(StringFormat("[%s] Closed position #%I64u (%s)", symbol, ticket, reason));
                 }
              }
           }
        }
      return success;
     }
  };
