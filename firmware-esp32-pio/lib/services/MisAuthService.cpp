// Service: MIS CAS login workflow (see MisAuthService.h).
#include "MisAuthService.h"

#include <Logger.h>
#include <TextUtil.h>
#include "HttpTransport.h"

MisAuthService::MisAuthService(HttpTransport &transport) : transport_(transport)
{
}

bool MisAuthService::login(const String &username, const String &password)
{
  transport_.clearMisCookies();
  String casUrl = "https://online.mis.pens.ac.id/index.php?Login=1&halAwal=1";
  String body = "";

  // 1. Landing page, follow redirects manually until the CAS form arrives.
  for (int i = 0; i < 5; i++)
  {
    HttpResult r = transport_.get("GET", casUrl, CookiePolicy::MisManual);
    if ((r.code == 301 || r.code == 302 || r.code == 303 || r.code == 307) && r.location.length())
    {
      domain::Logger::log(transport_.tag(), "  redirect -> " + r.location);
      casUrl = domain::resolveUrl(casUrl, r.location);
      body = "";
      continue;
    }
    if (r.code == 200)
      body = r.body;
    break;
  }

  if (body.length() == 0)
  {
    domain::Logger::log(transport_.tag(), "GAGAL: body kosong");
    return false;
  }
  domain::Logger::logf(transport_.tag(), "body len=%d", body.length());

  // 2. Parse lt + action. A leading "/" action belongs to the CAS host that
  // served the form (login.pens.ac.id), never to online.mis.
  String lt = domain::extract(body, "name=\"lt\" value=\"", "\"");
  String action = domain::extract(body, "action=\"", "\"");
  domain::Logger::log(transport_.tag(), "lt=" + lt);
  domain::Logger::log(transport_.tag(), "action=" + action);
  if (lt == "" || action == "")
  {
    domain::Logger::log(transport_.tag(), "GAGAL: lt/action tidak ketemu");
    return false;
  }
  action = domain::resolveUrl(casUrl, action);
  domain::Logger::log(transport_.tag(), "action_abs=" + action);

  // 3. CAS login POST.
  String payload = "username=" + domain::urlEncode(username) +
                   "&password=" + domain::urlEncode(password) +
                   "&lt=" + domain::urlEncode(lt) + "&_eventId=submit&submit=LOGIN";
  HttpResult p = transport_.post("POST", action, payload,
                                 "application/x-www-form-urlencoded",
                                 CookiePolicy::MisManual, casUrl);

  // 4. Success = redirect carrying ticket=ST- ; exchange it for the session.
  if (p.location.indexOf("ticket=ST-") < 0)
  {
    domain::Logger::log(transport_.tag(), "=== LOGIN GAGAL: tidak ada ticket ===");
    domain::Logger::log(transport_.tag(), "penyebab umum: lt kedaluwarsa / jsessionid tidak terkirim / user/pass salah");
    return false;
  }
  domain::Logger::log(transport_.tag(), "=== LOGIN SUKSES (dapat ticket) ===");
  String cur = domain::resolveUrl(casUrl, p.location);
  for (int i = 0; i < 5; i++)
  {
    domain::Logger::log(transport_.tag(), "[TUKAR] " + cur);
    HttpResult t = transport_.get("TUKAR", cur, CookiePolicy::MisManual);
    if ((t.code == 301 || t.code == 302 || t.code == 303 || t.code == 307) && t.location.length())
    {
      cur = domain::resolveUrl(cur, t.location);
      continue;
    }
    break;
  }
  domain::Logger::log(transport_.tag(), "VERIFIKASI OK: login MIS berhasil");
  return true;
}

