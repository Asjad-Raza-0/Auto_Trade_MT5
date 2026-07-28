//+------------------------------------------------------------------+
//|                                                 StateMachine.mqh |
//|                     Copyright 2026, TG Capital EA Development    |
//+------------------------------------------------------------------+
#property strict

#include "Enums.mqh"
#include "Logger.mqh"
#include "FVGDetector.mqh"
#include "DojiDetector.mqh"

struct SSymbolStateContext
  {
   string         symbol;
   ENUM_EA_STATE  state;
   SFVGPattern    active_fvg;
   SDojiPattern   doji;
   datetime       last_m30_candle;
   datetime       last_d1_candle;
   ulong          pending_ticket;
   ulong          position_ticket;
   string         rejection_reason;
  };

class CStateMachine
  {
private:
   SSymbolStateContext m_context;
   CLogger*            m_logger;

public:
   CStateMachine(const string symbol = "", CLogger* logger = NULL)
     : m_logger(logger)
     {
      m_context.symbol = symbol;
      m_context.state = STATE_WAIT_FOR_DAILY_FILTER;
      m_context.pending_ticket = 0;
      m_context.position_ticket = 0;
      m_context.rejection_reason = "";
     }

   void SetSymbol(const string symbol) { m_context.symbol = symbol; }

   ENUM_EA_STATE GetState() const { return m_context.state; }

   void TransitionTo(ENUM_EA_STATE new_state, const string reason = "")
     {
      if(m_context.state != new_state)
        {
         if(m_logger)
            m_logger.Info(StringFormat("[%s] State transition: %s -> %s (%s)",
                                       m_context.symbol, EnumToString(m_context.state), EnumToString(new_state), reason));
         m_context.state = new_state;
         m_context.rejection_reason = reason;
        }
     }

   SSymbolStateContext* GetContextPtr() { return &m_context; }

   // Reconstruct state on terminal restart by scanning open positions & pending orders
   void ReconstructState(const ulong magic)
     {
      // Search active positions
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         ulong ticket = PositionGetTicket(i);
         if(ticket > 0 && PositionGetString(POSITION_SYMBOL) == m_context.symbol && PositionGetInteger(POSITION_MAGIC) == magic)
           {
            m_context.position_ticket = ticket;
            TransitionTo(STATE_MANAGE_POSITION, "Reconstructed from open position on restart");
            return;
           }
        }

      // Search pending orders
      for(int i = OrdersTotal() - 1; i >= 0; i--)
        {
         ulong ticket = OrderGetTicket(i);
         if(ticket > 0 && OrderGetString(ORDER_SYMBOL) == m_context.symbol && OrderGetInteger(ORDER_MAGIC) == magic)
           {
            m_context.pending_ticket = ticket;
            TransitionTo(STATE_WAIT_FOR_FILL, "Reconstructed from pending BuyLimit order on restart");
            return;
           }
        }
     }
  };
