// Domain: pure string/JSON helpers. No hardware, network, or SDK behavior.
// Legacy seam: uses Arduino String like the rest of the firmware so the
// functions stay drop-in. No allocation beyond returned values.
#pragma once

#include <Arduino.h>

namespace domain {

String urlOrigin(const String &url);
String resolveUrl(const String &base, const String &rel);
String urlEncode(const String &s);
String extract(const String &body, const String &start, const String &end);

// JSON value reader tolerant to spacing: "k":"v", "k": "v", numbers.
// Handles escaped quotes inside strings. Returns "" when absent.
String jsonVal(const String &body, const String &key, int from = 0);

// True when an aktif-kuliah payload contains "open": 1 (spacing tolerant).
bool jsonOpenActive(const String &body);

// Escape text for embedding in a JSON string value.
String jsonEscape(const String &s);

// Escape text for embedding in an HTML-formatted Telegram message.
String htmlEscape(const String &s);

} // namespace domain
