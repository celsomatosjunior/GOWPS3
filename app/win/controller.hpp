// SPDX-License-Identifier: GPL-2.0-only
// Lógica do aplicativo (usada pela janela e pelos modos --check e --selftest).
#pragma once

#include "../core/game.hpp"
#include "../core/runtime.hpp"
#include "../core/settings.hpp"
#include "platform.hpp"

#include <mutex>

#include "version.h"

namespace gow3 {

inline constexpr const char* app_name = "GOW3 PS3 PC";
inline constexpr const char* app_version = GOW3_VERSION;

class Controller {
public:
	explicit Controller(Layout layout);

	const Layout& layout() const { return layout_; }
	Settings& settings() { return settings_; }
	const GameInfo& game() const { return game_; }

	void load_settings();
	void save_settings();
	void log(const std::string& message);

	Findings preflight(); // atualiza game()
	bool ready() const { return ready_; }

	// Inicia o jogo; devolve o handle do processo (esperar com win::wait_process) ou nullptr.
	void* start_game(std::string& error);
	Findings install_firmware(const fs::path& pup);
	Findings vcruntime_status() const;              // Visual C++ instalado no Windows (exigido pelo RPCS3)
	Findings install_vcredist(bool quiet);          // roda runtime\redist\vc_redist.x64.exe como administrador
	Findings import_rpcs3(const fs::path& folder); // instala o RPCS3 baixado pelo usuário em runtime\rpcs3
	Findings check_rpcs3_binary();
	Findings run_rpcs3_version(std::string* version);
	bool open_rpcs3_settings(std::string& error);
	Findings check_game_integrity(bool reset_reference);
	Findings clear_game_cache();
	std::string diagnostics_text();
	Findings after_game_exit(unsigned long exit_code);

	// Autoteste do pacote. Devolve true se tudo o que é obrigatório passou.
	bool self_test(std::string& report, bool allow_missing_vulkan);

	std::vector<std::pair<std::string, std::string>> rpcs3_environment() const;
	std::string installed_update(const std::string& serial) const;

private:
	Layout layout_;
	Settings settings_;
	GameInfo game_;
	bool ready_ = false;
	std::mutex log_mutex_;
};

std::string format_findings(const Findings& findings);

} // namespace gow3
