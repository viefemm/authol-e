// Driver: owns the wall-clock boundary (NTP sync) and the deep-sleep exit.
// Pure window math lives in domain::Schedule; this class only touches time
// hardware and the sleep peripheral.
#pragma once

#include <Arduino.h>
#include <time.h>

class TimeDriver
{
public:
  // Blocking NTP sync with serial progress (called from boot only).
  bool beginSync();
  bool now(struct tm &out, uint32_t timeoutMs = 1000) const;
  bool inWindow(const struct tm &ti, int startHour, int endHour) const;
  // Computes the nap via domain math, arms the timer, sleeps. Never returns.
  void sleepUntilNextWindow(int startHour) const;
};
