// SPDX-License-Identifier: GPL-2.0-only
#include "psf.hpp"

#include <cstring>

namespace gow3::psf {
namespace {

constexpr std::uint16_t fmt_string_special = 0x0004;
constexpr std::uint16_t fmt_string = 0x0204;
constexpr std::uint16_t fmt_integer = 0x0404;

std::uint32_t u32(const std::string& d, size_t at)
{
	return static_cast<std::uint8_t>(d[at]) | static_cast<std::uint8_t>(d[at + 1]) << 8 |
	       static_cast<std::uint8_t>(d[at + 2]) << 16 | static_cast<std::uint32_t>(static_cast<std::uint8_t>(d[at + 3])) << 24;
}

std::uint16_t u16(const std::string& d, size_t at)
{
	return static_cast<std::uint16_t>(static_cast<std::uint8_t>(d[at]) | static_cast<std::uint8_t>(d[at + 1]) << 8);
}

void put32(std::string& d, std::uint32_t v)
{
	for (int i = 0; i < 4; i++)
		d.push_back(static_cast<char>((v >> (8 * i)) & 0xff));
}

void put16(std::string& d, std::uint16_t v)
{
	d.push_back(static_cast<char>(v & 0xff));
	d.push_back(static_cast<char>(v >> 8));
}

std::optional<Map> fail(std::string* error, const char* message)
{
	if (error)
		*error = message;
	return std::nullopt;
}

} // namespace

std::optional<Map> parse(const std::string& data, std::string* error)
{
	if (data.size() < 20 || std::memcmp(data.data(), "\0PSF", 4) != 0)
		return fail(error, "não é um arquivo PARAM.SFO (assinatura PSF ausente)");
	const std::uint32_t key_table = u32(data, 8), data_table = u32(data, 12), count = u32(data, 16);
	if (20ull + count * 16ull > data.size() || key_table > data.size() || data_table > data.size())
		return fail(error, "PARAM.SFO truncado ou corrompido");

	Map result;
	for (std::uint32_t i = 0; i < count; i++) {
		const size_t entry = 20 + size_t{i} * 16;
		const size_t key_start = size_t{key_table} + u16(data, entry);
		const std::uint16_t fmt = u16(data, entry + 2);
		const std::uint32_t size = u32(data, entry + 4), max_size = u32(data, entry + 8);
		const size_t start = size_t{data_table} + u32(data, entry + 12);
		const size_t key_end = data.find('\0', key_start);
		if (key_start >= data.size() || key_end == std::string::npos)
			return fail(error, "tabela de chaves corrompida");
		if (size > max_size || start + size > data.size())
			return fail(error, "valor fora dos limites do arquivo");
		std::string key = data.substr(key_start, key_end - key_start);
		if (fmt == fmt_integer) {
			if (size != 4)
				return fail(error, "inteiro com tamanho inválido");
			result[key] = u32(data, start);
		} else if (fmt == fmt_string || fmt == fmt_string_special) {
			std::string value = data.substr(start, size);
			value = value.substr(0, value.find('\0'));
			result[key] = value;
		} else {
			return fail(error, "formato de entrada desconhecido");
		}
	}
	return result;
}

std::string build(const Map& entries)
{
	std::string keys, values, table;
	for (const auto& [key, value] : entries) {
		const auto key_off = static_cast<std::uint16_t>(keys.size());
		keys += key;
		keys.push_back('\0');
		std::string raw;
		std::uint16_t fmt;
		std::uint32_t size, max_size;
		if (const auto* number = std::get_if<std::uint32_t>(&value)) {
			put32(raw, *number);
			fmt = fmt_integer;
			size = max_size = 4;
		} else {
			raw = std::get<std::string>(value);
			raw.push_back('\0');
			fmt = fmt_string;
			size = static_cast<std::uint32_t>(raw.size());
			max_size = (size + 3) & ~3u;
			raw.resize(max_size, '\0');
		}
		put16(table, key_off);
		put16(table, fmt);
		put32(table, size);
		put32(table, max_size);
		put32(table, static_cast<std::uint32_t>(values.size()));
		values += raw;
	}
	while (keys.size() % 4)
		keys.push_back('\0');
	std::string out("\0PSF", 4);
	put32(out, 0x0101);
	put32(out, static_cast<std::uint32_t>(20 + table.size()));
	put32(out, static_cast<std::uint32_t>(20 + table.size() + keys.size()));
	put32(out, static_cast<std::uint32_t>(entries.size()));
	return out + table + keys + values;
}

std::string get_string(const Map& map, const std::string& key)
{
	const auto it = map.find(key);
	if (it == map.end())
		return {};
	if (const auto* text = std::get_if<std::string>(&it->second))
		return *text;
	return std::to_string(std::get<std::uint32_t>(it->second));
}

} // namespace gow3::psf
