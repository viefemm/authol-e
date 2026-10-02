#pragma once

#include <Arduino.h>

class GitHubDispatcher {
public:
  GitHubDispatcher(const String &repo, const String &token);

  // Memicu GitHub Actions workflow melalui repository_dispatch API
  bool triggerPresensi(const String &matkul, const String &kuliahId);

private:
  String repo_;
  String token_;
};
