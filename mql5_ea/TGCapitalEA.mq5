//+------------------------------------------------------------------+
//|                                                 TGCapitalEA.mq5 |
//|                     Copyright 2026, TG Capital EA Development    |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, TG Capital EA Development"
#property link      "https://tgcapital.io"
#property version   "2.00"
#property description "TG Capital London EMA Stack + FVG Trident Strategy EA v2.0"
#property strict

// Include Modular Architecture Header Files
#include "Include/Version.mqh"
#include "Include/Constants.mqh"
#include "Include/Enums.mqh"
#include "Include/Utilities.mqh"
#include "Include/Logger.mqh"
#include "Include/BrokerInfo.mqh"
#include "Include/DataCache.mqh"
#include "Include/SymbolManager.mqh"
#include "Include/SessionManager.mqh"
#include "Include/EMAFilter.mqh"
#include "Include/FVGDetector.mqh"
#include "Include/DojiDetector.mqh"
#include "Include/ConfirmationValidator.mqh"
#include "Include/RiskManager.mqh"
#include "Include/TradeManager.mqh"
#include "Include/VisualizationManager.mqh"
#include "Include/StateMachine.mqh"
#include "Include/TelegramNotifier.mqh"

// Input Parameters
input group "--- General Settings ---"
input string          InpSymbolsList         = "XAUUSD,EURUSD,USDJPY,GBPUSD,AUDUSD,USDCAD,USDCHF,EURGBP"; // Symbols (comma separated)
input double          InpRiskPercent         = 1.0;                  // Risk % per trade
input ulong           InpMagicNumber         = DEFAULT_MAGIC_NUMBER; // Magic Number
input string          InpTradeComment        = DEFAULT_TRADE_COMMENT; // Trade Comment

input group "--- Strategy Parameters ---"
input double          InpMaxStopGold         = DEFAULT_MAX_STOP_GOLD_PTS; // Max Stop Distance Gold (Points)
input double          InpMaxStopForex        = DEFAULT_MAX_STOP_FOREX_PIPS; // Max Stop Distance Forex (Pips)
input double          InpDojiThreshold       = DEFAULT_DOJI_THRESHOLD;  // Doji Body/Range Ratio Threshold
input string          InpSessionStart        = DEFAULT_SESSION_START;    // Session Start NY (03:00)
input string          InpSessionEnd          = DEFAULT_SESSION_END;      // Session End NY (06:30)

input group "--- Visualization & Logs ---"
input bool            InpEnableVisualization = true;                     // Enable Chart Visualization
input ENUM_LOG_LEVEL  InpLogLevel            = LOG_INFO;                 // Logging Level

input group "--- Telegram Notifications ---"
input bool            InpTelegramEnabled     = false;                    // Enable Telegram Alerts
input string          InpTelegramBotToken    = "";                       // Telegram Bot Token
input string          InpTelegramChatID      = "";                       // Telegram Chat ID

// Indicator Handles Structure per Symbol
struct SSymbolHandles
  {
   string symbol;
   int    h_ema5;
   int    h_ema9;
   int    h_ema13;
   int    h_ema21;
   int    h_ema200;
  };

// Global Architecture Managers
CLogger*                g_logger = NULL;
CBrokerInfo*            g_broker_info = NULL;
CDataCache*             g_cache = NULL;
CSymbolManager*         g_symbol_mgr = NULL;
CSessionManager*        g_session_mgr = NULL;
CEMAFilter*             g_ema_filter = NULL;
CFVGDetector*           g_fvg_detector = NULL;
CDojiDetector*          g_doji_detector = NULL;
CConfirmationValidator* g_conf_validator = NULL;
CRiskManager*           g_risk_mgr = NULL;
CTradeManager*          g_trade_mgr = NULL;
CVisualizationManager*  g_viz_mgr = NULL;
CTelegramNotifier*      g_telegram = NULL;

