//+------------------------------------------------------------------+
//|                                                  FVGDetector.mqh |
//|                     Copyright 2026, TG Capital EA Development    |
//+------------------------------------------------------------------+
#property strict

#include "Logger.mqh"
#include "DataCache.mqh"
#include "Utilities.mqh"

struct SFVGPattern
  {
   string   id;
   string   symbol;
   datetime candle_c_time;
   double   top;    // Low of Candle C
   double   bottom; // High of Candle A
   double   size;   // Top - Bottom
   double   ce;     // Consequent Encroachment = (Top + Bottom) / 2
   bool     valid;
  };

class CFVGDetector
  {
private:
   CLogger*   m_logger;
   CDataCache* m_cache;

public:
   CFVGDetector(CDataCache* cache, CLogger* logger = NULL)
     : m_cache(cache), m_logger(logger)
     {
     }

   // Detect Bullish Fair Value Gap across 3 completed M30 candles: A (index 3), B (index 2), C (index 1)
   bool DetectBullishFVG(const string symbol, SFVGPattern &out_fvg)
     {
      MqlRates rates[];
      if(!m_cache.GetRates(symbol, PERIOD_M30, 10, rates))
         return false;

      // Search recent completed candles for newest valid Bullish FVG
      for(int i = 1; i <= 5; i++)
        {
         double high_a = rates[i + 2].high; // Candle A (oldest)
         double low_c  = rates[i].low;      // Candle C (newest)

         if(high_a < low_c)
           {
            out_fvg.top = low_c;
            out_fvg.bottom = high_a;
            out_fvg.size = out_fvg.top - out_fvg.bottom;
            if(out_fvg.size <= 0)
               continue;

            out_fvg.ce = (out_fvg.top + out_fvg.bottom) / 2.0;
            out_fvg.candle_c_time = rates[i].time;
            out_fvg.symbol = symbol;
            out_fvg.id = CUtilities::GenerateFVGID(symbol, out_fvg.candle_c_time, out_fvg.top, out_fvg.bottom);
            out_fvg.valid = true;
            return true;
           }
        }

      out_fvg.valid = false;
      return false;
     }
  };
