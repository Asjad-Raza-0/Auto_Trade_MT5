//+------------------------------------------------------------------+
//|                                                    EMAFilter.mqh |
//|                     Copyright 2026, TG Capital EA Development    |
//+------------------------------------------------------------------+
#property strict

#include "Logger.mqh"
#include "DataCache.mqh"

class CEMAFilter
  {
private:
   CLogger*   m_logger;
   CDataCache* m_cache;

public:
   CEMAFilter(CDataCache* cache, CLogger* logger = NULL)
     : m_cache(cache), m_logger(logger)
     {
     }

   // Validates Daily EMA filter on completed Daily candle
   bool ValidateDailyFilter(const string symbol, int h_ema5, int h_ema9, int h_ema13, int h_ema21, int h_ema200, string &reason)
     {
      MqlRates rates[];
      if(!m_cache.GetRates(symbol, PERIOD_D1, 3, rates))
        {
         reason = "Failed to copy D1 rates";
         return false;
        }

      // Index 1 is the last COMPLETED Daily candle
      double close_d1 = rates[1].close;

      double b_ema5[], b_ema9[], b_ema13[], b_ema21[], b_ema200[];
      if(!m_cache.GetBuffer(h_ema5, 0, 3, b_ema5) ||
         !m_cache.GetBuffer(h_ema9, 0, 3, b_ema9) ||
         !m_cache.GetBuffer(h_ema13, 0, 3, b_ema13) ||
         !m_cache.GetBuffer(h_ema21, 0, 3, b_ema21) ||
         !m_cache.GetBuffer(h_ema200, 0, 3, b_ema200))
        {
         reason = "Failed to copy D1 EMA buffers";
         return false;
        }

      double v_ema5   = b_ema5[1];
      double v_ema9   = b_ema9[1];
      double v_ema13  = b_ema13[1];
      double v_ema21  = b_ema21[1];
      double v_ema200 = b_ema200[1];

      if(close_d1 <= v_ema200)
        {
         reason = StringFormat("Close(%.5f) <= EMA200(%.5f)", close_d1, v_ema200);
         return false;
        }

      if(!(v_ema5 > v_ema9 && v_ema9 > v_ema13 && v_ema13 > v_ema21))
        {
         reason = StringFormat("EMA Stack Broken: EMA5(%.5f) EMA9(%.5f) EMA13(%.5f) EMA21(%.5f)",
                               v_ema5, v_ema9, v_ema13, v_ema21);
         return false;
        }

      reason = "PASSED";
      return true;
     }

   // Checks exit condition for open trades when Daily EMA stack breaks
   bool CheckDailyEMAExitCondition(const string symbol, int h_ema5, int h_ema9, int h_ema13, int h_ema21)
     {
      double b_ema5[], b_ema9[], b_ema13[], b_ema21[];
      if(!m_cache.GetBuffer(h_ema5, 0, 3, b_ema5) ||
         !m_cache.GetBuffer(h_ema9, 0, 3, b_ema9) ||
         !m_cache.GetBuffer(h_ema13, 0, 3, b_ema13) ||
         !m_cache.GetBuffer(h_ema21, 0, 3, b_ema21))
        {
         return false;
        }

      double v_ema5  = b_ema5[1];
      double v_ema9  = b_ema9[1];
      double v_ema13 = b_ema13[1];
      double v_ema21 = b_ema21[1];

      // Exit if completed Daily candle satisfies ANY: EMA5 <= EMA9 OR EMA9 <= EMA13 OR EMA13 <= EMA21
      if(v_ema5 <= v_ema9 || v_ema9 <= v_ema13 || v_ema13 <= v_ema21)
         return true;

      return false;
     }
  };
