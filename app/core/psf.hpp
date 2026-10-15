// SPDX-License-Identifier: GPL-2.0-only
// PARAM.SFO (formato PSF), o mesmo lido pelo RPCS3 em rpcs3/Loader/PSF.cpp.
#pragma once

#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <variant>

namespace gow3::psf {

using Value = std::variant<std::string, std::uint32_t>;
using Map = std::map<std::string, Value>;

// Devolve nullopt e preenche `error` se o arquivo não for um PSF válido.
std::optional<Map> parse(const std::string& data, std::string* error = nullptr);
std::string build(const Map& entries); // usado pelos testes

std::string get_string(const Map& map, const std::string& key);

} // namespace gow3::psf
