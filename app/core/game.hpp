// SPDX-License-Identifier: GPL-2.0-only
// Reconhecimento da cópia do God of War III fornecida pelo usuário. Só leitura: nada é
// decifrado, alterado ou copiado.
#pragma once

#include "common.hpp"

#include <map>

namespace gow3 {

// Seriais listados na wiki do RPCS3 (https://wiki.rpcs3.net/index.php?title=God_of_War_III).
extern const std::vector<std::string> known_serials;
std::string region_for_serial(std::string_view serial);
std::string firmware_from_sfo(std::string_view ps3_system_ver); // "03.1500" -> "3.15"

struct GameInfo {
	fs::path root;      // pasta escolhida
	fs::path game_dir;  // pasta com PARAM.SFO e USRDIR
	fs::path boot_path; // o que é passado ao RPCS3
	std::string serial, title, app_version, category, required_firmware, region, eboot_kind;
	Findings findings;
	bool ok() const { return !has_error(findings); }
};

GameInfo inspect_game(const fs::path& root);

// Manifesto: caminho relativo -> "tamanho sha256".
using Manifest = std::map<std::string, std::string>;
Manifest build_manifest(const fs::path& dir);
std::string serialize_manifest(const Manifest& manifest);
Manifest parse_manifest(const std::string& text);
Findings compare_manifest(const Manifest& saved, const Manifest& current);

} // namespace gow3
