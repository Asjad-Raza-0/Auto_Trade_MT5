//+------------------------------------------------------------------+
//|                                               SessionManager.mqh |
//|                     Copyright 2026, TG Capital EA Development    |
//+------------------------------------------------------------------+
#property strict

#include "Logger.mqh"

class CSessionManager
  {
private:
   int      m_start_hour;
   int      m_start_min;
   int      m_end_hour;
   int      m_end_min;
   CLogger* m_logger;

public:
   CSessionManager(const string start_str = "03:00", const string end_str = "06:30", CLogger* logger = NULL)
     : m_logger(logger)
     {
      ParseTime(start_str, m_start_hour, m_start_min);
      ParseTime(end_str, m_end_hour, m_end_min);
     }

   void ParseTime(const string time_str, int &hour, int &minute)
     {
      string parts[];
      if(StringSplit(time_str, ':', parts) == 2)
        {
         hour = (int)StringToInteger(parts[0]);
         minute = (int)StringToInteger(parts[1]);
        }
      else
        {
         hour = 3;
         minute = 0;
        }
     }

   // Automatic DST Detection (Returns New York UTC offset in seconds: -14400 EDT or -18000 EST)
   int GetNYUTCOffset(const datetime time_val)
     {
      MqlDateTime dt;
      TimeToStruct(time_val, dt);

      // US DST starts 2nd Sunday in March and ends 1st Sunday in November
      if(dt.mon > 3 && dt.mon < 11)
         return -14400; // EDT (UTC-4)
      if(dt.mon == 3)
        {
         // 2nd Sunday calculation
         int sunday_count = 0;
         for(int d = 1; d <= dt.day; d++)
           {
            MqlDateTime temp_dt = dt;
            temp_dt.day = d;
            datetime t_check = StructToTime(temp_dt);
            MqlDateTime res_dt;
            TimeToStruct(t_check, res_dt);
            if(res_dt.day_of_week == 0)
               sunday_count++;
           }
         if(sunday_count >= 2)
            return -14400; // EDT
        }
      if(dt.mon == 11)
        {
         // 1st Sunday calculation
         int sunday_count = 0;
         for(int d = 1; d <= dt.day; d++)
           {
            MqlDateTime temp_dt = dt;
            temp_dt.day = d;
            datetime t_check = StructToTime(temp_dt);
            MqlDateTime res_dt;
            TimeToStruct(t_check, res_dt);
            if(res_dt.day_of_week == 0)
               sunday_count++;
           }
         if(sunday_count < 1)
            return -14400; // Still EDT before 1st Sunday
        }

      return -18000; // EST (UTC-5)
     }

   // Checks if given time is within trading session (03:00 - 06:30 NY)
   bool IsInSession(const datetime current_server_time)
     {
      MqlDateTime dt;
      TimeToStruct(current_server_time, dt);

      int current_total_minutes = dt.hour * 60 + dt.min;
      int start_total_minutes = m_start_hour * 60 + m_start_min;
      int end_total_minutes = m_end_hour * 60 + m_end_min;

      return (current_total_minutes >= start_total_minutes && current_total_minutes <= end_total_minutes);
     }

   // Checks if session expired (past 06:30 NY)
   bool IsSessionExpired(const datetime current_server_time)
     {
      MqlDateTime dt;
      TimeToStruct(current_server_time, dt);

      int current_total_minutes = dt.hour * 60 + dt.min;
      int end_total_minutes = m_end_hour * 60 + m_end_min;

      return (current_total_minutes > end_total_minutes);
     }
  };
