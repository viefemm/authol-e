// Domain: pure schedule rules for the 24/5 lecture window.
// Inputs are plain integers so the rules stay testable without hardware clocks.
#pragma once

#include <Arduino.h>

namespace domain {

// Senin-Jumat (wday 1-5), pukul [startHour, endHour).
bool inLectureWindow(int wday, int hour, int startHour, int endHour);

// Seconds from (wday, secsSinceMidnight) until the next window start.
// Pure companion of the deep-sleep path; hardware sleep stays in the driver.
long secondsUntilNextWindow(int wday, long secsSinceMidnight, int startHour);

} // namespace domain
