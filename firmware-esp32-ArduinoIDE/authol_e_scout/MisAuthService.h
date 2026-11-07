// Service: owns the MIS CAS login workflow (validate -> ticket -> session).
// Transport and cookie storage live in HttpTransport; URLs, payloads, and
// the logout check live here.
#pragma once

#include <Arduino.h>

class HttpTransport;

class MisAuthService
{
public:
  explicit MisAuthService(HttpTransport &transport);

  // Full CAS login. Clears stale MIS cookies first. True when the landing
  // page contains "logout".
  bool login(const String &username, const String &password);

private:
  HttpTransport &transport_;
};
