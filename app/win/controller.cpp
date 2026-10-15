// SPDX-License-Identifier: GPL-2.0-only
#include "controller.hpp"

#include "../core/diagnostics.hpp"
#include "../core/psf.hpp"

#include <chrono>
#include <ctime>
#include <cstdio>
#include <set>
#include <thread>

namespace gow3 {

std::string format_findings(const Findings& findings)
{
	std::string out;
	for (const auto& f : findings)
		out += std::string("[") + level_tag(f.level) + "] " + f.message + "\n";
	return out;
}

Controller::Controller(Layout layout) : layout_(std::move(layout)) {}

void Controller::load_settings()
{
	std::string text;
	settings_ = read_file(layout_.settings_file(), text) ? parse_settings(text) : Settings{};
}

void Controller::save_settings()
{
	write_file(layout_.settings_file(), serialize_settings(settings_));
}

void Controller::log(const std::string& message)
{
	std::lock_guard lock(log_mutex_);
	const std::time_t now = std::time(nullptr);
	char stamp[32] = {};
	std::strftime(stamp, sizeof(stamp), "%Y-%m-%d %H:%M:%S", std::localtime(&now));
	std::error_code ec;
	fs::create_directories(layout_.launcher_log().parent_path(), ec);
	std::string existing;
	read_file(layout_.launcher_log(), existing);
	if (existing.size() > 2 * 1024 * 1024)
		existing = existing.substr(existing.size() - 1024 * 1024);
	write_file(layout_.launcher_log(), existing + stamp + "  " + message + "\n");
}

std::vector<std::pair<std::string, std::string>> Controller::rpcs3_environment() const
{
	return {{"RPCS3_CONFIG_DIR", layout_.config_dir_env()}};
}

std::string Controller::installed_update(const std::string& serial) const
{
	std::string raw;
	if (serial.empty() || !read_file(layout_.game_updates() / serial / "PARAM.SFO", raw))
		return {};
	const auto sfo = psf::parse(raw);
	return sfo ? psf::get_string(*sfo, "APP_VER") : std::string();
}

Findings Controller::preflight()
{
	Findings out = check_runtime(layout_, false);
	game_ = inspect_game(utf8_to_path(settings_.game_path));
	out.insert(out.end(), game_.findings.begin(), game_.findings.end());

	if (firmware_installed(layout_)) {
		const std::string version = installed_firmware(layout_);
		out.push_back({Level::ok, "Firmware do PS3 instalado: " + (version.empty() ? std::string("versão desconhecida") : version)});
		if (!game_.required_firmware.empty() && !version.empty() && compare_versions(version, game_.required_firmware) < 0)
			out.push_back({Level::error, "O jogo pede firmware " + game_.required_firmware + "; o instalado é " + version + "."});
	} else {
		out.push_back({Level::error, "Firmware do PS3 não instalado. Baixe o PS3UPDAT.PUP no site oficial da PlayStation "
		                             "e clique em 'Instalar firmware'."});
	}
	if (!game_.serial.empty()) {
		const std::string update = installed_update(game_.serial);
		out.push_back(update.empty() ? Finding{Level::warning, "Nenhuma atualização do jogo instalada (opcional)."}
		                             : Finding{Level::ok, "Atualização do jogo instalada: versão " + update});
	}
	out.push_back({Level::ok, "Salvamentos: " + path_to_utf8(layout_.savedata())});
	ready_ = !has_error(out);
	return out;
}

void* Controller::start_game(std::string& error)
{
	if (!ready_) {
		error = "Resolva os itens marcados como ERRO na aba HOME.";
		return nullptr;
	}
	try {
		if (!write_file(layout_.override_config(), rpcs3_yaml(settings_))) {
			error = "Não foi possível gravar " + path_to_utf8(layout_.override_config());
			return nullptr;
		}
	} catch (const std::exception& e) {
		error = std::string("Configuração inválida: ") + e.what();
		return nullptr;
	}
	const auto args = boot_arguments(layout_.override_config(), game_.boot_path, settings_.fullscreen);
	log("Iniciando: " + windows_command_line(layout_.rpcs3_exe(), args));
	void* handle = win::start_process(layout_.rpcs3_exe(), args, rpcs3_environment(), error);
	if (!handle)
		log("Falha ao iniciar o RPCS3: " + error);
	return handle;
}

Findings Controller::after_game_exit(unsigned long code)
{
	char hex[16];
	std::snprintf(hex, sizeof(hex), "0x%08lX", code);
	log(std::string("RPCS3 terminou com código ") + hex);
	Findings out;
	std::string text;
	if (read_file(layout_.rpcs3_log(), text))
		for (const auto& explanation : analyse_log(text).explanations)
			out.push_back({Level::error, explanation});
	if (code == 0xC0000135)
		out.push_back({Level::error, "Faltou uma DLL ao iniciar o RPCS3. Rode ADVANCED > Autoteste do pacote."});
	if (code != 0 && out.empty())
		out.push_back({Level::warning, std::string("O RPCS3 terminou com código ") + hex + ". Veja ADVANCED > Diagnóstico."});
	return out;
}

Findings Controller::install_firmware(const fs::path& pup)
{
	Findings out;
	if (to_lower(path_to_utf8(pup.filename())) != "ps3updat.pup") {
		out.push_back({Level::error, "Escolha o arquivo PS3UPDAT.PUP."});
		return out;
	}
	log("Instalando firmware: " + path_to_utf8(pup));
	const auto result = win::run_process(layout_.rpcs3_exe(), install_firmware_arguments(pup), rpcs3_environment(), 0);
	if (!result.started) {
		out.push_back({Level::error, "Não foi possível iniciar o RPCS3: " + result.error});
		return out;
	}
	log("Instalação de firmware terminou com código " + std::to_string(result.exit_code));
	if (firmware_installed(layout_))
		out.push_back({Level::ok, "Firmware instalado: " + installed_firmware(layout_)});
	else
		out.push_back({Level::error, "O firmware não foi instalado. Veja ADVANCED > Diagnóstico."});
	return out;
}

bool Controller::open_rpcs3_settings(std::string& error)
{
	void* handle = win::start_process(layout_.rpcs3_exe(), {}, rpcs3_environment(), error);
	if (!handle)
		return false;
	std::thread([handle] { win::wait_process(handle); }).detach();
	return true;
}

Findings Controller::check_game_integrity(bool reset_reference)
{
	if (!game_.ok())
		return {{Level::error, "Escolha uma pasta válida do jogo primeiro."}};
	const Manifest current = build_manifest(game_.game_dir);
	std::string saved_text;
	if (reset_reference || !read_file(layout_.game_manifest(), saved_text)) {
		write_file(layout_.game_manifest(), serialize_manifest(current));
		return {{Level::ok, "Referência criada com " + std::to_string(current.size()) +
		                        " arquivos. As próximas verificações comparam com ela."}};
	}
	return compare_manifest(parse_manifest(saved_text), current);
}

Findings Controller::clear_game_cache()
{
	if (game_.serial.empty())
		return {{Level::error, "Escolha o jogo primeiro."}};
	const fs::path target = layout_.cache_dir() / game_.serial;
	std::error_code ec;
	const auto removed = fs::remove_all(target, ec);
	if (ec)
		return {{Level::error, "Não foi possível apagar " + path_to_utf8(target) + ": " + ec.message()}};
	log("Cache apagado: " + path_to_utf8(target));
	return {{Level::ok, std::to_string(removed) + " itens apagados de " + path_to_utf8(target) +
	                        ". O código e os shaders serão recompilados no próximo início."}};
}

std::string Controller::diagnostics_text()
{
	std::string text;
	if (!read_file(layout_.rpcs3_log(), text))
		return "Nenhum log do RPCS3 ainda (" + path_to_utf8(layout_.rpcs3_log()) + ").\r\n";
	const LogReport report = analyse_log(text);
	Findings findings;
	for (const auto& e : report.explanations)
		findings.push_back({Level::warning, e});
	for (const auto& f : report.fatal)
		findings.push_back({Level::error, f});
	if (findings.empty())
		findings.push_back({Level::ok, "Sem erros fatais. " + std::to_string(report.errors) + " erros e " +
		                                   std::to_string(report.warnings) + " avisos no log."});
	return "Log: " + path_to_utf8(layout_.rpcs3_log()) + "\n\n" + format_findings(findings) +
	       "\nÚltimas linhas:\n" + log_tail(text, 60);
}

bool Controller::self_test(std::string& report, bool allow_missing_vulkan)
{
	bool ok = true;
	auto section = [&](const std::string& title, const Findings& findings) {
		report += "\n== " + title + " ==\n" + format_findings(findings);
		if (has_error(findings))
			ok = false;
	};
	report = std::string(app_name) + " " + app_version + " - autoteste do pacote\n";
	report += "Pasta do aplicativo: " + path_to_utf8(layout_.app_dir) + "\n";
	report += "Pasta de dados: " + path_to_utf8(layout_.user_dir) + "\n";

	// 1. Componentes
	section("1. Componentes do RPCS3 (tamanho e SHA-256)", check_runtime(layout_, true));

	// 2. DLLs importadas por cada .exe e .dll do runtime
	Findings dll_findings;
	size_t images = 0, imports = 0;
	bool vulkan_missing = false;
	std::set<std::string> missing, optional_missing;
	std::error_code ec;
	if (fs::is_directory(layout_.runtime_dir, ec)) {
		for (auto it = fs::recursive_directory_iterator(layout_.runtime_dir, ec); it != fs::recursive_directory_iterator(); it.increment(ec)) {
			if (ec || !it->is_regular_file(ec))
				continue;
			const std::string ext = to_lower(path_to_utf8(it->path().extension()));
			if (ext != ".exe" && ext != ".dll")
				continue;
			std::string image;
			if (!read_file(it->path(), image))
				continue;
			const PeImports pe = read_pe_imports(image);
			if (!pe.valid)
				continue;
			images++;
			// Plugins do Qt são carregados sob demanda: se um deles não carrega, só aquele recurso some.
			const std::string relative = to_lower(generic_utf8(fs::relative(it->path(), layout_.runtime_dir, ec)));
			auto& missing_list = relative.rfind("qt6/plugins/", 0) == 0 ? optional_missing : missing;
			for (const auto& dll : pe.dlls) {
				if (is_api_set(dll))
					continue;
				imports++;
				// O processo roda a partir de runtime\rpcs3: plugins do Qt também enxergam essa pasta.
				win::DllLocation found = win::resolve_dll(dll, it->path().parent_path());
				if (found.source == win::DllSource::not_found || found.source == win::DllSource::path) {
					const win::DllLocation root = win::resolve_dll(dll, layout_.runtime_dir);
					if (root.source == win::DllSource::local)
						found = root;
				}
				const std::string lower = to_lower(dll);
				if (lower == "vulkan-1.dll") {
					// Vem do driver de vídeo, nunca do pacote.
					if (found.source == win::DllSource::not_found)
						vulkan_missing = true;
					continue;
				}
				const bool vc_runtime = lower.rfind("msvcp", 0) == 0 || lower.rfind("vcruntime", 0) == 0 ||
				                        lower.rfind("concrt", 0) == 0 || lower.rfind("vcomp", 0) == 0;
				if (found.source == win::DllSource::local)
					continue;
				if (found.source == win::DllSource::system && !vc_runtime)
					continue; // DLL do Windows
				if (found.source != win::DllSource::not_found) {
					// Achou fora do pacote (PATH ou Visual C++ instalado): num PC limpo faltaria.
					missing_list.insert(dll + " (usada por " + generic_utf8(fs::relative(it->path(), layout_.runtime_dir, ec)) +
					               "; encontrada só fora do pacote, em " + path_to_utf8(found.file) + ")");
					continue;
				}
				missing_list.insert(dll + " (usada por " + generic_utf8(fs::relative(it->path(), layout_.runtime_dir, ec)) + ")");
			}
		}
	}
	for (const auto& m : missing)
		dll_findings.push_back({Level::error, "DLL ausente: " + m});
	for (const auto& m : optional_missing)
		dll_findings.push_back({Level::warning, "DLL ausente para um plugin opcional do Qt: " + m});
	if (vulkan_missing)
		dll_findings.push_back({allow_missing_vulkan ? Level::warning : Level::error,
		                        "vulkan-1.dll não existe nesta máquina: ela vem com o driver de vídeo, não com o pacote."});
	if (images == 0)
		dll_findings.push_back({Level::error, "Nenhum executável encontrado em " + path_to_utf8(layout_.runtime_dir)});
	else if (missing.empty())
		dll_findings.push_back({Level::ok, std::to_string(images) + " executáveis/DLLs analisados, " + std::to_string(imports) +
		                                       " importações resolvidas"});
	section("2. Dependências (DLLs)", dll_findings);

	// 3. Pasta de dados e configuração
	Findings data;
	data.push_back(win::directory_writable(layout_.user_dir) ? Finding{Level::ok, "Pasta de dados gravável"}
	                                                         : Finding{Level::error, "Sem permissão de escrita em " + path_to_utf8(layout_.user_dir)});
	try {
		write_file(layout_.override_config(), rpcs3_yaml(settings_));
		data.push_back({Level::ok, "Configuração do RPCS3 gerada: " + path_to_utf8(layout_.override_config())});
	} catch (const std::exception& e) {
		data.push_back({Level::error, std::string("Configuração inválida: ") + e.what()});
	}
	section("3. Dados do usuário", data);

	// 4. Execução real do RPCS3 embutido
	Findings run;
	if (vulkan_missing && allow_missing_vulkan) {
		run.push_back({Level::warning, "Execução do RPCS3 pulada: sem vulkan-1.dll o Windows não carrega o rpcs3.exe."});
	} else {
		std::error_code rm;
		fs::remove(layout_.rpcs3_log(), rm);
		// Sem console, o Qt mostraria o --version numa caixa de diálogo (QCommandLineParser no Windows);
		// esta variável do Qt manda o texto para a saída padrão, que o autoteste captura.
		auto env = rpcs3_environment();
		env.emplace_back("QT_COMMAND_LINE_PARSER_NO_GUI_MESSAGE_BOXES", "1");
		const auto result = win::run_process(layout_.rpcs3_exe(), version_arguments(), env, 120000);
		char hex[16];
		std::snprintf(hex, sizeof(hex), "0x%08lX", result.exit_code);
		if (!result.started)
			run.push_back({Level::error, "rpcs3.exe não iniciou: " + result.error});
		else if (result.timed_out)
			run.push_back({Level::error, "rpcs3.exe --version não terminou em 120 s"});
		else if (result.exit_code != 0)
			run.push_back({Level::error, std::string("rpcs3.exe --version terminou com código ") + hex +
			                                 (result.exit_code == 0xC0000135 ? " (DLL ausente)" : "")});
		else
			run.push_back({Level::ok, "rpcs3.exe executou e respondeu: " + trim(result.output.empty() ? std::string("(sem texto)") : result.output)});
		if (result.started && !result.timed_out && result.exit_code == 0)
			run.push_back(fs::is_regular_file(layout_.rpcs3_log(), rm)
			                  ? Finding{Level::ok, "O RPCS3 gravou o log dentro da pasta do pacote: " + path_to_utf8(layout_.rpcs3_log())}
			                  : Finding{Level::error, "O RPCS3 não gravou o log em " + path_to_utf8(layout_.rpcs3_log()) +
			                                              " (isolamento por RPCS3_CONFIG_DIR falhou)"});
	}
	section("4. Execução do RPCS3 embutido", run);

	// 5. Computador (informativo)
	report += "\n== 5. Computador (informativo) ==\n" + format_findings(win::evaluate_system(win::collect_system_info()));
	report += std::string("\nRESULTADO: ") + (ok ? "APROVADO" : "REPROVADO") + "\n";
	report += "Observação: este autoteste não executa God of War III; ele confirma que o pacote está completo e que o "
	          "RPCS3 embutido inicia.\n";
	return ok;
}

} // namespace gow3
