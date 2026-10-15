// SPDX-License-Identifier: GPL-2.0-only
// Tipos e utilitários compartilhados pelo núcleo (sem dependência de Windows).
#pragma once

#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <string>
#include <string_view>
#include <vector>

namespace gow3 {

namespace fs = std::filesystem;

enum class Level { ok, warning, error };

struct Finding {
	Level level;
	std::string message;
};

using Findings = std::vector<Finding>;

inline bool has_error(const Findings& findings)
{
	return std::any_of(findings.begin(), findings.end(), [](const Finding& f) { return f.level == Level::error; });
}

inline const char* level_tag(Level level)
{
	switch (level) {
	case Level::ok: return "OK   ";
	case Level::warning: return "AVISO";
	default: return "ERRO ";
	}
}

std::string trim(std::string_view text);
std::string to_lower(std::string_view text);
std::vector<std::string> split(std::string_view text, char separator);

// Texto UTF-8 <-> caminho, sem perder acentos no Windows.
std::string path_to_utf8(const fs::path& path);
fs::path utf8_to_path(std::string_view text);
std::string generic_utf8(const fs::path& path); // sempre com "/"

bool read_file(const fs::path& path, std::string& out);
bool write_file(const fs::path& path, std::string_view data);

} // namespace gow3
