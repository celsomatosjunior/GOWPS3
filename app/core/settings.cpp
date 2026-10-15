// SPDX-License-Identifier: GPL-2.0-only
#include "settings.hpp"

#include <sstream>
#include <stdexcept>

namespace gow3 {

const Option* OptionTable::find(std::string_view id) const
{
	for (const auto& option : options)
		if (option.id == id)
			return &option;
	return nullptr;
}

// God of War III renderiza em 1280x720 no PS3; "Resolution Scale" do RPCS3 é relativo a isso.
const OptionTable& internal_resolution_table()
{
	static const OptionTable table{"Resolution Scale", {
		{"720p", "720p (original do PS3)", "100"},
		{"900p", "900p", "125"},
		{"1080p", "1080p", "150"},
		{"1440p", "1440p", "200"},
		{"4K", "4K (2160p)", "300"},
	}};
	return table;
}

const OptionTable& scaling_table()
{
	static const OptionTable table{"Output Scaling Mode", {
		{"bilinear", "Bilinear", "Bilinear"},
		{"fsr", "AMD FSR 1 (com nitidez RCAS)", "FidelityFX Super Resolution"},
		{"nearest", "Vizinho mais próximo", "Nearest"},
	}};
	return table;
}

const OptionTable& anisotropic_table()
{
	static const OptionTable table{"Anisotropic Filter Override", {
		{"auto", "O jogo decide", "0"}, {"2x", "2x", "2"}, {"4x", "4x", "4"}, {"8x", "8x", "8"}, {"16x", "16x", "16"},
	}};
	return table;
}

const OptionTable& vsync_table()
{
	static const OptionTable table{"VSync Mode", {
		{"off", "Desligado", "Disabled"}, {"adaptive", "Adaptativo", "Adaptive"}, {"full", "Ligado", "Full"},
	}};
	return table;
}

const OptionTable& frame_limit_table()
{
	static const OptionTable table{"Frame limit", {
		{"auto", "Automático (o jogo decide)", "Auto"},
		{"30", "30 FPS", "30"},
		{"60", "60 FPS", "60"},
		{"display", "Taxa do monitor", "Display"},
		{"off", "Sem limite", "Off"},
	}};
	return table;
}

const OptionTable& shader_mode_table()
{
	static const OptionTable table{"Shader Mode", {
		{"async_interpreter", "Assíncrono com intérprete (sem travadas)", "Async Recompiler with Shader Interpreter"},
		{"async", "Assíncrono", "Async Recompiler (multi-threaded)"},
		{"legacy", "Legado (uma thread)", "Legacy Recompiler (single-threaded)"},
	}};
	return table;
}

const OptionTable& spu_block_table()
{
	static const OptionTable table{"SPU Block Size", {
		{"safe", "Safe (recomendado)", "Safe"}, {"mega", "Mega", "Mega"}, {"giga", "Giga", "Giga"},
	}};
	return table;
}

namespace {

struct Field {
	const char* name;
	std::string Settings::*text;
	const OptionTable& (*table)();
};

const Field text_fields[] = {
	{"internal_resolution", &Settings::internal_resolution, internal_resolution_table},
	{"output_scaling", &Settings::output_scaling, scaling_table},
	{"anisotropic", &Settings::anisotropic, anisotropic_table},
	{"vsync", &Settings::vsync, vsync_table},
	{"frame_limit", &Settings::frame_limit, frame_limit_table},
	{"shader_mode", &Settings::shader_mode, shader_mode_table},
	{"spu_block_size", &Settings::spu_block_size, spu_block_table},
};

struct BoolField {
	const char* name;
	bool Settings::*flag;
};

const BoolField bool_fields[] = {
	{"fullscreen", &Settings::fullscreen},
	{"performance_overlay", &Settings::performance_overlay},
	{"shader_compilation_hint", &Settings::shader_compilation_hint},
	{"write_color_buffers", &Settings::write_color_buffers},
};

std::string quote(std::string_view text)
{
	std::string out = "\"";
	for (char c : text) {
		if (c == '"' || c == '\\')
			out.push_back('\\');
		if (c == '\n' || c == '\r')
			continue;
		out.push_back(c);
	}
	return out + "\"";
}

const std::string& value_of(const OptionTable& table, const std::string& id)
{
	return table.find(id)->value;
}

} // namespace

std::vector<std::string> Settings::validate() const
{
	std::vector<std::string> errors;
	for (const auto& field : text_fields)
		if (!field.table().find(this->*field.text))
			errors.push_back(std::string(field.name) + ": valor inválido '" + this->*field.text + "'");
	if (rcas_sharpening < 0 || rcas_sharpening > 100)
		errors.push_back("rcas_sharpening: precisa estar entre 0 e 100");
	if (preferred_spu_threads < 0 || preferred_spu_threads > 6)
		errors.push_back("preferred_spu_threads: precisa estar entre 0 e 6");
	return errors;
}

std::string serialize_settings(const Settings& s)
{
	std::ostringstream out;
	out << "# GOW3 PS3 PC\n";
	out << "game_path=" << s.game_path << "\n";
	for (const auto& field : text_fields)
		out << field.name << "=" << s.*field.text << "\n";
	for (const auto& field : bool_fields)
		out << field.name << "=" << (s.*field.flag ? "1" : "0") << "\n";
	out << "rcas_sharpening=" << s.rcas_sharpening << "\n";
	out << "preferred_spu_threads=" << s.preferred_spu_threads << "\n";
	out << "vulkan_adapter=" << s.vulkan_adapter << "\n";
	return out.str();
}

Settings parse_settings(const std::string& text)
{
	Settings s;
	const Settings defaults;
	for (const auto& raw : split(text, '\n')) {
		const auto line = trim(raw);
		const auto eq = line.find('=');
		if (line.empty() || line[0] == '#' || eq == std::string::npos)
			continue;
		const std::string key = line.substr(0, eq), value = line.substr(eq + 1);
		if (key == "game_path")
			s.game_path = value;
		else if (key == "vulkan_adapter")
			s.vulkan_adapter = value;
		else if (key == "rcas_sharpening" || key == "preferred_spu_threads") {
			try {
				(key == "rcas_sharpening" ? s.rcas_sharpening : s.preferred_spu_threads) = std::stoi(value);
			} catch (...) {
			}
		}
		for (const auto& field : text_fields)
			if (key == field.name)
				s.*field.text = value;
		for (const auto& field : bool_fields)
			if (key == field.name)
				s.*field.flag = value == "1" || value == "true";
	}
	// Corrige individualmente o que estiver inválido, preservando o resto.
	for (const auto& field : text_fields)
		if (!field.table().find(s.*field.text))
			s.*field.text = defaults.*field.text;
	if (s.rcas_sharpening < 0 || s.rcas_sharpening > 100)
		s.rcas_sharpening = defaults.rcas_sharpening;
	if (s.preferred_spu_threads < 0 || s.preferred_spu_threads > 6)
		s.preferred_spu_threads = defaults.preferred_spu_threads;
	return s;
}

std::string rpcs3_yaml(const Settings& s)
{
	const auto errors = s.validate();
	if (!errors.empty())
		throw std::invalid_argument(errors.front());
	auto b = [](bool v) { return std::string(v ? "true" : "false"); };
	std::ostringstream y;
	y << "# Gerado pelo GOW3 PS3 PC. Sobrescrito a cada início do jogo.\n"
	  << "Core:\n"
	  << "  PPU Decoder: " << quote("Recompiler (LLVM)") << "\n"
	  << "  SPU Decoder: " << quote("Recompiler (LLVM)") << "\n"
	  << "  SPU Block Size: " << quote(value_of(spu_block_table(), s.spu_block_size)) << "\n"
	  << "  Preferred SPU Threads: " << s.preferred_spu_threads << "\n"
	  << "Video:\n"
	  << "  Renderer: " << quote("Vulkan") << "\n"
	  << "  Resolution: " << quote("1280x720") << "\n"
	  << "  Resolution Scale: " << value_of(internal_resolution_table(), s.internal_resolution) << "\n"
	  << "  Output Scaling Mode: " << quote(value_of(scaling_table(), s.output_scaling)) << "\n"
	  << "  FidelityFX CAS Sharpening Intensity: " << s.rcas_sharpening << "\n"
	  << "  Anisotropic Filter Override: " << value_of(anisotropic_table(), s.anisotropic) << "\n"
	  << "  VSync Mode: " << quote(value_of(vsync_table(), s.vsync)) << "\n"
	  << "  Frame limit: " << quote(value_of(frame_limit_table(), s.frame_limit)) << "\n"
	  << "  Shader Mode: " << quote(value_of(shader_mode_table(), s.shader_mode)) << "\n"
	  << "  Write Color Buffers: " << b(s.write_color_buffers) << "\n"
	  << "  Vulkan:\n"
	  << "    Adapter: " << quote(s.vulkan_adapter) << "\n"
	  << "  Performance Overlay:\n"
	  << "    Enabled: " << b(s.performance_overlay) << "\n"
	  << "Miscellaneous:\n"
	  << "  Exit RPCS3 when process finishes: true\n"
	  << "  Start games in fullscreen mode: " << b(s.fullscreen) << "\n"
	  << "  Show shader compilation hint: " << b(s.shader_compilation_hint) << "\n";
	return y.str();
}

} // namespace gow3
