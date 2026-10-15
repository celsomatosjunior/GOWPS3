// SPDX-License-Identifier: GPL-2.0-only
#include "runtime.hpp"

#include "sha256.hpp"

#include <algorithm>

namespace gow3 {

Layout Layout::from_app_dir(const fs::path& app_dir, const fs::path& user_dir_override)
{
	Layout layout;
	layout.app_dir = app_dir;
	layout.runtime_dir = app_dir / "runtime" / "rpcs3";
	layout.user_dir = user_dir_override.empty() ? app_dir / "user" : user_dir_override;
	layout.profile_dir = layout.user_dir / "rpcs3";
	return layout;
}

std::string Layout::config_dir_env() const
{
	std::string value = path_to_utf8(profile_dir.lexically_normal());
	if (value.empty() || (value.back() != '\\' && value.back() != '/'))
		value.push_back(static_cast<char>(fs::path::preferred_separator));
	return value;
}

std::string firmware_version_from_text(const std::string& text)
{
	const auto parts = split(text, ':');
	if (parts.size() < 3)
		return {};
	const std::string& version = parts[1];
	size_t start = version.find_first_not_of('0');
	if (start == std::string::npos)
		return {};
	if (version[start] == '.') {
		if (start == 0)
			return {};
		start--;
	}
	const size_t dot = version.find('.', start);
	if (dot == std::string::npos)
		return {};
	// Reproduz a conta do RPCS3 (o segundo argumento de substr é uma contagem).
	const size_t last_not_zero = version.find_last_not_of('0', dot + 1);
	const size_t count = std::max(last_not_zero == std::string::npos ? size_t{0} : last_not_zero,
	                              std::min(dot + 2, version.size()));
	return version.substr(start, count);
}

std::string installed_firmware(const Layout& layout)
{
	std::string text;
	if (!read_file(layout.dev_flash() / "vsh" / "etc" / "version.txt", text))
		return {};
	return firmware_version_from_text(text);
}

bool firmware_installed(const Layout& layout)
{
	std::error_code ec;
	return fs::is_regular_file(layout.dev_flash() / "sys" / "external" / "liblv2.sprx", ec);
}

int compare_versions(const std::string& a, const std::string& b)
{
	const auto pa = split(a, '.'), pb = split(b, '.');
	for (size_t i = 0; i < std::max(pa.size(), pb.size()); i++) {
		auto number = [](const std::vector<std::string>& parts, size_t at) {
			if (at >= parts.size())
				return 0;
			int value = 0;
			for (char c : parts[at])
				if (c >= '0' && c <= '9')
					value = value * 10 + (c - '0');
			return value;
		};
		const int x = number(pa, i), y = number(pb, i);
		if (x != y)
			return x < y ? -1 : 1;
	}
	return 0;
}

std::vector<std::string> boot_arguments(const fs::path& config_file, const fs::path& game, bool fullscreen)
{
	std::vector<std::string> args{"--no-gui"};
	if (fullscreen)
		args.emplace_back("--fullscreen"); // o RPCS3 só aceita junto com --no-gui
	args.emplace_back("--config");
	args.push_back(path_to_utf8(config_file));
	args.push_back(path_to_utf8(game));
	return args;
}

std::vector<std::string> install_firmware_arguments(const fs::path& pup)
{
	// No modo headless o RPCS3 instala sem janelas e encerra (rpcs3.cpp, ramo sem gui_application).
	return {"--headless", "--installfw", path_to_utf8(pup)};
}

std::vector<std::string> version_arguments()
{
	return {"--headless", "--version"};
}

std::string quote_windows_argument(const std::string& arg)
{
	if (!arg.empty() && arg.find_first_of(" \t\n\v\"") == std::string::npos)
		return arg;
	std::string out = "\"";
	size_t backslashes = 0;
	for (char c : arg) {
		if (c == '\\') {
			backslashes++;
			continue;
		}
		if (c == '"')
			out.append(backslashes * 2 + 1, '\\');
		else
			out.append(backslashes, '\\');
		backslashes = 0;
		out.push_back(c);
	}
	out.append(backslashes * 2, '\\');
	return out + "\"";
}

std::string windows_command_line(const fs::path& exe, const std::vector<std::string>& arguments)
{
	std::string line = quote_windows_argument(path_to_utf8(exe));
	for (const auto& arg : arguments)
		line += " " + quote_windows_argument(arg);
	return line;
}

std::vector<RuntimeEntry> parse_runtime_manifest(const std::string& text)
{
	std::vector<RuntimeEntry> entries;
	for (const auto& raw : split(text, '\n')) {
		const auto line = trim(raw);
		if (line.empty() || line[0] == '#')
			continue;
		const auto a = line.find(' ');
		const auto b = a == std::string::npos ? a : line.find(' ', a + 1);
		if (b == std::string::npos)
			continue;
		RuntimeEntry entry;
		entry.sha256 = line.substr(0, a);
		try {
			entry.size = std::stoull(line.substr(a + 1, b - a - 1));
		} catch (...) {
			continue;
		}
		entry.path = line.substr(b + 1);
		entries.push_back(entry);
	}
	return entries;
}

Findings check_runtime(const Layout& layout, bool verify_hashes)
{
	Findings out;
	std::error_code ec;
	if (!fs::is_regular_file(layout.rpcs3_exe(), ec)) {
		out.push_back({Level::error, "RPCS3 ainda não instalado neste aplicativo. Baixe o RPCS3 para Windows em rpcs3.net, "
		                             "extraia, clique em 'Instalar RPCS3...' e escolha a pasta extraída."});
		return out;
	}
	if (fs::is_directory(layout.portable_dir(), ec))
		out.push_back({Level::error, "A pasta " + path_to_utf8(layout.portable_dir()) +
		                                 " faz o RPCS3 ignorar a pasta user. Apague-a."});

	std::string text;
	if (!read_file(layout.runtime_manifest(), text)) {
		out.push_back({Level::warning, "Lista de componentes (runtime_manifest.txt) não encontrada."});
		return out;
	}
	const auto entries = parse_runtime_manifest(text);
	size_t missing = 0, wrong = 0;
	std::string example;
	for (const auto& entry : entries) {
		const fs::path file = layout.app_dir / "runtime" / utf8_to_path(entry.path);
		const auto size = fs::file_size(file, ec);
		if (ec) {
			if (missing++ == 0)
				example = entry.path;
			continue;
		}
		bool bad = size != entry.size;
		if (!bad && verify_hashes)
			bad = sha256_file(file).value_or("") != entry.sha256;
		if (bad && wrong++ == 0 && example.empty())
			example = entry.path;
	}
	if (missing || wrong)
		out.push_back({Level::error, std::to_string(missing) + " componente(s) ausente(s) e " + std::to_string(wrong) +
		                                 " diferente(s) do que foi instalado (ex.: " + example + "). Use 'Instalar RPCS3...' de novo."});
	else
		out.push_back({Level::ok, "Componentes do RPCS3 conferidos: " + std::to_string(entries.size()) + " arquivos" +
		                              (verify_hashes ? " (com SHA-256)" : "")});
	return out;
}

std::string build_runtime_manifest(const Layout& layout)
{
	std::string out = "# sha256 tamanho caminho (gerado pelo GOW3_PS3_PC.exe ao instalar o RPCS3)\n";
	std::error_code ec;
	std::vector<fs::path> files;
	for (auto it = fs::recursive_directory_iterator(layout.runtime_dir, ec); !ec && it != fs::recursive_directory_iterator();
	     it.increment(ec))
		if (it->is_regular_file(ec))
			files.push_back(it->path());
	std::sort(files.begin(), files.end());
	const fs::path base = layout.runtime_dir.parent_path();
	for (const auto& file : files)
		out += sha256_file(file).value_or("ilegivel") + " " + std::to_string(fs::file_size(file, ec)) + " " +
		       generic_utf8(fs::relative(file, base, ec)) + "\n";
	return out;
}

std::vector<std::string> missing_strings(const std::string& image, const std::vector<std::string>& needles)
{
	std::vector<std::string> missing;
	for (const auto& needle : needles) {
		if (image.find(needle) != std::string::npos)
			continue;
		std::string wide;
		for (char c : needle) {
			wide.push_back(c);
			wide.push_back('\0');
		}
		if (image.find(wide) == std::string::npos)
			missing.push_back(needle);
	}
	return missing;
}

fs::path find_rpcs3_folder(const fs::path& picked)
{
	std::error_code ec;
	if (fs::is_regular_file(picked / "rpcs3.exe", ec))
		return picked;
	for (const auto& entry : fs::directory_iterator(picked, ec))
		if (entry.is_directory(ec) && fs::is_regular_file(entry.path() / "rpcs3.exe", ec))
			return entry.path();
	return {};
}

} // namespace gow3
