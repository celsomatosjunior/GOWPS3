// SPDX-License-Identifier: GPL-2.0-only
#include "game.hpp"

#include "psf.hpp"
#include "sha256.hpp"

#include <fstream>
#include <set>

namespace gow3 {

const std::vector<std::string> known_serials = {
	"BCES00510", "BCUS98111", "BCAS25003", "BCES00799", "BCKS15003",
	"BCES00516", "BCAS25007", "BCJS37001", "BCJS75001",
};

std::string region_for_serial(std::string_view serial)
{
	const std::string prefix(serial.substr(0, 4));
	if (prefix == "BCUS") return "América do Norte";
	if (prefix == "BCES") return "Europa";
	if (prefix == "BCAS") return "Ásia";
	if (prefix == "BCJS") return "Japão";
	if (prefix == "BCKS") return "Coreia";
	return "desconhecida";
}

std::string firmware_from_sfo(std::string_view text)
{
	const std::string value = trim(text);
	const auto dot = value.find('.');
	if (dot == std::string::npos || dot == 0)
		return value;
	try {
		const int major = std::stoi(value.substr(0, dot));
		std::string minor = value.substr(dot + 1);
		while (minor.size() > 1 && minor.back() == '0')
			minor.pop_back();
		return std::to_string(major) + "." + minor;
	} catch (...) {
		return value;
	}
}

namespace {

void walk(const fs::path& dir, std::vector<fs::path>& out)
{
	std::error_code ec;
	if (!fs::is_directory(dir, ec))
		return;
	for (auto it = fs::recursive_directory_iterator(dir, fs::directory_options::skip_permission_denied, ec);
	     it != fs::recursive_directory_iterator(); it.increment(ec)) {
		if (ec)
			break;
		if (it->is_regular_file(ec))
			out.push_back(it->path());
	}
}

} // namespace

GameInfo inspect_game(const fs::path& root)
{
	GameInfo info;
	info.root = info.game_dir = info.boot_path = root;
	auto add = [&](Level level, std::string message) { info.findings.push_back({level, std::move(message)}); };
	std::error_code ec;

	if (root.empty() || !fs::is_directory(root, ec)) {
		add(Level::error, "Escolha a pasta do God of War III (a que contém PS3_GAME).");
		return info;
	}
	if (fs::is_regular_file(root / "PS3_GAME" / "PARAM.SFO", ec))
		info.game_dir = root / "PS3_GAME";
	else if (!fs::is_regular_file(root / "PARAM.SFO", ec)) {
		add(Level::error, "PARAM.SFO não encontrado. Escolha a pasta do jogo (a que contém PS3_GAME, ou a própria PS3_GAME).");
		return info;
	}
	info.boot_path = root; // o RPCS3 aceita a raiz do disco ou a própria pasta do jogo

	std::string raw, error;
	if (!read_file(info.game_dir / "PARAM.SFO", raw)) {
		add(Level::error, "Não foi possível ler o PARAM.SFO.");
		return info;
	}
	const auto sfo = psf::parse(raw, &error);
	if (!sfo) {
		add(Level::error, "PARAM.SFO ilegível: " + error);
		return info;
	}
	info.serial = psf::get_string(*sfo, "TITLE_ID");
	info.title = psf::get_string(*sfo, "TITLE");
	info.app_version = psf::get_string(*sfo, "APP_VER");
	info.category = psf::get_string(*sfo, "CATEGORY");
	info.required_firmware = firmware_from_sfo(psf::get_string(*sfo, "PS3_SYSTEM_VER"));
	info.region = region_for_serial(info.serial);

	if (std::find(known_serials.begin(), known_serials.end(), info.serial) != known_serials.end())
		add(Level::ok, "God of War III reconhecido: " + info.serial + " (" + info.region + ")");
	else
		add(Level::error, "O serial " + (info.serial.empty() ? std::string("(vazio)") : info.serial) +
		                      " não é de God of War III.");
	if (info.category != "DG" && info.category != "HG" && info.category != "GD")
		add(Level::warning, "Categoria inesperada no PARAM.SFO: " + info.category);

	const fs::path eboot = info.game_dir / "USRDIR" / "EBOOT.BIN";
	if (!fs::is_regular_file(eboot, ec)) {
		add(Level::error, "USRDIR/EBOOT.BIN não encontrado: a cópia do jogo está incompleta.");
	} else {
		char magic[4] = {};
		std::ifstream(eboot, std::ios::binary).read(magic, 4);
		if (std::string_view(magic, 4) == std::string_view("SCE\0", 4))
			info.eboot_kind = "SELF (original do disco)";
		else if (std::string_view(magic, 4) == "\x7f" "ELF")
			info.eboot_kind = "ELF (já decifrado)";
		if (info.eboot_kind.empty())
			add(Level::error, "EBOOT.BIN não tem cabeçalho SELF nem ELF: arquivo corrompido.");
		else
			add(Level::ok, "EBOOT.BIN presente: " + info.eboot_kind);
	}

	std::vector<fs::path> files;
	walk(info.game_dir / "USRDIR", files);
	size_t empty = 0;
	std::string example;
	for (const auto& file : files)
		if (fs::file_size(file, ec) == 0 && !ec && empty++ == 0)
			example = path_to_utf8(fs::relative(file, info.game_dir, ec));
	if (empty)
		add(Level::warning, std::to_string(empty) + " arquivo(s) vazio(s) em USRDIR (ex.: " + example +
		                        "). Isso costuma indicar uma cópia interrompida.");
	if (info.game_dir != root && !fs::is_regular_file(root / "PS3_DISC.SFB", ec))
		add(Level::warning, "PS3_DISC.SFB ausente na raiz do disco.");
	return info;
}

Manifest build_manifest(const fs::path& dir)
{
	std::vector<fs::path> files;
	walk(dir, files);
	Manifest manifest;
	std::error_code ec;
	for (const auto& file : files) {
		const auto digest = sha256_file(file);
		manifest[generic_utf8(fs::relative(file, dir, ec))] =
			std::to_string(fs::file_size(file, ec)) + " " + digest.value_or("ilegivel");
	}
	return manifest;
}

std::string serialize_manifest(const Manifest& manifest)
{
	std::string out;
	for (const auto& [path, value] : manifest)
		out += value + " " + path + "\n";
	return out;
}

Manifest parse_manifest(const std::string& text)
{
	Manifest manifest;
	for (const auto& line : split(text, '\n')) {
		const auto first = line.find(' ');
		const auto second = first == std::string::npos ? first : line.find(' ', first + 1);
		if (second == std::string::npos)
			continue;
		std::string path = line.substr(second + 1);
		if (!path.empty() && path.back() == '\r')
			path.pop_back();
		manifest[path] = line.substr(0, second);
	}
	return manifest;
}

Findings compare_manifest(const Manifest& saved, const Manifest& current)
{
	std::vector<std::string> missing, changed, added;
	for (const auto& [path, value] : saved) {
		const auto it = current.find(path);
		if (it == current.end())
			missing.push_back(path);
		else if (it->second != value)
			changed.push_back(path);
	}
	for (const auto& [path, value] : current)
		if (!saved.count(path))
			added.push_back(path);
	Findings out;
	if (!missing.empty())
		out.push_back({Level::error, std::to_string(missing.size()) + " arquivo(s) sumiram (ex.: " + missing[0] + ")"});
	if (!changed.empty())
		out.push_back({Level::error, std::to_string(changed.size()) + " arquivo(s) mudaram (ex.: " + changed[0] + ")"});
	if (!added.empty())
		out.push_back({Level::warning, std::to_string(added.size()) + " arquivo(s) novos (ex.: " + added[0] + ")"});
	if (out.empty())
		out.push_back({Level::ok, "Integridade conferida: " + std::to_string(current.size()) + " arquivos iguais à referência"});
	return out;
}

} // namespace gow3
