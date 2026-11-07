// Driver: owns the HTTP/TLS platform boundary (ESP32 HTTPClient +
// WiFiClientSecure) dan kedua cookie policy. Services own URLs, payloads,
// dan policy; kelas ini hanya memindahkan byte dan menjaga serial diagnostics.
#pragma once

#include <Arduino.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>

enum class CookiePolicy
{
  None,      // no Cookie header is sent
  MisManual, // MIS/CAS manual cookie string (single-host CAS flow)
  EtholJar   // ETHOL CookieJar replay (captures ALL Set-Cookie headers)
};

struct HttpResult
{
  int code = 0;
  String body;
  String location;
};

class HttpTransport
{
public:
  explicit HttpTransport(const String &tag = "");

  void setTag(const String &tag) { tag_ = tag; }
  const String &tag() const { return tag_; }

  static void initLock();

  // Testing only: skip certificate verification (production: pin a root CA).
  void beginInsecure();

  HttpResult get(const String &label, const String &url, CookiePolicy policy);

  // customHeaderName / customHeaderVal: header tambahan opsional (misal
  // "Authorization" untuk Fonnte). Dikosongkan berarti tidak dikirim.
  HttpResult post(const String &label, const String &url, const String &body,
                  const String &contentType, CookiePolicy policy,
                  const String &referer = "",
                  const String &customHeaderName = "",
                  const String &customHeaderVal = "");

  void clearMisCookies();
  void clearEtholCookies();

private:
  String tag_;
  WiFiClientSecure client_;
  HTTPClient http_;
  const char *keys_[2];
  String misCookies_;
  String etholMirror_; // debug mirror only; replay goes through etholJar_
  CookieJar etholJar_;

  static SemaphoreHandle_t netMutex_;

  void storeMisCookies();
  void storeEtholCookies();
  void log(const String &msg);
};

