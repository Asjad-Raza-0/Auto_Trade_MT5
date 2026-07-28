//+------------------------------------------------------------------+
//|                                        ConfirmationValidator.mqh |
//|                     Copyright 2026, TG Capital EA Development    |
//+------------------------------------------------------------------+
#property strict

#include "Logger.mqh"
#include "DataCache.mqh"
#include "DojiDetector.mqh"

class CConfirmationValidator
  {
private:
   CLogger*   m_logger;
   CDataCache* m_cache;

public:
   CConfirmationValidator(CDataCache* cache, CLogger* logger = NULL)
     : m_cache(cache), m_logger(logger)
     {
     }

   // Validates confirmation candle immediately following the Doji
   bool ValidateConfirmationCandle(const string symbol, const SDojiPattern &doji, string &reason)
     {
      MqlRates rates[];
      if(!m_cache.GetRates(symbol, PERIOD_M30, 20, rates))
        {
         reason = "Failed to copy rates";
         return false;
        }

      // Locate Doji index
      int doji_idx = -1;
      for(int i = 0; i < ArraySize(rates); i++)
        {
         if(rates[i].time == doji.time)
           {
            doji_idx = i;
            break;
           }
        }

      if(doji_idx <= 0) // doji_idx must be > 0 so that index doji_idx - 1 (immediately next completed candle) exists
        {
         reason = "Waiting for immediately next M30 completed candle after Doji";
         return false;
        }

      // Immediately next completed M30 candle in series order (index doji_idx - 1)
      MqlRates conf_candle = rates[doji_idx - 1];

      // Rule: Close(Confirmation) < High(Doji)
      if(conf_candle.close >= doji.high)
        {
         reason = StringFormat("Close(%.5f) >= High(Doji)(%.5f)", conf_candle.close, doji.high);
         return false;
        }

      reason = "Confirmation PASSED";
      return true;
     }
  };
