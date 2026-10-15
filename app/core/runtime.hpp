// SPDX-License-Identifier: GPL-2.0-only
// Estrutura portátil do pacote e integração com o RPCS3 embutido em runtime\rpcs3.
//
// Comportamentos do RPCS3 usados aqui (conferidos no código, commit em RPCS3_COMMIT.txt):
//  * --no-gui, --fullscreen, --config, --installfw, --headless, --version: rpcs3/rpcs3.cpp
//  * RPCS3_CONFIG_DIR muda a pasta de dados; o RPCS3 corta o valor na última barra, então ele
//    PRECISA terminar com separador (Utilities/File.cpp, fs::get_config_dir)
//  * uma pasta "portable" ao lado do rpcs3.exe tem prioridade sobre RPCS3_CONFIG_DIR
//  * firmware: dev_flash/sys/external/liblv2.sprx e dev_flash/vsh/etc/version.txt
#pragma once

#include "common.hpp"

namespace gow3 {

struct Layout {
	fs::path app_dir;     // pasta do GOW3_PS3_PC.exe
	fs::path runtime_dir; // runtime\rpcs3
	fs::path user_dir;    // user
	fs::path profile_dir; // user\rpcs3 (= RPCS3_CONFIG_DIR)

	static Layout from_app_dir(const fs::path& app_dir, const fs::path& user_dir_override = {});

	fs::path rpcs3_exe() const { return runtime_dir / "rpcs3.exe"; }
	fs::path runtime_manifest() const { return app_dir / "runtime" / "runtime_manifest.txt"; }
	fs::path portable_dir() const { return runtime_dir / "portable"; }
	fs::path settings_file() const { return user_dir / "settings.ini"; }
	fs::path launcher_log() const { return user_dir / "logs" / "GOW3_PS3_PC.log"; }
	fs::path selftest_report() const { return user_dir / "logs" / "selftest.txt"; }
	fs::path override_config() const { return user_dir / "gow3_rpcs3_config.yml"; }
	fs::path game_manifest() const { return user_dir / "game_manifest.txt"; }
	fs::path rpcs3_log() const { return profile_dir / "log" / "RPCS3.log"; }
	fs::path dev_flash() const { return profile_dir / "dev_flash"; }
	fs::path savedata() const { return profile_dir / "dev_hdd0" / "home" / "00000001" / "savedata"; }
	fs::path game_updates() const { return profile_dir / "dev_hdd0" / "game"; }
	fs::path cache_dir() const { return profile_dir / "cache"; }

	std::string config_dir_env() const; // valor de RPCS3_CONFIG_DIR, sempre com separador final
};

// Mesma regra de utils::get_firmware_version do RPCS3: "release:04.9200:" -> "4.92".
std::string firmware_version_from_text(const std::string& version_txt);
std::string installed_firmware(const Layout& layout); // vazio se não instalado
bool firmware_installed(const Layout& layout);
int compare_versions(const std::string& a, const std::string& b);

std::vector<std::string> boot_arguments(const fs::path& config_file, const fs::path& game, bool fullscreen);
std::vector<std::string> install_firmware_arguments(const fs::path& pup);
std::vector<std::string> version_arguments();

// Monta uma linha de comando que CommandLineToArgvW / o CRT do MSVC separa de volta exatamente.
std::string quote_windows_argument(const std::string& argument);
std::string windows_command_line(const fs::path& exe, const std::vector<std::string>& arguments);

// Manifesto do runtime gerado na compilação: "sha256 tamanho caminho/relativo".
struct RuntimeEntry {
	std::string sha256;
	std::uint64_t size = 0;
	std::string path;
};
std::vector<RuntimeEntry> parse_runtime_manifest(const std::string& text);
Findings check_runtime(const Layout& layout, bool verify_hashes);

} // namespace gow3
