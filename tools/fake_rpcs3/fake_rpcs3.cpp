// SPDX-License-Identifier: GPL-2.0-only
// RPCS3 FALSO, só para testes do GOW3_PS3_PC.exe sem o emulador real.
// Reproduz o contrato observado no código do RPCS3: RPCS3_CONFIG_DIR cortado na última barra,
// log em <config>/log/RPCS3.log, --headless --version, --headless --installfw, --no-gui --config.
#include <windows.h>
#include <cstdio>
#include <string>
#include <filesystem>
#include <fstream>

extern "C" __declspec(dllimport) int fake_qt_version();
#ifdef WITH_VCRUNTIME
// Importa uma função do VCRUNTIME140.dll, como o rpcs3.exe oficial (compilado com MSVC) faz.
extern "C" __declspec(dllimport) const void* vcr_memchr(const void*, int, size_t);
#endif

namespace fs = std::filesystem;

#ifdef WITH_CONTRACT
#include "contract_strings.inc"
#endif

int wmain(int argc, wchar_t** argv)
{
	wchar_t env[4096] = {};
	std::wstring dir;
#ifdef WITH_VCRUNTIME
	if (argc > 98) std::printf("%p", vcr_memchr("abc", 98, 3));
#endif
#ifdef WITH_CONTRACT
	if (argc > 99) std::puts(contract_strings[0]);
#endif
	if (GetEnvironmentVariableW(L"RPCS3_CONFIG_DIR", env, 4096)) {
		dir = env;
		for (auto& c : dir) if (c == L'\\') c = L'/';
		dir.resize(dir.rfind(L'/') + 1); // mesmo corte do fs::get_config_dir
	} else {
		dir = fs::path(argv[0]).parent_path().wstring() + L"/";
	}
	fs::create_directories(fs::path(dir) / "log");
	std::ofstream log(fs::path(dir) / "log" / "RPCS3.log", std::ios::app);
	log << "\xC2\xB7! 0:00:00.000000 SYS: RPCS3 FALSO (qt " << fake_qt_version() << ")\n";
	std::ofstream args(fs::path(dir) / "fake_args.txt");
	for (int i = 1; i < argc; i++) {
		char buf[4096];
		WideCharToMultiByte(CP_UTF8, 0, argv[i], -1, buf, sizeof(buf), nullptr, nullptr);
		args << buf << "\n";
	}
	for (int i = 1; i < argc; i++) {
		if (std::wstring(argv[i]) == L"--version" && GetEnvironmentVariableW(L"FAKE_RPCS3_HANG", nullptr, 0)) {
			MessageBoxW(nullptr, L"Erro fatal de teste", L"RPCS3", MB_OK); // simula report_fatal_error
			return 1;
		}
		if (std::wstring(argv[i]) == L"--version") {
			std::printf("RPCS3 0.0.0-falso\n");
			return 0;
		}
		if (std::wstring(argv[i]) == L"--installfw" && i + 1 < argc) {
			fs::create_directories(fs::path(dir) / "dev_flash/sys/external");
			fs::create_directories(fs::path(dir) / "dev_flash/vsh/etc");
			std::ofstream(fs::path(dir) / "dev_flash/sys/external/liblv2.sprx") << "x";
			std::ofstream(fs::path(dir) / "dev_flash/vsh/etc/version.txt") << "release:04.9200:\n";
			return 0;
		}
		if (std::wstring(argv[i]) == L"--no-gui") {
			log << "\xC2\xB7" "E 0:00:01.000000 SYS: Booting with cli argument failed: reason: Firmware is too old\n";
			return 7;
		}
	}
	return 0;
}
