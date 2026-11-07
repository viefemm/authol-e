// Driver: HTTP/TLS boundary (lihat HttpTransport.h).
#include "HttpTransport.h"

#include <Logger.h>

SemaphoreHandle_t HttpTransport::netMutex_ = nullptr;

void HttpTransport::initLock()
{
  if (!netMutex_)
  {
    netMutex_ = xSemaphoreCreateMutex();
  }
}

HttpTransport::HttpTransport(const String &tag) : tag_(tag)
{
  keys_[0] = "Set-Cookie";
  keys_[1] = "Location";
}

void HttpTransport::log(const String &msg)
{
  domain::Logger::log(tag_, msg);
}

void HttpTransport::beginInsecure()
{
  client_.setInsecure();
}


void HttpTransport::storeMisCookies()
{
  if (!http_.hasHeader("Set-Cookie"))
    return;
  String sc = http_.header("Set-Cookie");
  log("[Set-Cookie raw] " + sc);
  sc.replace(";", ",");
  int start = 0;
  while (start < (int)sc.length())
  {
    int end = sc.indexOf(',', start);
    if (end < 0)
      end = sc.length();
    String tok = sc.substring(start, end);
    start = end + 1;
    tok.trim();
    int eq = tok.indexOf('=');
    if (eq <= 0)
      continue;
    String name = tok.substring(0, eq);
    String pair = tok;
    name.trim();
    String lname = name;
    lname.toLowerCase();
    if (lname == "path" || lname == "expires" || lname == "domain" ||
        lname == "max-age" || lname == "secure" || lname == "httponly" ||
        lname == "samesite")
      continue;
    int pos = misCookies_.indexOf(name + "=");
    if (pos < 0)
    {
      if (misCookies_.length() > 0)
        misCookies_ += "; ";
      misCookies_ += pair;
    }
    else
    {
      int pend = misCookies_.indexOf(";", pos);
      String head = misCookies_.substring(0, pos);
      String tail = (pend >= 0) ? misCookies_.substring(pend) : "";
      misCookies_ = head + pair + tail;
    }
    log("[COOKIE] " + pair);
  }
}

void HttpTransport::storeEtholCookies()
{
  if (!http_.hasHeader("Set-Cookie"))
    return;
  String sc = http_.header("Set-Cookie");
  log("[ETHOL Set-Cookie] " + sc);
  sc.replace(";", ",");
  int start = 0;
  while (start < (int)sc.length())
  {
    int end = sc.indexOf(',', start);
    if (end < 0)
      end = sc.length();
    String tok = sc.substring(start, end);
    start = end + 1;
    tok.trim();
    int eq = tok.indexOf('=');
    if (eq <= 0)
      continue;
    String name = tok.substring(0, eq);
    String pair = tok;
    name.trim();
    String lname = name;
    lname.toLowerCase();
    if (lname == "path" || lname == "expires" || lname == "domain" ||
        lname == "max-age" || lname == "secure" || lname == "httponly" ||
        lname == "samesite")
      continue;
    int pos = etholMirror_.indexOf(name + "=");
    if (pos < 0)
    {
      if (etholMirror_.length() > 0)
        etholMirror_ += "; ";
      etholMirror_ += pair;
    }
    else
    {
      int pend = etholMirror_.indexOf(";", pos);
      String head = etholMirror_.substring(0, pos);
      String tail = (pend >= 0) ? etholMirror_.substring(pend) : "";
      etholMirror_ = head + pair + tail;
    }
    log("[ETHOL COOKIE] " + pair);
  }
}

HttpResult HttpTransport::get(const String &label, const String &url, CookiePolicy policy)
{
  if (netMutex_)
    xSemaphoreTake(netMutex_, portMAX_DELAY);

  log("[" + label + "] " + url);
  client_.setInsecure();
  client_.setTimeout(15);
  http_.setTimeout(15000);
  http_.setReuse(false);

  http_.begin(client_, url);
  http_.collectHeaders(keys_, 2);
  http_.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);
  if (policy == CookiePolicy::EtholJar)
  {
    http_.setCookieJar(&etholJar_);
    http_.addHeader("Accept", "application/json");
  }
  else
  {
    http_.resetCookieJar();
  }
  http_.addHeader("User-Agent", "Mozilla/5.0 (ESP32)");
  if (policy == CookiePolicy::MisManual && misCookies_.length())
    http_.addHeader("Cookie", misCookies_);

  HttpResult r;
  r.code = http_.GET();
  domain::Logger::logf(tag_, "  code=%d", r.code);
  if (policy == CookiePolicy::MisManual)
    storeMisCookies();
  else if (policy == CookiePolicy::EtholJar)
    storeEtholCookies();
  if (http_.hasHeader("Location"))
  {
    r.location = http_.header("Location");
    log("  Location: " + r.location);
  }
  if (r.code == 200 || r.code < 0 || (r.code >= 400 && r.code < 600))
  {
    r.body = http_.getString();
    domain::Logger::logf(tag_, "  body len=%d", r.body.length());
    if (policy == CookiePolicy::EtholJar && r.body.length())
      log("  body[:800]= " + r.body.substring(0, 800));
  }
  http_.end();
  client_.stop();

  if (netMutex_)
    xSemaphoreGive(netMutex_);

  return r;
}

HttpResult HttpTransport::post(const String &label, const String &url, const String &body,
                               const String &contentType, CookiePolicy policy,
                               const String &referer,
                               const String &customHeaderName,
                               const String &customHeaderVal)
{
  if (netMutex_)
    xSemaphoreTake(netMutex_, portMAX_DELAY);

  log("[" + label + "] " + url);
  client_.setInsecure();
  client_.setTimeout(15);
  http_.setTimeout(15000);
  http_.setReuse(false);

  http_.begin(client_, url);
  http_.collectHeaders(keys_, 2);
  http_.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);
  if (policy == CookiePolicy::EtholJar)
  {
    http_.setCookieJar(&etholJar_);
    http_.addHeader("Accept", "application/json");
  }
  else
  {
    http_.resetCookieJar();
  }
  http_.addHeader("User-Agent", "Mozilla/5.0 (ESP32)");
  http_.addHeader("Content-Type", contentType);
  if (referer.length())
    http_.addHeader("Referer", referer);
  if (policy == CookiePolicy::MisManual && misCookies_.length())
    http_.addHeader("Cookie", misCookies_);
  if (customHeaderName.length() && customHeaderVal.length())
    http_.addHeader(customHeaderName, customHeaderVal);

  HttpResult r;
  r.code = http_.POST(body);
  domain::Logger::logf(tag_, "  code=%d", r.code);
  if (policy == CookiePolicy::MisManual)
    storeMisCookies();
  else if (policy == CookiePolicy::EtholJar)
    storeEtholCookies();
  if (http_.hasHeader("Location"))
  {
    r.location = http_.header("Location");
    log("  Location: " + r.location);
  }
  r.body = http_.getString();
  if (policy == CookiePolicy::EtholJar)
    domain::Logger::logf(tag_, "  body len=%d", r.body.length());
  http_.end();
  client_.stop();

  if (netMutex_)
    xSemaphoreGive(netMutex_);

  return r;
}

void HttpTransport::clearMisCookies()
{
  misCookies_ = "";
}

void HttpTransport::clearEtholCookies()
{
  etholJar_ = CookieJar();
  etholMirror_ = "";
}

