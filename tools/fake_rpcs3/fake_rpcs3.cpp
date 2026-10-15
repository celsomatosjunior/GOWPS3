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

namespace fs = std::filesystem;

int wmain(int argc, wchar_t** argv)
{
	wchar_t env[4096] = {};
	std::wstring dir;
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
