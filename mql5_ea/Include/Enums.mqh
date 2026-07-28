//+------------------------------------------------------------------+
//|                                                        Enums.mqh |
//|                     Copyright 2026, TG Capital EA Development    |
//+------------------------------------------------------------------+
#property strict

// Log Levels
enum ENUM_LOG_LEVEL
  {
   LOG_NONE  = 0, // No logging
   LOG_ERROR = 1, // Errors only
   LOG_INFO  = 2, // Informational
   LOG_DEBUG = 3  // Full Debug logging
  };

// State Machine States
enum ENUM_EA_STATE
  {
   STATE_WAIT_FOR_DAILY_FILTER = 0,
   STATE_WAIT_FOR_SESSION      = 1,
   STATE_WAIT_FOR_FVG          = 2,
   STATE_WAIT_FOR_DOJI         = 3,
   STATE_WAIT_FOR_CONFIRMATION = 4,
   STATE_PLACE_PENDING_ORDER   = 5,
   STATE_WAIT_FOR_FILL         = 6,
   STATE_MANAGE_POSITION       = 7,
   STATE_EXIT                  = 8
  };
