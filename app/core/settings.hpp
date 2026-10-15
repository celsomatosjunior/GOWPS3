// SPDX-License-Identifier: GPL-2.0-only
// Configurações do GOW3 PS3 PC e geração do arquivo de configuração passado ao RPCS3 (--config).
// Nomes de chaves e textos de valores conferidos em rpcs3/Emu/system_config.h e
// system_config_types.cpp (commit fixado em RPCS3_COMMIT.txt). O RPCS3 carrega os padrões e aplica
// este arquivo por cima, então chaves ausentes ficam com o padrão.
#pragma once

#include "common.hpp"

namespace gow3 {

struct Option {
	std::string id;     // gravado no settings.ini
	std::string label;  // mostrado na interface
	std::string value;  // texto que o RPCS3 entende (ou número)
};

struct OptionTable {
	std::string key;
	std::vector<Option> options;
	const Option* find(std::string_view id) const;
};

// Tabelas públicas para a interface montar as listas.
const OptionTable& internal_resolution_table();
const OptionTable& scaling_table();
const OptionTable& anisotropic_table();
const OptionTable& vsync_table();
const OptionTable& frame_limit_table();
const OptionTable& shader_mode_table();
const OptionTable& spu_block_table();

struct Settings {
	std::string game_path;
	std::string internal_resolution = "720p";
	std::string output_scaling = "bilinear";
	int rcas_sharpening = 50;
	std::string anisotropic = "auto";
	std::string vsync = "off";
	std::string frame_limit = "auto";
	std::string shader_mode = "async_interpreter";
	bool fullscreen = true;
	bool performance_overlay = false;
	bool shader_compilation_hint = true;
	// Recomendados pela wiki do RPCS3 para God of War III.
	bool write_color_buffers = true;
	std::string spu_block_size = "safe";
	int preferred_spu_threads = 0;
	std::string vulkan_adapter; // vazio = o RPCS3 escolhe

	std::vector<std::string> validate() const;
	bool operator==(const Settings&) const = default;
};

std::string serialize_settings(const Settings& settings);
Settings parse_settings(const std::string& text); // valores inválidos voltam ao padrão

std::string rpcs3_yaml(const Settings& settings); // lança std::invalid_argument se inválido

} // namespace gow3
