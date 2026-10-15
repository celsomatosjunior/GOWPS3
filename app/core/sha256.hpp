// SPDX-License-Identifier: GPL-2.0-only
// SHA-256 (FIPS 180-4) para verificar a integridade dos arquivos do jogo e do runtime.
#pragma once

#include <array>
#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>
#include <string_view>

namespace gow3 {

class Sha256 {
public:
	Sha256();
	void update(const void* data, size_t size);
	std::array<std::uint8_t, 32> finish();
	static std::string hex(std::string_view data);

private:
	void block(const std::uint8_t* chunk);
	std::array<std::uint32_t, 8> state_{};
	std::array<std::uint8_t, 64> buffer_{};
	size_t buffered_ = 0;
	std::uint64_t length_ = 0;
};

std::string to_hex(const std::array<std::uint8_t, 32>& digest);
std::optional<std::string> sha256_file(const std::filesystem::path& path);

} // namespace gow3
