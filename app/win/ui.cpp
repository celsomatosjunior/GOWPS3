// SPDX-License-Identifier: GPL-2.0-only
// Janela principal (API Win32 pura: não depende de Qt nem de outras DLLs além do Windows).
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <commctrl.h>
#include <shobjidl.h>

#include <functional>
#include <memory>
#include <thread>

#include "controller.hpp"
#include "ui.hpp"

namespace gow3 {
namespace {

enum : int {
	ID_TAB = 100, ID_GAME_PATH, ID_PICK_GAME, ID_STATUS, ID_FIRMWARE, ID_REFRESH, ID_PLAY,
	ID_RES, ID_SCALING, ID_ANISO, ID_VSYNC, ID_RCAS, ID_RCAS_VALUE, ID_FULLSCREEN,
	ID_FPS, ID_SHADER, ID_SPU_BLOCK, ID_SPU_THREADS, ID_ADAPTER, ID_WCB, ID_OVERLAY, ID_HINT,
	ID_RPCS3_SETTINGS,
	ID_DIAG, ID_INTEGRITY, ID_SELFTEST, ID_CLEAR_CACHE, ID_OPEN_DATA, ID_OPEN_SAVES, ID_OPEN_LOGS, ID_OUTPUT,
};

enum : UINT { WM_APP_SYSINFO = WM_APP + 1, WM_APP_GAME_EXIT, WM_APP_TASK_DONE };

struct TaskResult {
	int target;          // ID_STATUS ou ID_OUTPUT
	std::string text;
	bool refresh = false;
};

std::wstring crlf(const std::string& text)
{
	std::wstring wide = win::widen(text), out;
	for (wchar_t c : wide) {
		if (c == L'\n')
			out += L"\r\n";
		else if (c != L'\r')
			out.push_back(c);
	}
	return out;
}

class MainWindow {
public:
	MainWindow(HINSTANCE instance, Controller& controller) : instance_(instance), c_(controller) {}

	bool create();
	static LRESULT CALLBACK proc(HWND, UINT, WPARAM, LPARAM);

private:
	LRESULT handle(UINT msg, WPARAM wp, LPARAM lp);
	int px(int value) const { return MulDiv(value, dpi_, 96); }
	HWND add(int page, const wchar_t* cls, const std::wstring& text, DWORD style, int x, int y, int w, int h, int id = 0);
	HWND label(int page, const std::wstring& text, int x, int y, int w);
	HWND combo(int page, int id, const std::wstring& caption, int y, const OptionTable* table, const std::string& current);
	void build();
	void show_page(int page);
	void set_text(int id, const std::string& text);
	void refresh();
	void sync_controls();
	void on_command(int id, int code);
	void play();
	void run_task(int target, std::function<TaskResult()> work);
	std::wstring pick(bool folder, const wchar_t* title);

