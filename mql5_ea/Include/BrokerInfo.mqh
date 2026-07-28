//+------------------------------------------------------------------+
//|                                                    BrokerInfo.mqh |
//|                     Copyright 2026, TG Capital EA Development    |
//+------------------------------------------------------------------+
#property strict

#include <Trade\AccountInfo.mqh>
#include <Trade\SymbolInfo.mqh>
#include "Logger.mqh"

class CBrokerInfo
  {
private:
   CSymbolInfo    m_symbol_info;
   CAccountInfo   m_account_info;
   CLogger*       m_logger;

public:
   CBrokerInfo(CLogger* logger = NULL) : m_logger(logger)
     {
     }

   bool InitializeSymbol(const string symbol)
     {
      if(!m_symbol_info.Name(symbol))
        {
         if(m_logger)
            m_logger.Error(StringFormat("Failed to initialize CSymbolInfo for symbol: %s", symbol));
         return false;
        }
      if(!m_symbol_info.RefreshRates())
        {
         if(m_logger)
            m_logger.Error(StringFormat("Failed to refresh rates for symbol: %s", symbol));
         return false;
        }
      return true;
     }

   double GetAccountBalance()
     {
      return m_account_info.Balance();
     }

   double GetAccountEquity()
     {
      return m_account_info.Equity();
     }

   int GetDigits(const string symbol)
     {
      return (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
     }

   double GetPoint(const string symbol)
     {
      return SymbolInfoDouble(symbol, SYMBOL_POINT);
     }

   double GetTickSize(const string symbol)
     {
      return SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
     }

   double GetTickValue(const string symbol)
     {
      return SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
     }

   double GetContractSize(const string symbol)
     {
      return SymbolInfoDouble(symbol, SYMBOL_TRADE_CONTRACT_SIZE);
     }

   double GetMinLot(const string symbol)
     {
      return SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
     }

   double GetMaxLot(const string symbol)
     {
      return SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
     }

   double GetLotStep(const string symbol)
     {
      return SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
     }

   // Detect execution filling mode automatically (IOC, FOK, RETURN)
   ENUM_ORDER_TYPE_FILLING GetExecutionFillingMode(const string symbol)
     {
      uint filling = (uint)SymbolInfoInteger(symbol, SYMBOL_FILLING_MODE);
      if((filling & SYMBOL_FILLING_IOC) != 0)
         return ORDER_FILLING_IOC;
      if((filling & SYMBOL_FILLING_FOK) != 0)
         return ORDER_FILLING_FOK;
      return ORDER_FILLING_RETURN;
     }
  };
