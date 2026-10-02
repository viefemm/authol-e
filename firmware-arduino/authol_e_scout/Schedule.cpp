// Domain: pure schedule rules (see Schedule.h).
#include "Schedule.h"

namespace domain {

bool inLectureWindow(int wday, int hour, int startHour, int endHour)
{
  if (wday < 1 || wday > 5)
    return false; // Sabtu-Minggu libur
  return hour >= startHour && hour < endHour;
}

long secondsUntilNextWindow(int wday, long secsSinceMidnight, int startHour)
{
  const long startSec = (long)startHour * 3600;
  if (wday >= 1 && wday <= 5 && secsSinceMidnight < startSec)
    return startSec - secsSinceMidnight;
  int addDays = 1, ndw = (wday + 1) % 7;
  while (ndw == 0 || ndw == 6)
  {
    addDays++;
    ndw = (ndw + 1) % 7;
  }
  return (86400L - secsSinceMidnight) + (long)(addDays - 1) * 86400L + startSec;
}

} // namespace domain