	HINSTANCE instance_;
	Controller& c_;
	HWND hwnd_ = nullptr, tab_ = nullptr;
	HFONT font_ = nullptr, big_font_ = nullptr, title_font_ = nullptr;
	int dpi_ = 96;
	std::vector<HWND> pages_[5];
	std::string system_text_ = "Verificando o computador...\n";
	std::vector<std::string> adapters_;
	bool game_running_ = false;
	bool busy_ = false;
};

HWND MainWindow::add(int page, const wchar_t* cls, const std::wstring& text, DWORD style, int x, int y, int w, int h, int id)
{
	HWND control = CreateWindowExW(0, cls, text.c_str(), WS_CHILD | style, px(x), px(y), px(w), px(h), hwnd_,
	                               reinterpret_cast<HMENU>(static_cast<INT_PTR>(id)), instance_, nullptr);
	SendMessageW(control, WM_SETFONT, reinterpret_cast<WPARAM>(font_), TRUE);
	if (page >= 0)
		pages_[page].push_back(control);
	else
		ShowWindow(control, SW_SHOW);
	return control;
}

HWND MainWindow::label(int page, const std::wstring& text, int x, int y, int w)
{
	return add(page, L"STATIC", text, SS_LEFT, x, y + 3, w, 20);
}

HWND MainWindow::combo(int page, int id, const std::wstring& caption, int y, const OptionTable* table, const std::string& current)
{
	label(page, caption, 36, y, 230);
	HWND box = add(page, WC_COMBOBOXW, L"", CBS_DROPDOWNLIST | WS_VSCROLL | WS_TABSTOP, 270, y, 330, 300, id);
	if (table) {
		for (size_t i = 0; i < table->options.size(); i++) {
			SendMessageW(box, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(win::widen(table->options[i].label).c_str()));
			if (table->options[i].id == current)
				SendMessageW(box, CB_SETCURSEL, i, 0);
		}
	}
	return box;
}

void MainWindow::build()
{
	NONCLIENTMETRICSW metrics{};
	metrics.cbSize = sizeof(metrics);
	SystemParametersInfoW(SPI_GETNONCLIENTMETRICS, sizeof(metrics), &metrics, 0);
	LOGFONTW lf = metrics.lfMessageFont;
	lf.lfHeight = -px(15);
	font_ = CreateFontIndirectW(&lf);
	lf.lfHeight = -px(20);
	lf.lfWeight = FW_BOLD;
	big_font_ = CreateFontIndirectW(&lf);
	lf.lfHeight = -px(26);
	title_font_ = CreateFontIndirectW(&lf);

	HWND title = add(-1, L"STATIC", L"GOW3 PS3 PC", SS_LEFT, 20, 12, 205, 34);
	SendMessageW(title, WM_SETFONT, reinterpret_cast<WPARAM>(title_font_), TRUE);
	add(-1, L"STATIC",
	    win::widen(std::string("God of War III (PS3) · RPCS3 embutido · v") + app_version +
	               " · sem afiliação com a Sony"),
	    SS_LEFT, 230, 22, 660, 20);

	tab_ = CreateWindowExW(0, WC_TABCONTROLW, L"", WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS | WS_TABSTOP, px(12), px(54),
	                       px(876), px(560), hwnd_, reinterpret_cast<HMENU>(ID_TAB), instance_, nullptr);
	SendMessageW(tab_, WM_SETFONT, reinterpret_cast<WPARAM>(font_), TRUE);
	const wchar_t* names[] = {L"HOME", L"GRAPHICS", L"PERFORMANCE", L"CONTROLS", L"ADVANCED"};
	for (int i = 0; i < 5; i++) {
		TCITEMW item{};
		item.mask = TCIF_TEXT;
		item.pszText = const_cast<wchar_t*>(names[i]);
		SendMessageW(tab_, TCM_INSERTITEMW, i, reinterpret_cast<LPARAM>(&item));
	}
	const Settings& s = c_.settings();

	// HOME
	label(0, L"Pasta do jogo:", 36, 100, 110);
	add(0, L"EDIT", win::widen(s.game_path), ES_AUTOHSCROLL | ES_READONLY | WS_BORDER, 150, 98, 560, 26, ID_GAME_PATH);
	add(0, L"BUTTON", L"Escolher...", BS_PUSHBUTTON | WS_TABSTOP, 720, 97, 140, 28, ID_PICK_GAME);
	add(0, L"EDIT", L"", ES_MULTILINE | ES_READONLY | WS_VSCROLL | WS_BORDER, 36, 136, 824, 390, ID_STATUS);
	add(0, L"BUTTON", L"Instalar firmware...", BS_PUSHBUTTON | WS_TABSTOP, 36, 546, 170, 40, ID_FIRMWARE);
	add(0, L"BUTTON", L"Verificar de novo", BS_PUSHBUTTON | WS_TABSTOP, 216, 546, 150, 40, ID_REFRESH);
	HWND play_button = add(0, L"BUTTON", L"JOGAR", BS_DEFPUSHBUTTON | WS_TABSTOP, 680, 538, 180, 52, ID_PLAY);
	SendMessageW(play_button, WM_SETFONT, reinterpret_cast<WPARAM>(big_font_), TRUE);

	// GRAPHICS
	combo(1, ID_RES, L"Resolução interna", 100, &internal_resolution_table(), s.internal_resolution);
	combo(1, ID_SCALING, L"Escalonamento para a tela", 140, &scaling_table(), s.output_scaling);
	label(1, L"Nitidez RCAS (com FSR)", 36, 180, 230);
	HWND rcas = add(1, TRACKBAR_CLASSW, L"", TBS_HORZ | TBS_NOTICKS | WS_TABSTOP, 266, 178, 280, 30, ID_RCAS);
	SendMessageW(rcas, TBM_SETRANGE, TRUE, MAKELPARAM(0, 100));
	SendMessageW(rcas, TBM_SETPOS, TRUE, s.rcas_sharpening);
	add(1, L"STATIC", std::to_wstring(s.rcas_sharpening) + L"%", SS_LEFT, 556, 183, 60, 20, ID_RCAS_VALUE);
	combo(1, ID_ANISO, L"Filtragem anisotrópica", 220, &anisotropic_table(), s.anisotropic);
	combo(1, ID_VSYNC, L"VSync", 260, &vsync_table(), s.vsync);
	add(1, L"BUTTON", L"Tela cheia", BS_AUTOCHECKBOX | WS_TABSTOP, 36, 302, 300, 24, ID_FULLSCREEN);
	add(1, L"STATIC",
	    L"Renderizador: Vulkan. A resolução interna multiplica os 1280x720 originais do jogo.\r\n"
	    L"FSR 1 e RCAS são do próprio RPCS3. DLSS, XeSS e FSR 3/4 não são suportados.",
	    SS_LEFT, 36, 350, 820, 60);

	// PERFORMANCE
	combo(2, ID_FPS, L"Limite de FPS", 100, &frame_limit_table(), s.frame_limit);
	combo(2, ID_SHADER, L"Compilação de shaders", 140, &shader_mode_table(), s.shader_mode);
	combo(2, ID_SPU_BLOCK, L"Tamanho de bloco SPU", 180, &spu_block_table(), s.spu_block_size);
	HWND threads = combo(2, ID_SPU_THREADS, L"Threads SPU preferidas", 220, nullptr, "");
	for (int i = 0; i <= 6; i++)
		SendMessageW(threads, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(i ? std::to_wstring(i).c_str() : L"Automático"));
	SendMessageW(threads, CB_SETCURSEL, s.preferred_spu_threads, 0);
	HWND adapter = combo(2, ID_ADAPTER, L"Placa de vídeo (Vulkan)", 260, nullptr, "");
	SendMessageW(adapter, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(L"Automático (o RPCS3 escolhe)"));
	SendMessageW(adapter, CB_SETCURSEL, 0, 0);
	add(2, L"BUTTON", L"Write Color Buffers (recomendado pela wiki do RPCS3 para este jogo)", BS_AUTOCHECKBOX | WS_TABSTOP, 36, 302, 600, 24, ID_WCB);
	add(2, L"BUTTON", L"Mostrar overlay de desempenho do RPCS3 (FPS, CPU, GPU)", BS_AUTOCHECKBOX | WS_TABSTOP, 36, 332, 600, 24, ID_OVERLAY);
	add(2, L"BUTTON", L"Avisar na tela quando estiver compilando shaders", BS_AUTOCHECKBOX | WS_TABSTOP, 36, 362, 600, 24, ID_HINT);
	add(2, L"STATIC",
	    L"O código PPU/SPU traduzido e os shaders ficam em cache na pasta user\\rpcs3\\cache e são reaproveitados.\r\n"
	    L"FPS acima de 60 depende de patch do jogo e não está habilitado nesta versão.",
	    SS_LEFT, 36, 410, 820, 60);

	// CONTROLS
	add(3, L"STATIC",
	    L"Os controles usam o sistema do RPCS3 embutido: Xbox (XInput), DualSense, DualShock 4, controles SDL e teclado.\r\n\r\n"
	    L"O botão abaixo abre a janela do RPCS3 usando a pasta de dados deste aplicativo. Vá em Configuração > Controles,\r\n"
	    L"escolha o controle, salve e feche. A configuração passa a valer quando você clicar em JOGAR.",
	    SS_LEFT, 36, 100, 820, 110);
	add(3, L"BUTTON", L"Abrir configuração de controles (RPCS3)", BS_PUSHBUTTON | WS_TABSTOP, 36, 220, 320, 40, ID_RPCS3_SETTINGS);

	// ADVANCED
	const std::pair<int, const wchar_t*> buttons[] = {
		{ID_DIAG, L"Diagnóstico do log"}, {ID_SELFTEST, L"Autoteste do pacote"}, {ID_INTEGRITY, L"Verificar jogo"},
		{ID_CLEAR_CACHE, L"Limpar cache do jogo"}, {ID_OPEN_DATA, L"Pasta de dados"}, {ID_OPEN_SAVES, L"Salvamentos"},
		{ID_OPEN_LOGS, L"Logs"},
	};
	int x = 36;
	for (const auto& [id, text] : buttons) {
		const int w = static_cast<int>(wcslen(text)) * 7 + 14;
		add(4, L"BUTTON", text, BS_PUSHBUTTON | WS_TABSTOP, x, 98, w, 30, id);
		x += w + 6;
	}
	HWND output = add(4, L"EDIT", L"", ES_MULTILINE | ES_READONLY | WS_VSCROLL | WS_HSCROLL | WS_BORDER, 36, 140, 824, 450, ID_OUTPUT);
	HFONT mono = CreateFontW(-px(13), 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, FIXED_PITCH, L"Consolas");
	SendMessageW(output, WM_SETFONT, reinterpret_cast<WPARAM>(mono), TRUE);

	sync_controls();
	show_page(0);
}

void MainWindow::sync_controls()
{
	const Settings& s = c_.settings();
	CheckDlgButton(hwnd_, ID_FULLSCREEN, s.fullscreen ? BST_CHECKED : BST_UNCHECKED);
	CheckDlgButton(hwnd_, ID_WCB, s.write_color_buffers ? BST_CHECKED : BST_UNCHECKED);
	CheckDlgButton(hwnd_, ID_OVERLAY, s.performance_overlay ? BST_CHECKED : BST_UNCHECKED);
	CheckDlgButton(hwnd_, ID_HINT, s.shader_compilation_hint ? BST_CHECKED : BST_UNCHECKED);
}

void MainWindow::show_page(int page)
{
	for (int i = 0; i < 5; i++)
		for (HWND control : pages_[i])
			ShowWindow(control, i == page ? SW_SHOW : SW_HIDE);
}

void MainWindow::set_text(int id, const std::string& text)
{
	SetDlgItemTextW(hwnd_, id, crlf(text).c_str());
}

void MainWindow::refresh()
{
	if (busy_)
		return; // uma tarefa em segundo plano está usando o controlador
	const Findings findings = c_.preflight();
	set_text(ID_STATUS, format_findings(findings) + "\nComputador\n" + system_text_);
	EnableWindow(GetDlgItem(hwnd_, ID_PLAY), c_.ready() && !game_running_);
}

void MainWindow::run_task(int target, std::function<TaskResult()> work)
{
	if (busy_) {
		MessageBoxW(hwnd_, L"Aguarde a tarefa atual terminar.", L"GOW3 PS3 PC", MB_ICONINFORMATION);
		return;
	}
	busy_ = true;
	set_text(target, "Trabalhando...\n");
	HWND hwnd = hwnd_;
	std::thread([hwnd, work = std::move(work)] {
		auto* result = new TaskResult(work());
		PostMessageW(hwnd, WM_APP_TASK_DONE, 0, reinterpret_cast<LPARAM>(result));
	}).detach();
}

std::wstring MainWindow::pick(bool folder, const wchar_t* title)
{
	std::wstring result;
	IFileOpenDialog* dialog = nullptr;
	if (FAILED(CoCreateInstance(CLSID_FileOpenDialog, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&dialog))))
		return result;
	DWORD options = 0;
	dialog->GetOptions(&options);
	dialog->SetOptions(options | FOS_FORCEFILESYSTEM | (folder ? FOS_PICKFOLDERS : FOS_FILEMUSTEXIST));
	dialog->SetTitle(title);
	if (!folder) {
		const COMDLG_FILTERSPEC filter[] = {{L"Firmware do PS3 (PS3UPDAT.PUP)", L"*.PUP"}, {L"Todos os arquivos", L"*.*"}};
		dialog->SetFileTypes(2, filter);
	}
	if (SUCCEEDED(dialog->Show(hwnd_))) {
		IShellItem* item = nullptr;
		if (SUCCEEDED(dialog->GetResult(&item))) {
			wchar_t* path = nullptr;
			if (SUCCEEDED(item->GetDisplayName(SIGDN_FILESYSPATH, &path))) {
				result = path;
				CoTaskMemFree(path);
			}
			item->Release();
		}
	}
	dialog->Release();
	return result;
}

void MainWindow::play()
{
	if (busy_ || game_running_)
		return;
	std::string error;
	void* process = c_.start_game(error);
	if (!process) {
		MessageBoxW(hwnd_, crlf(error).c_str(), L"GOW3 PS3 PC", MB_ICONERROR);
		return;
	}
	game_running_ = true;
	EnableWindow(GetDlgItem(hwnd_, ID_PLAY), FALSE);
	SetDlgItemTextW(hwnd_, ID_PLAY, L"Em execução...");
	HWND hwnd = hwnd_;
	std::thread([hwnd, process] {
		const unsigned long code = win::wait_process(process);
		PostMessageW(hwnd, WM_APP_GAME_EXIT, static_cast<WPARAM>(code), 0);
	}).detach();
}

void MainWindow::on_command(int id, int code)
{
	Settings& s = c_.settings();
	auto selected = [&](int control) { return static_cast<int>(SendDlgItemMessageW(hwnd_, control, CB_GETCURSEL, 0, 0)); };
	auto table_choice = [&](int control, const OptionTable& table, std::string& field) {
		const int index = selected(control);
		if (index >= 0 && index < static_cast<int>(table.options.size()))
			field = table.options[static_cast<size_t>(index)].id;
	};

	if (code == CBN_SELCHANGE) {
		switch (id) {
		case ID_RES: table_choice(id, internal_resolution_table(), s.internal_resolution); break;
		case ID_SCALING: table_choice(id, scaling_table(), s.output_scaling); break;
		case ID_ANISO: table_choice(id, anisotropic_table(), s.anisotropic); break;
		case ID_VSYNC: table_choice(id, vsync_table(), s.vsync); break;
		case ID_FPS: table_choice(id, frame_limit_table(), s.frame_limit); break;
		case ID_SHADER: table_choice(id, shader_mode_table(), s.shader_mode); break;
		case ID_SPU_BLOCK: table_choice(id, spu_block_table(), s.spu_block_size); break;
		case ID_SPU_THREADS: s.preferred_spu_threads = std::max(0, selected(id)); break;
		case ID_ADAPTER: {
			const int index = selected(id);
			s.vulkan_adapter = index > 0 && index <= static_cast<int>(adapters_.size()) ? adapters_[static_cast<size_t>(index - 1)] : "";
			break;
		}
		default: return;
		}
		c_.save_settings();
		return;
	}
	if (code != BN_CLICKED)
		return;
	auto checked = [&](int control) { return IsDlgButtonChecked(hwnd_, control) == BST_CHECKED; };
	switch (id) {
	case ID_FULLSCREEN: s.fullscreen = checked(id); c_.save_settings(); break;
	case ID_WCB: s.write_color_buffers = checked(id); c_.save_settings(); break;
	case ID_OVERLAY: s.performance_overlay = checked(id); c_.save_settings(); break;
	case ID_HINT: s.shader_compilation_hint = checked(id); c_.save_settings(); break;
	case ID_PICK_GAME: {
		if (busy_)
			break;
		const std::wstring folder = pick(true, L"Pasta do God of War III (a que contém PS3_GAME)");
		if (!folder.empty()) {
			s.game_path = win::narrow(folder);
			c_.save_settings();
			SetDlgItemTextW(hwnd_, ID_GAME_PATH, folder.c_str());
			refresh();
		}
		break;
	}
	case ID_REFRESH: refresh(); break;
	case ID_PLAY: play(); break;
	case ID_FIRMWARE: {
		const std::wstring file = pick(false, L"Escolha o PS3UPDAT.PUP baixado do site oficial da PlayStation");
		if (!file.empty())
			run_task(ID_STATUS, [this, file] {
				return TaskResult{ID_STATUS, "Instalação de firmware:\n" + format_findings(c_.install_firmware(fs::path(file))), true};
			});
		break;
	}
	case ID_RPCS3_SETTINGS: {
		std::string error;
		if (!c_.open_rpcs3_settings(error))
			MessageBoxW(hwnd_, crlf("Não foi possível abrir o RPCS3: " + error).c_str(), L"GOW3 PS3 PC", MB_ICONERROR);
		break;
	}
	case ID_DIAG: set_text(ID_OUTPUT, c_.diagnostics_text()); break;
	case ID_SELFTEST:
		run_task(ID_OUTPUT, [this] {
			std::string report;
			c_.self_test(report, false);
			write_file(c_.layout().selftest_report(), report);
			return TaskResult{ID_OUTPUT, report};
		});
		break;
	case ID_INTEGRITY:
		run_task(ID_OUTPUT, [this] {
			return TaskResult{ID_OUTPUT, "Verificação do jogo (SHA-256 de todos os arquivos):\n" +
			                                 format_findings(c_.check_game_integrity(false))};
		});
		break;
	case ID_CLEAR_CACHE:
		if (MessageBoxW(hwnd_, L"Apagar o cache de código e shaders deste jogo?\r\nEle será recriado no próximo início (mais lento na primeira vez).",
		                L"GOW3 PS3 PC", MB_YESNO | MB_ICONQUESTION) == IDYES)
			set_text(ID_OUTPUT, format_findings(c_.clear_game_cache()));
		break;
	case ID_OPEN_DATA: win::open_folder(c_.layout().user_dir); break;
	case ID_OPEN_SAVES: win::open_folder(c_.layout().savedata()); break;
	case ID_OPEN_LOGS: win::open_folder(c_.layout().launcher_log().parent_path()); break;
	default: break;
	}
}

LRESULT MainWindow::handle(UINT msg, WPARAM wp, LPARAM lp)
{
	switch (msg) {
	case WM_COMMAND:
		on_command(LOWORD(wp), HIWORD(wp));
		return 0;
	case WM_NOTIFY:
		if (reinterpret_cast<NMHDR*>(lp)->idFrom == ID_TAB && reinterpret_cast<NMHDR*>(lp)->code == TCN_SELCHANGE)
			show_page(static_cast<int>(SendMessageW(tab_, TCM_GETCURSEL, 0, 0)));
		return 0;
	case WM_HSCROLL:
		if (reinterpret_cast<HWND>(lp) == GetDlgItem(hwnd_, ID_RCAS)) {
			c_.settings().rcas_sharpening = static_cast<int>(SendDlgItemMessageW(hwnd_, ID_RCAS, TBM_GETPOS, 0, 0));
			SetDlgItemTextW(hwnd_, ID_RCAS_VALUE, (std::to_wstring(c_.settings().rcas_sharpening) + L"%").c_str());
			if (LOWORD(wp) == TB_ENDTRACK || LOWORD(wp) == TB_THUMBPOSITION)
				c_.save_settings();
		}
		return 0;
	case WM_CTLCOLORSTATIC:
		SetBkMode(reinterpret_cast<HDC>(wp), TRANSPARENT);
		return reinterpret_cast<LRESULT>(GetSysColorBrush(COLOR_WINDOW));
	case WM_APP_SYSINFO: {
		std::unique_ptr<win::SystemInfo> info(reinterpret_cast<win::SystemInfo*>(lp));
		system_text_ = format_findings(win::evaluate_system(*info));
		HWND adapter = GetDlgItem(hwnd_, ID_ADAPTER);
		for (const auto& gpu : info->gpus) {
			adapters_.push_back(gpu.name);
			SendMessageW(adapter, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(win::widen(gpu.name).c_str()));
			if (gpu.name == c_.settings().vulkan_adapter)
				SendMessageW(adapter, CB_SETCURSEL, adapters_.size(), 0);
		}
		c_.log("Computador:\n" + system_text_);
		refresh();
		return 0;
	}
	case WM_APP_GAME_EXIT: {
		game_running_ = false;
		SetDlgItemTextW(hwnd_, ID_PLAY, L"JOGAR");
		const Findings problems = c_.after_game_exit(static_cast<unsigned long>(wp));
		refresh();
		if (!problems.empty())
			MessageBoxW(hwnd_, crlf(format_findings(problems)).c_str(), L"GOW3 PS3 PC", MB_ICONWARNING);
		return 0;
	}
	case WM_APP_TASK_DONE: {
		std::unique_ptr<TaskResult> result(reinterpret_cast<TaskResult*>(lp));
		busy_ = false;
		const std::string previous = result->target == ID_STATUS ? result->text + "\n" : std::string();
		if (result->target == ID_STATUS) {
			const Findings findings = c_.preflight();
			set_text(ID_STATUS, previous + format_findings(findings) + "\nComputador\n" + system_text_);
		} else {
			set_text(result->target, result->text);
		}
		return 0;
	}
	case WM_CLOSE:
		if (game_running_ && MessageBoxW(hwnd_, L"O jogo ainda está aberto. Fechar só esta janela?", L"GOW3 PS3 PC",
		                                 MB_YESNO | MB_ICONQUESTION) != IDYES)
			return 0;
		DestroyWindow(hwnd_);
		return 0;
	case WM_DESTROY:
		PostQuitMessage(0);
		return 0;
	default:
		return DefWindowProcW(hwnd_, msg, wp, lp);
	}
}

LRESULT CALLBACK MainWindow::proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
	if (msg == WM_NCCREATE) {
		auto* self = static_cast<MainWindow*>(reinterpret_cast<CREATESTRUCTW*>(lp)->lpCreateParams);
		self->hwnd_ = hwnd;
		SetWindowLongPtrW(hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(self));
	}
	auto* self = reinterpret_cast<MainWindow*>(GetWindowLongPtrW(hwnd, GWLP_USERDATA));
	return self ? self->handle(msg, wp, lp) : DefWindowProcW(hwnd, msg, wp, lp);
}

