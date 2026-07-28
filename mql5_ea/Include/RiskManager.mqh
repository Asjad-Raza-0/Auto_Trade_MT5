//+------------------------------------------------------------------+
//|                                                  RiskManager.mqh |
//|                     Copyright 2026, TG Capital EA Development    |
//+------------------------------------------------------------------+
#property strict

#include "Logger.mqh"
#include "BrokerInfo.mqh"
#include "Utilities.mqh"

class CRiskManager
  {
private:
   double       m_risk_percent;
   double       m_max_stop_gold;
   double       m_max_stop_forex;
   CBrokerInfo* m_broker_info;
   CLogger*     m_logger;

public:
   CRiskManager(CBrokerInfo* broker_info, double risk_percent = 1.0,
                double max_stop_gold = 600.0, double max_stop_forex = 100.0, CLogger* logger = NULL)
     : m_broker_info(broker_info), m_risk_percent(risk_percent),
       m_max_stop_gold(max_stop_gold), m_max_stop_forex(max_stop_forex), m_logger(logger)
     {
     }

   bool ValidateStopDistance(const string symbol, const double entry_price, const double stop_loss, string &reason)
     {
      if(entry_price <= 0 || stop_loss <= 0)
        {
         reason = "Invalid prices (<= 0)";
         return false;
        }

      double diff = MathAbs(entry_price - stop_loss);
      if(diff <= 0)
        {
         reason = "Risk distance <= 0";
         return false;
        }

      if(CUtilities::IsGold(symbol))
        {
         double points = diff * 100.0;
         if(points > m_max_stop_gold)
           {
            reason = StringFormat("Gold stop distance %.1f pts exceeds max limit of %.1f pts", points, m_max_stop_gold);
            return false;
           }
        }
      else
        {
         double pips = CUtilities::CalculatePipsDistance(symbol, entry_price, stop_loss);
         if(pips > m_max_stop_forex)
           {
            reason = StringFormat("Forex stop distance %.1f pips exceeds max limit of %.1f pips", pips, m_max_stop_forex);
            return false;
           }
        }

      reason = "Valid";
      return true;
     }

   double CalculateLotSize(const string symbol, const double entry_price, const double stop_loss)
     {
      string reason;
      if(!ValidateStopDistance(symbol, entry_price, stop_loss, reason))
        {
         if(m_logger)
            m_logger.Error(StringFormat("[%s] Risk validation failed: %s", symbol, reason));
         return 0.0;
        }

      double balance = m_broker_info.GetAccountBalance();
      double risk_money = balance * (m_risk_percent / 100.0);
      double price_diff = MathAbs(entry_price - stop_loss);

      double loss_per_lot = 0.0;
      if(CUtilities::IsGold(symbol))
        {
         loss_per_lot = price_diff * 100.0; // 100 oz contract
        }
      else
        {
         double pips = CUtilities::CalculatePipsDistance(symbol, entry_price, stop_loss);
         loss_per_lot = pips * 10.0; // Standard 100k contract ($10/pip)
        }

      if(loss_per_lot <= 0)
         return 0.0;

      double raw_lot = risk_money / loss_per_lot;
      double normalized_lot = CUtilities::NormalizeLotSize(symbol, raw_lot);

      return normalized_lot;
     }
  };
