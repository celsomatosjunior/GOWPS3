// SPDX-License-Identifier: GPL-2.0-only
#include "diagnostics.hpp"

#include <cstring>

namespace gow3 {
namespace {

// (trecho exato que aparece no log do RPCS3, explicação para o usuário)
const std::pair<const char*, const char*> known_patterns[] = {
	{"Firmware is missing",
	 "O firmware do PS3 não está instalado. Use 'Instalar firmware' com o arquivo PS3UPDAT.PUP baixado do site "
	 "oficial da PlayStation."},
	{"Firmware is too old", "O firmware instalado é mais antigo do que o jogo pede. Instale a versão mais recente."},
	{"No compatible GPU devices found", "Nenhuma placa de vídeo compatível com Vulkan foi encontrada. Atualize o driver."},
	{"VK_ERROR_OUT_OF_DEVICE_MEMORY", "Acabou a memória de vídeo (VRAM). Reduza a resolução interna."},
	{"VK_ERROR_DEVICE_LOST", "O driver de vídeo travou (device lost). Atualize o driver e tente sem overclock."},
	{"Failed to apply config: ", "O RPCS3 não aceitou o arquivo de configuração. Restaure as configurações padrão."},
	{"Invalid file or folder", "O RPCS3 não encontrou o executável do jogo na pasta escolhida."},
	{"Failed to decrypt content",
	 "O RPCS3 não conseguiu ler o executável do jogo. A cópia pode estar incompleta ou ser de outra fonte."},
	{"Missing decryption key for the disc",
	 "Esta cópia é uma imagem de disco que precisa da chave do próprio disco. Use a pasta do jogo copiada do seu PS3."},
};

const char fatal_prefix[] = "\xC2\xB7" "F ";
const char error_prefix[] = "\xC2\xB7" "E ";
const char warning_prefix[] = "\xC2\xB7" "W ";

std::uint32_t le32(const std::string& d, size_t at)
{
	if (at + 4 > d.size())
		return 0;
	return static_cast<std::uint8_t>(d[at]) | static_cast<std::uint8_t>(d[at + 1]) << 8 |
	       static_cast<std::uint8_t>(d[at + 2]) << 16 | static_cast<std::uint32_t>(static_cast<std::uint8_t>(d[at + 3])) << 24;
}

std::uint16_t le16(const std::string& d, size_t at)
{
	if (at + 2 > d.size())
		return 0;
	return static_cast<std::uint16_t>(static_cast<std::uint8_t>(d[at]) | static_cast<std::uint8_t>(d[at + 1]) << 8);
}

} // namespace

LogReport analyse_log(const std::string& text)
{
	LogReport report;
	report.found = true;
	for (const auto& line : split(text, '\n')) {
		if (line.rfind(fatal_prefix, 0) == 0) {
			report.fatal.push_back(trim(line.substr(sizeof(fatal_prefix) - 1)));
		} else if (line.rfind(error_prefix, 0) == 0) {
			report.errors++;
		} else if (line.rfind(warning_prefix, 0) == 0) {
			report.warnings++;
		}
	}
	if (report.fatal.size() > 10)
		report.fatal.erase(report.fatal.begin(), report.fatal.end() - 10);
	for (const auto& [needle, message] : known_patterns)
		if (text.find(needle) != std::string::npos)
			report.explanations.emplace_back(message);
	return report;
}

std::string log_tail(const std::string& text, size_t lines)
{
	auto all = split(text, '\n');
	if (!all.empty() && all.back().empty())
		all.pop_back();
	std::string out;
	for (size_t i = all.size() > lines ? all.size() - lines : 0; i < all.size(); i++)
		out += all[i] + "\n";
	return out;
}

PeImports read_pe_imports(const std::string& d)
{
	PeImports result;
	if (d.size() < 0x40 || d[0] != 'M' || d[1] != 'Z')
		return result;
	const std::uint32_t pe = le32(d, 0x3c);
	if (pe + 24 > d.size() || std::memcmp(d.data() + pe, "PE\0\0", 4) != 0)
		return result;
	const std::uint16_t machine = le16(d, pe + 4), sections = le16(d, pe + 6), opt_size = le16(d, pe + 20);
	const size_t opt = pe + 24;
	const std::uint16_t magic = le16(d, opt);
	if (magic != 0x20b) // só PE32+ (x64)
		return result;
	result.is_x64 = machine == 0x8664;
	const size_t dirs = opt + 112;
	const std::uint32_t import_rva = le32(d, dirs + 8), delay_rva = le32(d, dirs + 13 * 8);
	const size_t section_table = opt + opt_size;

	auto to_offset = [&](std::uint32_t rva) -> size_t {
		for (std::uint16_t i = 0; i < sections; i++) {
			const size_t s = section_table + size_t{i} * 40;
			const std::uint32_t vsize = le32(d, s + 8), vaddr = le32(d, s + 12), raw_size = le32(d, s + 16),
			                    raw_ptr = le32(d, s + 20);
			if (rva >= vaddr && rva < vaddr + std::max(vsize, raw_size))
				return size_t{raw_ptr} + (rva - vaddr);
		}
		return std::string::npos;
	};
	auto name_at = [&](std::uint32_t rva) {
		const size_t at = to_offset(rva);
		if (at == std::string::npos || at >= d.size())
			return std::string();
		const size_t end = d.find('\0', at);
		return end == std::string::npos ? std::string() : d.substr(at, end - at);
	};

	if (import_rva) {
		size_t at = to_offset(import_rva);
		for (; at != std::string::npos && at + 20 <= d.size(); at += 20) {
			const std::uint32_t name_rva = le32(d, at + 12);
			if (!name_rva)
				break;
			result.dlls.push_back(name_at(name_rva));
		}
	}
	if (delay_rva) {
		size_t at = to_offset(delay_rva);
		for (; at != std::string::npos && at + 32 <= d.size(); at += 32) {
			const std::uint32_t name_rva = le32(d, at + 4);
			if (!name_rva)
				break;
			result.delay_dlls.push_back(name_at(name_rva));
		}
	}
	result.valid = true;
	return result;
}

bool is_vc_runtime(std::string_view dll)
{
	const std::string lower = to_lower(dll);
	for (const char* prefix : {"msvcp140", "vcruntime140", "concrt140", "vccorlib140", "vcomp140"})
		if (lower.rfind(prefix, 0) == 0)
			return true;
	return false;
}

bool is_api_set(std::string_view dll)
{
	const std::string lower = to_lower(dll);
	return lower.rfind("api-ms-win-", 0) == 0 || lower.rfind("ext-ms-", 0) == 0;
}

} // namespace gow3