bool MainWindow::create()
{
	HDC screen = GetDC(nullptr);
	dpi_ = GetDeviceCaps(screen, LOGPIXELSY);
	ReleaseDC(nullptr, screen);

	WNDCLASSEXW wc{};
	wc.cbSize = sizeof(wc);
	wc.lpfnWndProc = proc;
	wc.hInstance = instance_;
	wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
	wc.hbrBackground = GetSysColorBrush(COLOR_WINDOW);
	wc.hIcon = LoadIconW(instance_, MAKEINTRESOURCEW(1));
	wc.lpszClassName = L"GOW3PS3PCWindow";
	RegisterClassExW(&wc);

	RECT rect{0, 0, px(900), px(630)};
	AdjustWindowRect(&rect, WS_OVERLAPPEDWINDOW & ~(WS_THICKFRAME | WS_MAXIMIZEBOX), FALSE);
	CreateWindowExW(0, wc.lpszClassName, L"GOW3 PS3 PC", WS_OVERLAPPEDWINDOW & ~(WS_THICKFRAME | WS_MAXIMIZEBOX),
	                CW_USEDEFAULT, CW_USEDEFAULT, rect.right - rect.left, rect.bottom - rect.top, nullptr, nullptr, instance_, this);
	if (!hwnd_)
		return false;
	build();
	refresh();
	ShowWindow(hwnd_, SW_SHOW);
	UpdateWindow(hwnd_);
	HWND hwnd = hwnd_;
	std::thread([hwnd] {
		auto* info = new win::SystemInfo(win::collect_system_info());
		PostMessageW(hwnd, WM_APP_SYSINFO, 0, reinterpret_cast<LPARAM>(info));
	}).detach();
	return true;
}

} // namespace

int run_window(void* instance_handle, Controller& controller)
{
	auto instance = static_cast<HINSTANCE>(instance_handle);
	INITCOMMONCONTROLSEX icc{sizeof(icc), ICC_TAB_CLASSES | ICC_BAR_CLASSES | ICC_STANDARD_CLASSES};
	InitCommonControlsEx(&icc);
	MainWindow window(instance, controller);
	if (!window.create())
		return 1;
	MSG msg;
	while (GetMessageW(&msg, nullptr, 0, 0) > 0) {
		if (!IsDialogMessageW(GetActiveWindow(), &msg)) {
			TranslateMessage(&msg);
			DispatchMessageW(&msg);
		}
	}
	return 0;
}

} // namespace gow3