SSymbolHandles          g_handles[];
CStateMachine*          g_state_machines[];
datetime                g_last_traded_m30_candle = 0;

// Helper: Find handles index for symbol
int FindHandlesIndex(const string symbol)
  {
   for(int i = 0; i < ArraySize(g_handles); i++)
     {
      if(g_handles[i].symbol == symbol)
         return i;
     }
   return -1;
  }

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
  {
   // 1. Initialize Logger
   g_logger = new CLogger(InpLogLevel, "TGCapitalEA");
   g_logger.Info(StringFormat("Initializing %s v%s...", EA_NAME, EA_VERSION));

   // 2. Validate Inputs
   if(InpRiskPercent <= 0 || InpRiskPercent > 50)
     {
      g_logger.Error("Invalid InpRiskPercent. Must be between 0.1 and 50.0.");
      return INIT_PARAMETERS_INCORRECT;
     }

   // 3. Initialize Core Managers
   g_broker_info    = new CBrokerInfo(g_logger);
   g_cache          = new CDataCache(g_logger);
   g_symbol_mgr     = new CSymbolManager(g_logger);
   g_session_mgr    = new CSessionManager(InpSessionStart, InpSessionEnd, g_logger);
   g_ema_filter     = new CEMAFilter(g_cache, g_logger);
   g_fvg_detector   = new CFVGDetector(g_cache, g_logger);
   g_doji_detector  = new CDojiDetector(g_cache, InpDojiThreshold, g_logger);
   g_conf_validator = new CConfirmationValidator(g_cache, g_logger);
   g_risk_mgr       = new CRiskManager(g_broker_info, InpRiskPercent, InpMaxStopGold, InpMaxStopForex, g_logger);
   g_trade_mgr      = new CTradeManager(g_broker_info, InpMagicNumber, InpTradeComment, g_logger);
   g_viz_mgr        = new CVisualizationManager(InpEnableVisualization);
   g_telegram       = new CTelegramNotifier(InpTelegramEnabled, InpTelegramBotToken, InpTelegramChatID, g_logger);

   // 4. Parse & Load Symbols
   if(!g_symbol_mgr.ParseSymbolsList(InpSymbolsList))
     {
      g_logger.Error("Failed to parse symbols list.");
      return INIT_FAILED;
     }

   int total_syms = g_symbol_mgr.GetTotalSymbols();
   ArrayResize(g_handles, total_syms);
   ArrayResize(g_state_machines, total_syms);

   // 5. Create Indicator Handles & State Machines per Symbol
   for(int i = 0; i < total_syms; i++)
     {
      string sym = g_symbol_mgr.GetSymbol(i);
      g_broker_info.InitializeSymbol(sym);

      g_handles[i].symbol   = sym;
      g_handles[i].h_ema5   = iMA(sym, PERIOD_D1, EMA_PERIOD_5, 0, MODE_EMA, PRICE_CLOSE);
      g_handles[i].h_ema9   = iMA(sym, PERIOD_D1, EMA_PERIOD_9, 0, MODE_EMA, PRICE_CLOSE);
      g_handles[i].h_ema13  = iMA(sym, PERIOD_D1, EMA_PERIOD_13, 0, MODE_EMA, PRICE_CLOSE);
      g_handles[i].h_ema21  = iMA(sym, PERIOD_D1, EMA_PERIOD_21, 0, MODE_EMA, PRICE_CLOSE);
      g_handles[i].h_ema200 = iMA(sym, PERIOD_D1, EMA_PERIOD_200, 0, MODE_EMA, PRICE_CLOSE);

      if(g_handles[i].h_ema5 == INVALID_HANDLE || g_handles[i].h_ema9 == INVALID_HANDLE ||
         g_handles[i].h_ema13 == INVALID_HANDLE || g_handles[i].h_ema21 == INVALID_HANDLE ||
         g_handles[i].h_ema200 == INVALID_HANDLE)
        {
         g_logger.Error(StringFormat("[%s] Failed to create D1 EMA indicator handles.", sym));
         return INIT_FAILED;
        }

      g_state_machines[i] = new CStateMachine(sym, g_logger);
      g_state_machines[i].ReconstructState(InpMagicNumber);
     }

   g_logger.Info("OnInit completed successfully with ZERO errors.");
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   g_logger.Info(StringFormat("Deinitializing EA (Reason code: %d)...", reason));

   // Release Indicator Handles
   for(int i = 0; i < ArraySize(g_handles); i++)
     {
      IndicatorRelease(g_handles[i].h_ema5);
      IndicatorRelease(g_handles[i].h_ema9);
      IndicatorRelease(g_handles[i].h_ema13);
      IndicatorRelease(g_handles[i].h_ema21);
      IndicatorRelease(g_handles[i].h_ema200);

      if(g_viz_mgr)
         g_viz_mgr.ClearAllObjects(g_handles[i].symbol);
     }

   // Free Manager Objects
   for(int i = 0; i < ArraySize(g_state_machines); i++)
     {
      if(g_state_machines[i] != NULL)
         delete g_state_machines[i];
     }

   if(g_logger) delete g_logger;
   if(g_broker_info) delete g_broker_info;
   if(g_cache) delete g_cache;
   if(g_symbol_mgr) delete g_symbol_mgr;
   if(g_session_mgr) delete g_session_mgr;
   if(g_ema_filter) delete g_ema_filter;
   if(g_fvg_detector) delete g_fvg_detector;
   if(g_doji_detector) delete g_doji_detector;
   if(g_conf_validator) delete g_conf_validator;
   if(g_risk_mgr) delete g_risk_mgr;
   if(g_trade_mgr) delete g_trade_mgr;
   if(g_viz_mgr) delete g_viz_mgr;
   if(g_telegram) delete g_telegram;
  }

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
  {
   datetime now_server = TimeCurrent();

   // Process symbols sequentially in configured input order
   for(int i = 0; i < g_symbol_mgr.GetTotalSymbols(); i++)
     {
      string sym = g_symbol_mgr.GetSymbol(i);
      CStateMachine* sm = g_state_machines[i];
      SSymbolStateContext* ctx = sm.GetContextPtr();
      SSymbolHandles h = g_handles[i];

      // Check current open position management
      if(g_trade_mgr.CountPositions(sym) > 0)
        {
         sm.TransitionTo(STATE_MANAGE_POSITION, "Position active");
         // Rule: Exit when completed Daily candle breaks EMA stack
         if(g_ema_filter.CheckDailyEMAExitCondition(sym, h.h_ema5, h.h_ema9, h.h_ema13, h.h_ema21))
           {
            g_trade_mgr.ClosePositions(sym, "Daily EMA Stack broken");
            sm.TransitionTo(STATE_WAIT_FOR_DAILY_FILTER, "Closed on Daily EMA stack break");
            g_viz_mgr.ClearAllObjects(sym);
           }
         continue;
        }

      // Check Daily Trend Filter
      string filter_reason;
      bool daily_ok = g_ema_filter.ValidateDailyFilter(sym, h.h_ema5, h.h_ema9, h.h_ema13, h.h_ema200, filter_reason);
      if(!daily_ok)
        {
         if(sm.GetState() != STATE_WAIT_FOR_DAILY_FILTER)
           {
            g_trade_mgr.CancelPendingOrders(sym, "Daily filter failed");
            sm.TransitionTo(STATE_WAIT_FOR_DAILY_FILTER, filter_reason);
            g_viz_mgr.ClearAllObjects(sym);
           }
         continue;
        }

      // Session Expiry Check (past 06:30 NY)
      if(g_session_mgr.IsSessionExpired(now_server))
        {
         if(g_trade_mgr.CountPendingOrders(sym) > 0)
           {
            g_trade_mgr.CancelPendingOrders(sym, "Session expired at 06:30 NY");
           }
         sm.TransitionTo(STATE_WAIT_FOR_SESSION, "Outside trading session");
         g_viz_mgr.ClearAllObjects(sym);
         continue;
        }

      // Check Trading Session (03:00 - 06:30 NY)
      if(!g_session_mgr.IsInSession(now_server))
        {
         sm.TransitionTo(STATE_WAIT_FOR_SESSION, "Waiting for 03:00 NY session start");
         continue;
        }

      // Fetch M30 rates
      MqlRates m30_rates[];
      if(!g_cache.GetRates(sym, PERIOD_M30, 2, m30_rates))
         continue;

      datetime current_m30_time = m30_rates[1].time;

      // Multi-symbol Execution Rule: Skip remaining symbols if signal already executed on current M30 candle
      if(g_last_traded_m30_candle == current_m30_time)
        {
         continue;
        }

      // Detect / Update Bullish FVG
      SFVGPattern fvg;
      if(g_fvg_detector.DetectBullishFVG(sym, fvg))
        {
         if(ctx.active_fvg.id != fvg.id)
           {
            ctx.active_fvg = fvg;
            // Cancel older pending order if a newer FVG forms
            g_trade_mgr.CancelPendingOrders(sym, "Newer Bullish FVG detected");
            sm.TransitionTo(STATE_WAIT_FOR_DOJI, "New Bullish FVG detected");
            g_viz_mgr.DrawFVG(sym, fvg);
           }
        }

      if(!ctx.active_fvg.valid)
         continue;

      // Detect Doji AFTER FVG
      SDojiPattern doji;
      if(g_doji_detector.DetectFirstDojiAfterFVG(sym, ctx.active_fvg, doji))
        {
         ctx.doji = doji;
         sm.TransitionTo(STATE_WAIT_FOR_CONFIRMATION, "Valid Doji detected");
         g_viz_mgr.DrawDojiMarker(sym, doji);
        }

      if(!ctx.doji.valid)
         continue;

      // Validate Confirmation Candle (Immediately next completed M30 candle after Doji)
      string conf_reason;
      if(g_conf_validator.ValidateConfirmationCandle(sym, ctx.doji, conf_reason))
        {
         // Calculate Stop Loss (Low of Candle B of FVG)
         double stop_loss = ctx.active_fvg.bottom;
         double entry_price = ctx.active_fvg.top;

         // Calculate Risk & Lot Size
         double lots = g_risk_mgr.CalculateLotSize(sym, entry_price, stop_loss);
         if(lots > 0)
           {
            // Expiration timestamp: 06:30 NY server time
            datetime exp_time = now_server + 12600; // ~06:30 NY expiry
            ulong ticket = g_trade_mgr.PlaceBuyLimitOrder(sym, entry_price, stop_loss, lots, exp_time);
            if(ticket > 0)
              {
               g_last_traded_m30_candle = current_m30_time;
               sm.TransitionTo(STATE_WAIT_FOR_FILL, "Placed BUY LIMIT order");

               // Optional Telegram Alert
               string alert_msg = StringFormat("🚨 <b>TGCapital EA Trade Alert</b> 🚨\nSymbol: <b>%s</b>\nBUY LIMIT: <b>%.5f</b>\nSL: <b>%.5f</b>\nLots: <b>%.2f</b>",
                                               sym, entry_price, stop_loss, lots);
               g_telegram.SendTelegramMessage(alert_msg);
              }
           }
        }

      g_viz_mgr.DrawStateStatusText(sym, sm.GetState(), filter_reason);
     }
  }

//+------------------------------------------------------------------+
//| Trade transaction event function                                 |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   // Synchronize state when orders are filled, cancelled, or positions closed
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
     {
      for(int i = 0; i < ArraySize(g_state_machines); i++)
        {
         g_state_machines[i].ReconstructState(InpMagicNumber);
        }
     }
  }
