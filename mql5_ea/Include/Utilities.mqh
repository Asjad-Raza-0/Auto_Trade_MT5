//+------------------------------------------------------------------+
//|                                                     Utilities.mqh |
//|                     Copyright 2026, TG Capital EA Development    |
//+------------------------------------------------------------------+
#property strict

class CUtilities
  {
public:
   // Detect if symbol is Gold
   static bool IsGold(const string symbol)
     {
      string s = symbol;
      StringToUpper(s);
      return (StringFind(s, "XAU") >= 0 || StringFind(s, "GOLD") >= 0);
     }

   // Normalize Price according to symbol digits
   static double NormalizePrice(const string symbol, const double price)
     {
      int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
      return NormalizeDouble(price, digits);
     }

   // Get Pip Value Size in Price
   static double GetPipSize(const string symbol)
     {
      if(IsGold(symbol))
         return 0.01;
      int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
      if(digits == 3 || digits == 5)
         return SymbolInfoDouble(symbol, SYMBOL_POINT) * 10.0;
      return SymbolInfoDouble(symbol, SYMBOL_POINT);
     }

   // Calculate Price Distance in Points
   static double CalculatePointsDistance(const string symbol, const double price1, const double price2)
     {
      double diff = MathAbs(price1 - price2);
      if(IsGold(symbol))
         return NormalizeDouble(diff * 100.0, 2);
      double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
      if(point <= 0)
         point = 0.00001;
      return NormalizeDouble(diff / point, 2);
     }

   // Calculate Price Distance in Pips
   static double CalculatePipsDistance(const string symbol, const double price1, const double price2)
     {
      double pip_size = GetPipSize(symbol);
      if(pip_size <= 0)
         pip_size = 0.0001;
      return NormalizeDouble(MathAbs(price1 - price2) / pip_size, 2);
     }

   // Floor Lot Size to respect Broker Lot Step
   static double NormalizeLotSize(const string symbol, const double raw_lot)
     {
      double min_lot = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
      double max_lot = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
      double lot_step = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);

      if(lot_step <= 0)
         lot_step = 0.01;

      // Always floor lot size to avoid exceeding requested risk %
      double steps = MathFloor(raw_lot / lot_step);
      double floored_lot = NormalizeDouble(steps * lot_step, 2);

      if(floored_lot < min_lot)
         return 0.0; // Reject if floored lot is less than minimum lot
      if(floored_lot > max_lot)
         floored_lot = max_lot;

      return floored_lot;
     }

   // Generate Unique FVG ID string
   static string GenerateFVGID(const string symbol, const datetime candle_c_time, const double top, const double bottom)
     {
      return StringFormat("FVG_%s_%s_%.5f_%.5f", symbol, TimeToString(candle_c_time, TIME_DATE|TIME_MINUTES), top, bottom);
     }
  };
