// SPDX-License-Identifier: GPL-2.0-only
// GOW3_PS3_PC.exe: ponto de entrada.
//   (sem argumentos)          abre a janela
//   --check                   verifica pacote, jogo, firmware e computador; código 0 = pronto para jogar
//   --selftest                autoteste do pacote (usado na compilação); código 0 = aprovado
//     --allow-missing-vulkan  em máquinas sem driver de vídeo (servidor de compilação)
//   --report <arquivo>        grava também o relatório nesse arquivo
//   --user-dir <pasta>        usa outra pasta de dados
//   --game <pasta>            grava a pasta do jogo nas configurações
//   --install-firmware <PUP>  instala o firmware do PS3 fornecido pelo usuário
//   --play                    inicia o jogo direto com as configurações salvas (atalhos, Steam)
//   --version
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <objbase.h>
#include <shellapi.h>

#include "controller.hpp"
#include "ui.hpp"

using namespace gow3;

namespace {

void write_out(const std::string& text)
{
	HANDLE out = GetStdHandle(STD_OUTPUT_HANDLE);
	if (!out || out == INVALID_HANDLE_VALUE || GetFileType(out) == FILE_TYPE_UNKNOWN) {
		if (AttachConsole(ATTACH_PARENT_PROCESS))
			out = GetStdHandle(STD_OUTPUT_HANDLE);
	}
	if (!out || out == INVALID_HANDLE_VALUE)
		return;
	DWORD written = 0;
	if (GetFileType(out) == FILE_TYPE_CHAR) {
		const std::wstring wide = win::widen(text);
		if (WriteConsoleW(out, wide.c_str(), static_cast<DWORD>(wide.size()), &written, nullptr))
			return;
	}
	WriteFile(out, text.data(), static_cast<DWORD>(text.size()), &written, nullptr);
}

fs::path choose_user_dir(const fs::path& app_dir)
{
	// Pacote portátil: tudo fica em "user" ao lado do .exe. Se a pasta não for gravável
	// (ex.: Arquivos de Programas), usa %LOCALAPPDATA%\GOW3_PS3_PC\user.
	if (win::directory_writable(app_dir / "user"))
		return app_dir / "user";
	wchar_t local[MAX_PATH] = {};
	if (GetEnvironmentVariableW(L"LOCALAPPDATA", local, MAX_PATH))
		return fs::path(local) / L"GOW3_PS3_PC" / L"user";
	return app_dir / "user";
}

} // namespace

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE, PWSTR, int)
{
	int argc = 0;
	wchar_t** argv = CommandLineToArgvW(GetCommandLineW(), &argc);
	std::vector<std::string> args;
	for (int i = 1; i < argc; i++)
		args.push_back(win::narrow(argv[i]));
	LocalFree(argv);
	auto flag = [&](const char* name) { return std::find(args.begin(), args.end(), name) != args.end(); };
	auto value = [&](const char* name) -> std::string {
		const auto it = std::find(args.begin(), args.end(), name);
		return it != args.end() && it + 1 != args.end() ? *(it + 1) : std::string();
	};

	if (flag("--version")) {
		write_out(std::string(app_name) + " " + app_version + "\n");
		return 0;
	}

	const fs::path app_dir = win::executable_dir();
	const std::string user_override = value("--user-dir");
	Controller controller(Layout::from_app_dir(app_dir, user_override.empty() ? choose_user_dir(app_dir) : utf8_to_path(user_override)));
	controller.load_settings();
	if (const std::string game = value("--game"); !game.empty()) {
		controller.settings().game_path = game;
		controller.save_settings();
	}
	if (const std::string pup = value("--install-firmware"); !pup.empty()) {
		const Findings findings = controller.install_firmware(utf8_to_path(pup));
		write_out(format_findings(findings));
		return has_error(findings) ? 1 : 0;
	}
	if (flag("--play")) {
		const Findings findings = controller.preflight();
		if (!controller.ready()) {
			write_out(format_findings(findings));
			MessageBoxW(nullptr, win::widen("Ainda não está pronto para jogar:\n\n" + format_findings(findings)).c_str(),
			            L"GOW3 PS3 PC", MB_ICONERROR);
			return 2;
		}
		std::string error;
		void* process = controller.start_game(error);
		if (!process) {
			write_out(error + "\n");
			return 3;
		}
		const unsigned long code = win::wait_process(process);
		const Findings problems = controller.after_game_exit(code);
		write_out(format_findings(problems));
		return static_cast<int>(code);
	}

	if (flag("--selftest") || flag("--check")) {
		std::string report;
		int code;
		if (flag("--selftest")) {
			code = controller.self_test(report, flag("--allow-missing-vulkan")) ? 0 : 1;
			write_file(controller.layout().selftest_report(), report);
		} else {
			const Findings findings = controller.preflight();
			report = std::string(app_name) + " " + app_version + " - verificação\n\n" + format_findings(findings) +
			         "\nComputador\n" + format_findings(win::evaluate_system(win::collect_system_info())) +
			         (controller.ready() ? "\nPronto para jogar.\n" : "\nAinda não está pronto: resolva os itens ERRO.\n");
			code = controller.ready() ? 0 : 2;
		}
		const std::string report_path = value("--report");
		if (!report_path.empty())
			write_file(utf8_to_path(report_path), report);
		write_out(report);
		controller.log(std::string(flag("--selftest") ? "Autoteste" : "Verificação") + " terminou com código " + std::to_string(code));
		return code;
	}

	HANDLE mutex = CreateMutexW(nullptr, TRUE, L"Local\\GOW3_PS3_PC_single_instance");
	if (GetLastError() == ERROR_ALREADY_EXISTS) {
		if (HWND existing = FindWindowW(L"GOW3PS3PCWindow", nullptr)) {
			ShowWindow(existing, SW_RESTORE);
			SetForegroundWindow(existing);
		}
		return 0;
	}
	CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE);
	controller.log(std::string("Aberto: ") + app_name + " " + app_version + " em " + path_to_utf8(app_dir));
	const int code = run_window(instance, controller);
	CoUninitialize();
	if (mutex)
		CloseHandle(mutex);
	return code;
}
