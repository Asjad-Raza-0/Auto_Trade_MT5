//+------------------------------------------------------------------+
//|                                         VisualizationManager.mqh |
//|                     Copyright 2026, TG Capital EA Development    |
//+------------------------------------------------------------------+
#property strict

#include "Constants.mqh"
#include "Enums.mqh"
#include "FVGDetector.mqh"
#include "DojiDetector.mqh"

class CVisualizationManager
  {
private:
   bool m_enabled;

public:
   CVisualizationManager(bool enabled = true) : m_enabled(enabled)
     {
     }

   void SetEnabled(bool enabled) { m_enabled = enabled; }

   void DrawFVG(const string symbol, const SFVGPattern &fvg)
     {
      if(!m_enabled) return;
      string rect_name = OBJ_PREFIX + symbol + "_FVG_Rect";
      string ce_name   = OBJ_PREFIX + symbol + "_FVG_CE";

      // Draw FVG Rectangle
      if(ObjectFind(0, rect_name) < 0)
         ObjectCreate(0, rect_name, OBJ_RECTANGLE, 0, fvg.candle_c_time, fvg.top, TimeCurrent() + 86400, fvg.bottom);
      else
        {
         ObjectSetInteger(0, rect_name, OBJPROP_TIME+1, TimeCurrent() + 86400);
         ObjectSetDouble(0, rect_name, OBJPROP_PRICE+0, fvg.top);
         ObjectSetDouble(0, rect_name, OBJPROP_PRICE+1, fvg.bottom);
        }
      ObjectSetInteger(0, rect_name, OBJPROP_COLOR, clrCornflowerBlue);
      ObjectSetInteger(0, rect_name, OBJPROP_STYLE, STYLE_SOLID);
      ObjectSetInteger(0, rect_name, OBJPROP_BACK, true);

      // Draw CE Line
      if(ObjectFind(0, ce_name) < 0)
         ObjectCreate(0, ce_name, OBJ_TREND, 0, fvg.candle_c_time, fvg.ce, TimeCurrent() + 86400, fvg.ce);
      else
        {
         ObjectSetInteger(0, ce_name, OBJPROP_TIME+1, TimeCurrent() + 86400);
         ObjectSetDouble(0, ce_name, OBJPROP_PRICE+0, fvg.ce);
         ObjectSetDouble(0, ce_name, OBJPROP_PRICE+1, fvg.ce);
        }
      ObjectSetInteger(0, ce_name, OBJPROP_COLOR, clrGold);
      ObjectSetInteger(0, ce_name, OBJPROP_STYLE, STYLE_DASH);
      ObjectSetInteger(0, ce_name, OBJPROP_WIDTH, 1);
     }

   void DrawDojiMarker(const string symbol, const SDojiPattern &doji)
     {
      if(!m_enabled) return;
      string name = OBJ_PREFIX + symbol + "_Doji";
      if(ObjectFind(0, name) < 0)
         ObjectCreate(0, name, OBJ_ARROW, 0, doji.time, doji.high + (10 * SymbolInfoDouble(symbol, SYMBOL_POINT)));
      ObjectSetInteger(0, name, OBJPROP_ARROWCODE, 161); // Circle marker
      ObjectSetInteger(0, name, OBJPROP_COLOR, clrOrange);
     }

   void DrawStateStatusText(const string symbol, const ENUM_EA_STATE state, const string extra_info = "")
     {
      if(!m_enabled) return;
      string name = OBJ_PREFIX + symbol + "_Status";
      if(ObjectFind(0, name) < 0)
         ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);

      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 20);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, 40);
      ObjectSetString(0, name, OBJPROP_TEXT, StringFormat("TG Capital Trident [%s] State: %s | %s", symbol, EnumToString(state), extra_info));
      ObjectSetInteger(0, name, OBJPROP_COLOR, clrWhite);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 10);
     }

   void ClearAllObjects(const string symbol)
     {
      ObjectsDeleteAll(0, OBJ_PREFIX + symbol);
     }
  };
