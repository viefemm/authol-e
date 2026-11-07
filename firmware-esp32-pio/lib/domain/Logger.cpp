// Domain: thread-safe Serial logger (lihat Logger.h).
#include "Logger.h"

#include <stdarg.h>

namespace domain {

SemaphoreHandle_t Logger::mutex_ = nullptr;

void Logger::init()
{
  if (!mutex_)
  {
    mutex_ = xSemaphoreCreateMutex();
  }
}

void Logger::log(const String &tag, const String &msg)
{
  if (mutex_)
    xSemaphoreTake(mutex_, portMAX_DELAY);

  if (tag.length() > 0)
  {
    Serial.print("[" + tag + "] ");
  }
  Serial.println(msg);

  if (mutex_)
    xSemaphoreGive(mutex_);
}

void Logger::logf(const String &tag, const char *fmt, ...)
{
  va_list args;
  va_start(args, fmt);
  char buf[384];
  vsnprintf(buf, sizeof(buf), fmt, args);
  va_end(args);

  log(tag, String(buf));
}

} // namespace domain
