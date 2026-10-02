// Service: ETHOL session workflow (see EtholSessionService.h).
#include "EtholSessionService.h"

#include <Logger.h>
#include <TextUtil.h>
#include "HttpTransport.h"

namespace {
constexpr const char *kValidateUrl = "https://ethol.pens.ac.id/api/auth/validasi-token";
constexpr const char *kRefreshUrl = "https://ethol.pens.ac.id/api/auth/refresh";
constexpr const char *kCasRedirectUrl = "https://ethol.pens.ac.id/api/auth/cas-redirect";
} // namespace

EtholSessionService::EtholSessionService(HttpTransport &transport) : transport_(transport)
{
}

void EtholSessionService::cacheNumber(const String &validateBody)
{
  String n = domain::jsonVal(validateBody, "nomor");
  n.trim();
  if (n.length() && studentNumber_ != n)
  {
    studentNumber_ = n;
    domain::Logger::log(transport_.tag(), "nomor mahasiswa ETHOL = " + studentNumber_);
  }
}

bool EtholSessionService::validate()
{
  HttpResult r = transport_.get("ETHOL GET", kValidateUrl, CookiePolicy::EtholJar);
  if (r.code == 200)
    cacheNumber(r.body);
  return r.code == 200;
}

bool EtholSessionService::refresh()
{
  HttpResult r = transport_.post("ETHOL POST", kRefreshUrl, "",
                                 "application/json", CookiePolicy::EtholJar);
  if (r.code != 200)
    domain::Logger::log(transport_.tag(), "  refresh body[:300]= " + r.body.substring(0, 300));
  return r.code == 200;
}

bool EtholSessionService::sso()
{
  domain::Logger::log(transport_.tag(), "--- SSO ETHOL via CAS (pakai CASTGC yang sudah ada) ---");

  HttpResult r1 = transport_.get("ETHOL GET", kCasRedirectUrl, CookiePolicy::EtholJar);
  domain::Logger::logf(transport_.tag(), "  cas-redirect code=%d", r1.code);
  if ((r1.code != 301 && r1.code != 302 && r1.code != 303 && r1.code != 307) || !r1.location.length())
  {
    domain::Logger::log(transport_.tag(), "SSO gagal langkah 1 (cas-redirect tidak redirect ke CAS)");
    return false;
  }

  domain::Logger::log(transport_.tag(), "[CAS] " + r1.location);
  // NOTE: the CAS host must only ever see MIS/CAS cookies, never ETHOL ones.
  HttpResult r2 = transport_.get("CAS", r1.location, CookiePolicy::MisManual);
  domain::Logger::logf(transport_.tag(), "  cas code=%d", r2.code);
  if (r2.code == 200)
  {
    domain::Logger::log(transport_.tag(), "CAS minta login ulang (dapat form, TGT tidak dipakai). SSO otomatis gagal.");
    return false;
  }
  if ((r2.code != 301 && r2.code != 302 && r2.code != 303 && r2.code != 307) || !r2.location.length())
  {
    domain::Logger::log(transport_.tag(), "SSO gagal langkah 2 (CAS tidak balik ke ETHOL + ticket)");
    return false;
  }

  String cur = r2.location;
  if (cur.startsWith("/"))
    cur = "https://ethol.pens.ac.id" + cur;
  for (int i = 0; i < 5; i++)
  {
    HttpResult r3 = transport_.get("ETHOL CB", cur, CookiePolicy::EtholJar);
    domain::Logger::logf(transport_.tag(), "  cb code=%d", r3.code);
    if ((r3.code == 301 || r3.code == 302 || r3.code == 303 || r3.code == 307) && r3.location.length())
    {
      cur = domain::resolveUrl(cur, r3.location);
      continue;
    }
    break;
  }

  // Same as the web app interceptor: mint the access token, then validate.
  refresh();
  const bool ok = validate();
  domain::Logger::log(transport_.tag(), ok ? "SSO ETHOL BERHASIL" : "SSO ETHOL GAGAL (validasi-token != 200)");
  return ok;
}

