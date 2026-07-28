//+------------------------------------------------------------------+
//|                                                    Constants.mqh |
//|                     Copyright 2026, TG Capital EA Development    |
//+------------------------------------------------------------------+
#property strict

// Magic Number & Trade Identification
const ulong   DEFAULT_MAGIC_NUMBER      = 777999;
const string  DEFAULT_TRADE_COMMENT     = "TGCapital_Trident_v2";

// Timeframe & Session Constants
const string  SESSION_TIMEZONE          = "America/New_York";
const string  DEFAULT_SESSION_START     = "03:00";
const string  DEFAULT_SESSION_END       = "06:30";

// Indicator Default Periods
const int     EMA_PERIOD_5              = 5;
const int     EMA_PERIOD_9              = 9;
const int     EMA_PERIOD_13             = 13;
const int     EMA_PERIOD_21             = 21;
const int     EMA_PERIOD_200            = 200;

// Strategy Default Limits
const double  DEFAULT_DOJI_THRESHOLD    = 0.10;
const double  DEFAULT_MAX_STOP_GOLD_PTS = 600.0;  // 600 points = $6.00
const double  DEFAULT_MAX_STOP_FOREX_PIPS= 100.0; // 100 pips

// Visualization Object Prefixes
const string  OBJ_PREFIX                = "TGC_Trident_";
