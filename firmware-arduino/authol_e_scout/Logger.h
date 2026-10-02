// Domain: thread-safe Serial logger untuk FreeRTOS tasks.
// Menggunakan FreeRTOS Mutex agar log dari beberapa task/core
// tidak saling tumpang-tindih di UART.
#pragma once

#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

namespace domain {

class Logger
{
public:
  static void init();

  // Cetak baris log dengan tag: "[tag] pesan"
  static void log(const String &tag, const String &msg);

  // Cetak format printf dengan tag
  static void logf(const String &tag, const char *fmt, ...);

private:
  static SemaphoreHandle_t mutex_;
};

} // namespace domain
