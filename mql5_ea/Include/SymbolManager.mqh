//+------------------------------------------------------------------+
//|                                                SymbolManager.mqh |
//|                     Copyright 2026, TG Capital EA Development    |
//+------------------------------------------------------------------+
#property strict

#include "Logger.mqh"

class CSymbolManager
  {
private:
   string   m_symbols[];
   int      m_total_symbols;
   CLogger* m_logger;

public:
   CSymbolManager(CLogger* logger = NULL) : m_total_symbols(0), m_logger(logger)
     {
     }

   bool ParseSymbolsList(const string symbols_csv)
     {
      string temp_list = symbols_csv;
      StringReplace(temp_list, " ", "");
      StringSplit(temp_list, ',', m_symbols);
      m_total_symbols = ArraySize(m_symbols);

      if(m_total_symbols <= 0)
        {
         if(m_logger)
            m_logger.Error("Symbols list is empty.");
         return false;
        }

      // Automatically call SymbolSelect for every symbol
      for(int i = 0; i < m_total_symbols; i++)
        {
         if(!SymbolSelect(m_symbols[i], true))
           {
            if(m_logger)
               m_logger.Error(StringFormat("Failed to select symbol in Market Watch: %s", m_symbols[i]));
           }
         else
           {
            if(m_logger)
               m_logger.Info(StringFormat("Symbol selected & loaded: %s", m_symbols[i]));
           }
        }
      return true;
     }

   int GetTotalSymbols() const { return m_total_symbols; }

   string GetSymbol(const int index) const
     {
      if(index >= 0 && index < m_total_symbols)
         return m_symbols[index];
      return "";
     }
  };
