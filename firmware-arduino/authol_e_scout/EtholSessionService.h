// Service: owns the ETHOL session workflow (validate -> refresh -> CAS SSO).
// Re-login orchestration across MIS + ETHOL lives in the controller; this
// class exposes the single steps plus the cached student number.
#pragma once

#include <Arduino.h>

class HttpTransport;

class EtholSessionService
{
public:
  explicit EtholSessionService(HttpTransport &transport);

  // True when GET validasi-token returns 200. Caches the student number.
  bool validate();
  // POST /auth/refresh (mirrors the web app interceptor).
  bool refresh();
  // Full CAS SSO using the TGT obtained from the MIS login. Ends with a
  // refresh + validate like the web app does after its callback chain.
  bool sso();

  const String &studentNumber() const { return studentNumber_; }

private:
  HttpTransport &transport_;
  String studentNumber_;

  void cacheNumber(const String &validateBody);
};
