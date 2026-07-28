//+------------------------------------------------------------------+
//|                                             TelegramNotifier.mqh |
//|                     Copyright 2026, TG Capital EA Development    |
//+------------------------------------------------------------------+
#property strict

#include "Logger.mqh"

class CTelegramNotifier
  {
private:
   bool     m_enabled;
   string   m_bot_token;
   string   m_chat_id;
   CLogger* m_logger;

public:
   CTelegramNotifier(bool enabled = true, string bot_token = "", string chat_id = "", CLogger* logger = NULL)
     : m_enabled(enabled), m_bot_token(bot_token), m_chat_id(chat_id), m_logger(logger)
     {
     }

   bool SendTelegramMessage(const string text)
     {
      if(!m_enabled || m_bot_token == "" || m_chat_id == "")
         return false;

      string url = StringFormat("https://api.telegram.org/bot%s/sendMessage", m_bot_token);
      string headers = "Content-Type: application/json\r\n";
      
      // Escape string for JSON
      string clean_text = text;
      StringReplace(clean_text, "\"", "\\\"");
      StringReplace(clean_text, "\n", "\\n");

      string body = StringFormat("{\"chat_id\":\"%s\",\"text\":\"%s\",\"parse_mode\":\"HTML\"}", m_chat_id, clean_text);

      char post_data[];
      char result_data[];
      string result_headers;

      StringToCharArray(body, post_data, 0, WHOLE_ARRAY, CP_UTF8);
      // Remove trailing null byte
      if(ArraySize(post_data) > 0 && post_data[ArraySize(post_data)-1] == 0)
         ArrayResize(post_data, ArraySize(post_data)-1);

      ResetLastError();
      int res = WebRequest("POST", url, headers, 10000, post_data, result_data, result_headers);
      if(res == 200)
        {
         if(m_logger)
            m_logger.Info("Telegram alert notification sent successfully.");
         return true;
        }
      else
        {
         if(m_logger)
            m_logger.Error(StringFormat("Failed to send Telegram notification. WebRequest result: %d, Error: %d", res, GetLastError()));
         return false;
        }
     }
  };
