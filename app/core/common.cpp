// SPDX-License-Identifier: GPL-2.0-only
#include "common.hpp"

#include <cctype>
#include <fstream>
#include <sstream>

namespace gow3 {

std::string trim(std::string_view text)
{
	const auto first = text.find_first_not_of(" \t\r\n");
	if (first == std::string_view::npos)
		return {};
	const auto last = text.find_last_not_of(" \t\r\n");
	return std::string(text.substr(first, last - first + 1));
}

std::string to_lower(std::string_view text)
{
	std::string out(text);
	for (char& c : out)
		c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
	return out;
}

std::vector<std::string> split(std::string_view text, char separator)
{
	std::vector<std::string> parts;
	size_t start = 0;
	while (true) {
		const size_t pos = text.find(separator, start);
		parts.emplace_back(text.substr(start, pos == std::string_view::npos ? std::string_view::npos : pos - start));
		if (pos == std::string_view::npos)
			break;
		start = pos + 1;
	}
	return parts;
}

std::string path_to_utf8(const fs::path& path)
{
	const auto u8 = path.u8string();
	return std::string(reinterpret_cast<const char*>(u8.data()), u8.size());
}

std::string generic_utf8(const fs::path& path)
{
	const auto u8 = path.generic_u8string();
	return std::string(reinterpret_cast<const char*>(u8.data()), u8.size());
}

fs::path utf8_to_path(std::string_view text)
{
	return fs::path(std::u8string(reinterpret_cast<const char8_t*>(text.data()), text.size()));
}

bool read_file(const fs::path& path, std::string& out)
{
	std::ifstream stream(path, std::ios::binary);
	if (!stream)
		return false;
	std::ostringstream buffer;
	buffer << stream.rdbuf();
	out = buffer.str();
	return true;
}

bool write_file(const fs::path& path, std::string_view data)
{
	std::error_code ec;
	if (path.has_parent_path())
		fs::create_directories(path.parent_path(), ec);
	std::ofstream stream(path, std::ios::binary | std::ios::trunc);
	if (!stream)
		return false;
	stream.write(data.data(), static_cast<std::streamsize>(data.size()));
	return static_cast<bool>(stream);
}

} // namespace gow3
