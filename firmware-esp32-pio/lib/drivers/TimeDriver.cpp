// Driver: wall-clock boundary (see TimeDriver.h).
#include "TimeDriver.h"

#include <Schedule.h>
#include <esp_sleep.h>

bool TimeDriver::beginSync()
{
  configTime(0, 0, "pool.ntp.org", "time.google.com", "id.pool.ntp.org");
  setenv("TZ", "WIB-7", 1);
  tzset();
  struct tm ti;
  for (int i = 0; i < 6; i++)
  {
    if (getLocalTime(&ti, 2000))
    {
      Serial.printf("Waktu: %02d-%02d-%04d %02d:%02d:%02d WIB (wday=%d)\n",
                    ti.tm_mday, ti.tm_mon + 1, ti.tm_year + 1900,
                    ti.tm_hour, ti.tm_min, ti.tm_sec, ti.tm_wday);
      return true;
    }
    Serial.println("NTP sync...");
  }
  Serial.println("NTP GAGAL");
  return false;
}

bool TimeDriver::now(struct tm &out, uint32_t timeoutMs) const
{
  return getLocalTime(&out, timeoutMs);
}

bool TimeDriver::inWindow(const struct tm &ti, int startHour, int endHour) const
{
  return domain::inLectureWindow(ti.tm_wday, ti.tm_hour, startHour, endHour);
}

void TimeDriver::sleepUntilNextWindow(int startHour) const
{
  struct tm ti;
  if (!getLocalTime(&ti, 1000))
  {
    Serial.println("Jam tidak valid, sleep 10 menit lalu cek lagi");
    esp_sleep_enable_timer_wakeup(600ULL * 1000000ULL);
    Serial.flush();
    esp_deep_sleep_start();
  }
  const long nowSec = ti.tm_hour * 3600 + ti.tm_min * 60 + ti.tm_sec;
  long sleepSec = domain::secondsUntilNextWindow(ti.tm_wday, nowSec, startHour) + 30;
  Serial.printf("Di luar jadwal, deep sleep %ld detik\n", sleepSec);
  Serial.flush();
  esp_sleep_enable_timer_wakeup((uint64_t)sleepSec * 1000000ULL);
  esp_deep_sleep_start();
}
