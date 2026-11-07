// Domain: pure string/JSON helpers (see TextUtil.h).
#include "TextUtil.h"

namespace domain {

String urlOrigin(const String &url)
{
  int p = url.indexOf("://");
  if (p < 0)
    return "";
  int s = url.indexOf("/", p + 3);
  if (s < 0)
    return url;
  return url.substring(0, s);
}

String resolveUrl(const String &base, const String &rel)
{
  if (rel.startsWith("http://") || rel.startsWith("https://"))
    return rel;
  if (rel.startsWith("/"))
    return urlOrigin(base) + rel;
  int q = base.lastIndexOf('/');
  if (q < 0)
    return rel;
  return base.substring(0, q + 1) + rel;
}

String urlEncode(const String &s)
{
  String out = "";
  for (size_t i = 0; i < s.length(); i++)
  {
    char c = s[i];
    if (isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~')
      out += c;
    else
    {
      char b[4];
      sprintf(b, "%%%02X", (uint8_t)c);
      out += b;
    }
  }
  return out;
}

String extract(const String &body, const String &start, const String &end)
{
  int a = body.indexOf(start);
  if (a < 0)
    return "";
  a += start.length();
  int b = body.indexOf(end, a);
  if (b < 0)
    return "";
  return body.substring(a, b);
}

String jsonVal(const String &body, const String &key, int from)
{
  String qk = "\"" + key + "\"";
  int a = body.indexOf(qk, from);
  if (a < 0)
    return "";
  int c = body.indexOf(':', a + qk.length());
  if (c < 0)
    return "";
  int p = c + 1;
  while (p < (int)body.length() && (body[p] == ' ' || body[p] == '\t' || body[p] == '\r' || body[p] == '\n'))
    p++;
  if (p >= (int)body.length())
    return "";
  if (body[p] == '"')
  {
    p++;
    String out = "";
    while (p < (int)body.length())
    {
      if (body[p] == '\\' && p + 1 < (int)body.length())
      {
        out += body[p + 1];
        p += 2;
        continue;
      }
      if (body[p] == '"')
        break;
      out += body[p];
      p++;
    }
    return out;
  }
  int e = p;
  while (e < (int)body.length() && body[e] != ',' && body[e] != '}' && body[e] != ']' &&
         body[e] != ' ' && body[e] != '\n' && body[e] != '\r' && body[e] != '\t')
    e++;
  return body.substring(p, e);
}

bool jsonOpenActive(const String &body)
{
  int p = 0;
  while (true)
  {
    int a = body.indexOf("\"open\"", p);
    if (a < 0)
      return false;
    int c = body.indexOf(':', a + 6);
    if (c < 0)
      return false;
    int q = c + 1;
    while (q < (int)body.length() && (body[q] == ' ' || body[q] == '\t'))
      q++;
    if (q < (int)body.length() && body[q] == '1')
      return true;
    p = c + 1;
  }
}

String jsonEscape(const String &s)
{
  String out = "";
  for (size_t i = 0; i < s.length(); i++)
  {
    char c = s[i];
    if (c == '"')
      out += "\\\"";
    else if (c == '\\')
      out += "\\\\";
    else if (c == '\n')
      out += "\\n";
    else if (c == '\r')
      out += "\\r";
    else if ((uint8_t)c < 0x20)
    {
      char b[7];
      sprintf(b, "\\u%04x", c);
      out += b;
    }
    else
      out += c;
  }
  return out;
}

String htmlEscape(const String &s)
{
  String out = "";
  for (size_t i = 0; i < s.length(); i++)
  {
    char c = s[i];
    if (c == '&')
      out += "&amp;";
    else if (c == '<')
      out += "&lt;";
    else if (c == '>')
      out += "&gt;";
    else
      out += c;
  }
  return out;
}

} // namespace domain
