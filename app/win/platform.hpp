// SPDX-License-Identifier: GPL-2.0-only
// Funções que dependem da API do Windows.
#pragma once

#include "../core/common.hpp"

#include <optional>

namespace gow3::win {

std::wstring widen(std::string_view utf8);
std::string narrow(std::wstring_view wide);

fs::path executable_dir();
fs::path system_dir(); // C:\Windows\System32
std::string file_version(const fs::path& file); // "14.44.35211.0" ou vazio
bool directory_writable(const fs::path& dir);

struct ProcessResult {
	bool started = false;
	unsigned long exit_code = 0;
	bool timed_out = false;
	std::string output;      // stdout+stderr, se capturado
	std::string error;       // mensagem do Windows se não iniciou
};

// Inicia `exe` com argumentos e variáveis extras de ambiente. Devolve o handle (para esperar
// depois) ou nullptr; `error` recebe a mensagem do Windows.
void* start_process(const fs::path& exe, const std::vector<std::string>& args,
                    const std::vector<std::pair<std::string, std::string>>& env, std::string& error);
unsigned long wait_process(void* handle); // fecha o handle
// Executa como administrador (pede confirmação do UAC) e espera. Devolve o código de saída.
ProcessResult run_elevated(const fs::path& exe, const std::vector<std::string>& args);
// Executa e espera, capturando a saída. timeout_ms = 0 espera sem limite.
ProcessResult run_process(const fs::path& exe, const std::vector<std::string>& args,
                          const std::vector<std::pair<std::string, std::string>>& env, unsigned timeout_ms);

void open_folder(const fs::path& dir);

struct GpuInfo {
	std::string name;
	std::string type;       // integrada, dedicada...
	std::string api_version;
	std::uint64_t vram_bytes = 0;
};

struct SystemInfo {
	std::string os;
	unsigned os_build = 0;
	std::string cpu_name;
	unsigned threads = 0;
	bool avx2 = false, avx512 = false;
	double ram_gb = 0;
	bool vulkan_loader = false;   // vulkan-1.dll encontrada
	std::string vulkan_error;
	std::vector<GpuInfo> gpus;
};

SystemInfo collect_system_info();
Findings evaluate_system(const SystemInfo& info);

// Onde o Windows encontraria esta DLL para um executável em `exe_dir`.
enum class DllSource { not_found, local, system, path };
struct DllLocation {
	DllSource source = DllSource::not_found;
	fs::path file;
};
DllLocation resolve_dll(const std::string& dll, const fs::path& exe_dir);

} // namespace gow3::win
