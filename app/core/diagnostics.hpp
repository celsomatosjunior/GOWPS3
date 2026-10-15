// SPDX-License-Identifier: GPL-2.0-only
// Leitura do RPCS3.log e verificação das DLLs importadas pelos executáveis do runtime.
#pragma once

#include "common.hpp"

#include <optional>

namespace gow3 {

struct LogReport {
	bool found = false;
	std::vector<std::string> fatal;
	size_t errors = 0, warnings = 0;
	std::vector<std::string> explanations;
};

// Prefixos de nível conferidos em rpcs3/util/logs.cpp ("·F " fatal, "·E " erro, "·W " aviso).
LogReport analyse_log(const std::string& text);
std::string log_tail(const std::string& text, size_t lines);

// Nomes das DLLs importadas (tabela de importação normal e "delay load") de um PE x64.
struct PeImports {
	bool valid = false;
	bool is_x64 = false;
	std::vector<std::string> dlls;
	std::vector<std::string> delay_dlls;
};
PeImports read_pe_imports(const std::string& image);

// DLLs do Visual C++ e o carregador Vulkan: o RPCS3 só aceita essas DLLs carregadas da pasta do
// Windows (rpcs3/module_verifier.cpp); cópias ao lado do rpcs3.exe causam "Fatal Error".
bool is_vc_runtime(std::string_view dll);

// DLLs que o Windows resolve sozinho (API sets).
bool is_api_set(std::string_view dll);

} // namespace gow3
