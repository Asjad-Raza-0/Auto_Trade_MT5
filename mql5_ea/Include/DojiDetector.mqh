//+------------------------------------------------------------------+
//|                                                 DojiDetector.mqh |
//|                     Copyright 2026, TG Capital EA Development    |
//+------------------------------------------------------------------+
#property strict

#include "Logger.mqh"
#include "DataCache.mqh"
#include "FVGDetector.mqh"

struct SDojiPattern
  {
   datetime time;
   double   open;
   double   high;
   double   low;
   double   close;
   bool     valid;
  };

class CDojiDetector
  {
private:
   double     m_threshold;
   CLogger*   m_logger;
   CDataCache* m_cache;

public:
   CDojiDetector(CDataCache* cache, double threshold = 0.10, CLogger* logger = NULL)
     : m_cache(cache), m_threshold(threshold), m_logger(logger)
     {
     }

   // Detect first valid Doji after FVG forms
   bool DetectFirstDojiAfterFVG(const string symbol, const SFVGPattern &fvg, SDojiPattern &out_doji)
     {
      MqlRates rates[];
      if(!m_cache.GetRates(symbol, PERIOD_M30, 20, rates))
         return false;

      // Iterate through candles after FVG Candle C time
      for(int i = ArraySize(rates) - 1; i >= 1; i--)
        {
         if(rates[i].time <= fvg.candle_c_time)
            continue;

         double high_val = rates[i].high;
         double low_val  = rates[i].low;
         double open_val = rates[i].open;
         double close_val= rates[i].close;

         double rng = high_val - low_val;
         if(rng <= 0)
            continue;

         double body = MathAbs(open_val - close_val);
         if((body / rng) <= m_threshold)
           {
            // Rule: Low(Doji) <= CE AND Close(Doji) > CE
            if(low_val <= fvg.ce && close_val > fvg.ce)
              {
               out_doji.time = rates[i].time;
               out_doji.open = open_val;
               out_doji.high = high_val;
               out_doji.low = low_val;
               out_doji.close = close_val;
               out_doji.valid = true;
               return true; // Return FIRST valid Doji only
              }
           }
        }

      out_doji.valid = false;
      return false;
     }
  };
