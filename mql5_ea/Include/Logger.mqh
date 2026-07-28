//+------------------------------------------------------------------+
//|                                                        Logger.mqh |
//|                     Copyright 2026, TG Capital EA Development    |
//+------------------------------------------------------------------+
#property strict

#include "Enums.mqh"

class CLogger
  {
private:
   ENUM_LOG_LEVEL m_level;
   string         m_tag;

public:
   CLogger(ENUM_LOG_LEVEL level = LOG_INFO, string tag = "TGCapital")
     : m_level(level), m_tag(tag)
     {
     }

   void SetLogLevel(ENUM_LOG_LEVEL level)
     {
      m_level = level;
     }

   void Error(const string msg)
     {
      if(m_level >= LOG_ERROR)
         PrintFormat("[%s][ERROR] %s", m_tag, msg);
     }

   void Info(const string msg)
     {
      if(m_level >= LOG_INFO)
         PrintFormat("[%s][INFO] %s", m_tag, msg);
     }

   void Debug(const string msg)
     {
      if(m_level >= LOG_DEBUG)
         PrintFormat("[%s][DEBUG] %s", m_tag, msg);
     }

   void LogTradeDetails(const string symbol, const string action, const double price, const double sl, const double lots, const double risk_pts)
     {
      if(m_level >= LOG_INFO)
        {
         PrintFormat("[%s][TRADE] %s | Action: %s | Price: %.5f | SL: %.5f | Lots: %.2f | Risk: %.1f pts",
                     m_tag, symbol, action, price, sl, lots, risk_pts);
        }
     }
  };
