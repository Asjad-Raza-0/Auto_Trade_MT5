//+------------------------------------------------------------------+
//|                                                    DataCache.mqh |
//|                     Copyright 2026, TG Capital EA Development    |
//+------------------------------------------------------------------+
#property strict

#include "Logger.mqh"

class CDataCache
  {
private:
   CLogger* m_logger;

public:
   CDataCache(CLogger* logger = NULL) : m_logger(logger)
     {
     }

   // Copy historical rates into MqlRates array
   bool GetRates(const string symbol, const ENUM_TIMEFRAMES timeframe, const int count, MqlRates &rates[])
     {
      ArraySetAsSeries(rates, true);
      int copied = CopyRates(symbol, timeframe, 0, count, rates);
      if(copied < count)
        {
         if(m_logger)
            m_logger.Error(StringFormat("[%s][%s] Failed to copy rates (Requested: %d, Copied: %d)",
                                        symbol, EnumToString(timeframe), count, copied));
         return false;
        }
      return true;
     }

   // Copy indicator buffer into double array
   bool GetBuffer(const int handle, const int buffer_num, const int count, double &buffer[])
     {
      if(handle == INVALID_HANDLE)
        {
         if(m_logger)
            m_logger.Error("Invalid indicator handle provided to GetBuffer");
         return false;
        }
      ArraySetAsSeries(buffer, true);
      int copied = CopyBuffer(handle, buffer_num, 0, count, buffer);
      if(copied < count)
        {
         if(m_logger)
            m_logger.Error(StringFormat("Failed to copy indicator buffer %d (Requested: %d, Copied: %d)",
                                        buffer_num, count, copied));
         return false;
        }
      return true;
     }
  };
