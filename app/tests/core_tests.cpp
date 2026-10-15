// SPDX-License-Identifier: GPL-2.0-only
// Testes do núcleo. Rodam em Linux e Windows (sem arquivos do jogo: tudo é gerado aqui).
//   core_tests                 roda os testes
//   core_tests --pe <arquivo>  também confere a leitura da tabela de importação de um .exe real
//   core_tests --dump-yaml     imprime a configuração padrão enviada ao RPCS3
#include "../core/diagnostics.hpp"
#include "../core/game.hpp"
#include "../core/psf.hpp"
#include "../core/runtime.hpp"
#include "../core/settings.hpp"
#include "../core/sha256.hpp"

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <iostream>

using namespace gow3;

static int failures = 0, checks = 0;

#define CHECK(cond)                                                                       \
	do {                                                                                  \
		checks++;                                                                         \
		if (!(cond)) {                                                                    \
			failures++;                                                                   \
			std::fprintf(stderr, "FALHOU %s:%d: %s\n", __FILE__, __LINE__, #cond);        \
		}                                                                                 \
	} while (0)

#define CHECK_EQ(a, b)                                                                    \
	do {                                                                                  \
		checks++;                                                                         \
		const auto va = (a);                                                              \
		const auto vb = (b);                                                              \
		if (!(va == vb)) {                                                                \
			failures++;                                                                   \
			std::cerr << "FALHOU " << __FILE__ << ":" << __LINE__ << ": " #a " == " #b    \
			          << "\n   obtido:   " << va << "\n   esperado: " << vb << "\n";      \
		}                                                                                 \
	} while (0)

struct TempDir {
	fs::path path;
	TempDir()
	{
		path = fs::temp_directory_path() / ("gow3_test_" + std::to_string(std::rand()) + std::to_string(checks));
		fs::remove_all(path);
		fs::create_directories(path);
	}
	~TempDir()
	{
		std::error_code ec;
		fs::remove_all(path, ec);
	}
};

static fs::path make_game(const fs::path& root, const std::string& serial = "BCUS98111",
                          const std::string& eboot = std::string("SCE\0", 4) + std::string(60, '\0'), bool disc = true)
{
	const fs::path game = disc ? root / "PS3_GAME" : root;
	fs::create_directories(game / "USRDIR");
	write_file(game / "PARAM.SFO", psf::build({{"TITLE_ID", serial}, {"TITLE", "GOD OF WAR® III"}, {"CATEGORY", "DG"},
	                                           {"APP_VER", "01.00"}, {"PS3_SYSTEM_VER", "03.1500"}, {"ATTRIBUTE", 0u}}));
	if (!eboot.empty())
		write_file(game / "USRDIR" / "EBOOT.BIN", eboot);
	write_file(game / "USRDIR" / "data.psarc", "conteudo-falso");
	if (disc)
		write_file(root / "PS3_DISC.SFB", ".SFB");
	return root;
}

static void test_sha256()
{
	CHECK_EQ(Sha256::hex(""), std::string("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"));
	CHECK_EQ(Sha256::hex("abc"), std::string("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"));
	CHECK_EQ(Sha256::hex(std::string(1000, 'a')), std::string("41edece42d63e8d9bf515a9ba6932e1c20cbc9f5a5d134645adb5db1b9737ea3"));
}

static void test_psf()
{
	const std::string data = psf::build({{"TITLE_ID", "BCES00510"}, {"ATTRIBUTE", 32u}, {"TITLE", "GOD OF WAR® III"}});
	const auto map = psf::parse(data);
	CHECK(map.has_value());
	CHECK_EQ(psf::get_string(*map, "TITLE_ID"), std::string("BCES00510"));
	CHECK_EQ(psf::get_string(*map, "TITLE"), std::string("GOD OF WAR® III"));
	CHECK_EQ(psf::get_string(*map, "ATTRIBUTE"), std::string("32"));
	CHECK(!psf::parse("not a sfo file at all").has_value());
	CHECK(!psf::parse(data.substr(0, 30)).has_value());
}

static void test_game()
{
	TempDir tmp;
	const fs::path disc = make_game(tmp.path / "God of War III");
	GameInfo info = inspect_game(disc);
	CHECK(info.ok());
	CHECK_EQ(info.serial, std::string("BCUS98111"));
	CHECK_EQ(info.region, std::string("América do Norte"));
	CHECK_EQ(info.required_firmware, std::string("3.15"));
	CHECK_EQ(info.eboot_kind, std::string("SELF (original do disco)"));
	CHECK(info.boot_path == disc);

	CHECK(inspect_game(disc / "PS3_GAME").ok());
	CHECK(!inspect_game(make_game(tmp.path / "outro", "BLUS30001")).ok());
	CHECK(!inspect_game(make_game(tmp.path / "sem_eboot", "BCES00510", "")).ok());
	CHECK(!inspect_game(make_game(tmp.path / "corrompido", "BCES00510", "garbage!")).ok());
	CHECK(!inspect_game(tmp.path / "nao_existe").ok());

	write_file(disc / "PS3_GAME" / "USRDIR" / "vazio.psarc", "");
	const GameInfo with_empty = inspect_game(disc);
	bool warned = false;
	for (const auto& f : with_empty.findings)
		warned |= f.level == Level::warning && f.message.find("vazio") != std::string::npos;
	CHECK(warned);

	const Manifest saved = build_manifest(disc / "PS3_GAME");
	CHECK(parse_manifest(serialize_manifest(saved)) == saved);
	CHECK(compare_manifest(saved, saved)[0].level == Level::ok);
	write_file(disc / "PS3_GAME" / "USRDIR" / "data.psarc", "alterado");
	CHECK(compare_manifest(saved, build_manifest(disc / "PS3_GAME"))[0].level == Level::error);
}

static void test_settings()
{
	Settings s;
	s.internal_resolution = "1440p";
	s.output_scaling = "fsr";
	s.anisotropic = "16x";
	s.vsync = "full";
	s.frame_limit = "60";
	s.vulkan_adapter = "AMD \"Radeon\" 890M";
	const std::string yaml = rpcs3_yaml(s);
	CHECK(yaml.find("  Resolution Scale: 200\n") != std::string::npos);
	CHECK(yaml.find("  Output Scaling Mode: \"FidelityFX Super Resolution\"\n") != std::string::npos);
	CHECK(yaml.find("  Anisotropic Filter Override: 16\n") != std::string::npos);
	CHECK(yaml.find("  VSync Mode: \"Full\"\n") != std::string::npos);
	CHECK(yaml.find("  Frame limit: \"60\"\n") != std::string::npos);
	CHECK(yaml.find("  Write Color Buffers: true\n") != std::string::npos);
	CHECK(yaml.find("  SPU Block Size: \"Safe\"\n") != std::string::npos);
	CHECK(yaml.find("    Adapter: \"AMD \\\"Radeon\\\" 890M\"\n") != std::string::npos);

	Settings bad;
	bad.internal_resolution = "8K";
	bool threw = false;
	try {
		rpcs3_yaml(bad);
	} catch (const std::invalid_argument&) {
		threw = true;
	}
	CHECK(threw);

	s.game_path = "D:\\Jogos\\God of War III";
	CHECK(parse_settings(serialize_settings(s)) == s);
	const Settings repaired = parse_settings("internal_resolution=8K\nvsync=full\nrcas_sharpening=900\n");
	CHECK_EQ(repaired.internal_resolution, std::string("720p"));
	CHECK_EQ(repaired.vsync, std::string("full"));
	CHECK_EQ(repaired.rcas_sharpening, 50);
}

static void test_runtime()
{
	const Layout layout = Layout::from_app_dir(fs::path("C:") / "GOW3");
	const std::string env = layout.config_dir_env();
	CHECK(env.back() == '/' || env.back() == '\\');
	CHECK(layout.rpcs3_exe() == fs::path("C:") / "GOW3" / "runtime" / "rpcs3" / "rpcs3.exe");
	CHECK(layout.savedata() == fs::path("C:") / "GOW3" / "user" / "rpcs3" / "dev_hdd0" / "home" / "00000001" / "savedata");

	CHECK_EQ(firmware_version_from_text("release:04.9200:\nbuild:1:\n"), std::string("4.92"));
	CHECK_EQ(firmware_version_from_text("release:04.9000:"), std::string("4.90"));
	CHECK_EQ(firmware_version_from_text("release:03.1500:"), std::string("3.15"));
	CHECK_EQ(firmware_version_from_text("release:00.3100:"), std::string("0.31"));
	CHECK_EQ(firmware_version_from_text("lixo"), std::string(""));
	CHECK(compare_versions("4.92", "3.15") > 0);
	CHECK(compare_versions("3.15", "3.15") == 0);
	CHECK(compare_versions("3.15", "3.40") < 0);

	const auto args = boot_arguments("cfg.yml", fs::path("D:") / "GOW3", true);
	CHECK(args.size() == 5 && args[0] == "--no-gui" && args[1] == "--fullscreen" && args[2] == "--config");
	CHECK(boot_arguments("c", "g", false).size() == 4);
	CHECK(install_firmware_arguments("PS3UPDAT.PUP")[1] == "--installfw");

	CHECK_EQ(quote_windows_argument("simples"), std::string("simples"));
	CHECK_EQ(quote_windows_argument("com espaço"), std::string("\"com espaço\""));
	CHECK_EQ(quote_windows_argument("C:\\Jogos\\GOW III\\"), std::string("\"C:\\Jogos\\GOW III\\\\\""));
	CHECK_EQ(quote_windows_argument("a\"b"), std::string("\"a\\\"b\""));
	CHECK_EQ(quote_windows_argument(""), std::string("\"\""));

	TempDir tmp;
	const Layout real = Layout::from_app_dir(tmp.path);
	CHECK(has_error(check_runtime(real, false)));
	write_file(real.rpcs3_exe(), "MZ falso");
	write_file(real.runtime_dir / "Qt6Core.dll", "dll");
	write_file(real.runtime_manifest(), Sha256::hex("MZ falso") + " 8 rpcs3/rpcs3.exe\n" + Sha256::hex("dll") + " 3 rpcs3/Qt6Core.dll\n");
	CHECK(!has_error(check_runtime(real, true)));
	write_file(real.runtime_dir / "Qt6Core.dll", "DLL");
	CHECK(has_error(check_runtime(real, true)));
	fs::remove(real.runtime_dir / "Qt6Core.dll");
	CHECK(has_error(check_runtime(real, false)));
	write_file(real.runtime_dir / "Qt6Core.dll", "dll");
	fs::create_directories(real.portable_dir());
	CHECK(has_error(check_runtime(real, false)));

	write_file(real.dev_flash() / "sys" / "external" / "liblv2.sprx", "x");
	write_file(real.dev_flash() / "vsh" / "etc" / "version.txt", "release:04.9200:\n");
	CHECK(firmware_installed(real));
	CHECK_EQ(installed_firmware(real), std::string("4.92"));
}

static void test_contract_strings()
{
	const auto needles = rpcs3_required_strings();
	auto has = [&](const char* text) { return std::find(needles.begin(), needles.end(), text) != needles.end(); };
	CHECK(has("Write Color Buffers"));
	CHECK(has("FidelityFX Super Resolution"));
	CHECK(has("Async Recompiler with Shader Interpreter"));
	CHECK(has("no-gui"));
	CHECK(has("RPCS3_CONFIG_DIR"));
	CHECK(!has("100"));
	std::string image = "xx Write Color Buffers\0yy";
	for (char c : std::string("RPCS3_CONFIG_DIR")) {
		image.push_back(c);
		image.push_back('\0');
	}
	const auto missing = missing_strings(image, {"Write Color Buffers", "RPCS3_CONFIG_DIR", "Nao Existe"});
	CHECK(missing.size() == 1 && missing[0] == "Nao Existe");

	TempDir tmp;
	fs::create_directories(tmp.path / "rpcs3-v0.0.38-win64" / "qt6");
	write_file(tmp.path / "rpcs3-v0.0.38-win64" / "rpcs3.exe", "MZ");
	CHECK(find_rpcs3_folder(tmp.path) == tmp.path / "rpcs3-v0.0.38-win64");
	CHECK(find_rpcs3_folder(tmp.path / "rpcs3-v0.0.38-win64") == tmp.path / "rpcs3-v0.0.38-win64");
	CHECK(find_rpcs3_folder(tmp.path / "rpcs3-v0.0.38-win64" / "qt6").empty());

	const Layout layout = Layout::from_app_dir(tmp.path / "app");
	write_file(layout.rpcs3_exe(), "MZ falso");
	write_file(layout.runtime_dir / "qt6" / "plugins" / "x.dll", "dll");
	write_file(layout.runtime_manifest(), build_runtime_manifest(layout));
	CHECK(parse_runtime_manifest(build_runtime_manifest(layout)).size() == 2);
	CHECK(!has_error(check_runtime(layout, true)));
}

static void test_diagnostics()
{
	const std::string log = "\xC2\xB7! 0:00:00.000 SYS: RPCS3\n"
	                        "\xC2\xB7W 0:00:01.000 SYS: something\n"
	                        "\xC2\xB7" "E 0:00:01.000 SYS: Booting '/g' with cli argument failed: reason: Firmware is missing\n"
	                        "\xC2\xB7" "F 0:00:02.000 RSX: No compatible GPU devices found\n";
	const LogReport report = analyse_log(log);
	CHECK_EQ(report.errors, size_t{1});
	CHECK_EQ(report.warnings, size_t{1});
	CHECK(report.fatal.size() == 1 && report.fatal[0] == "0:00:02.000 RSX: No compatible GPU devices found");
	CHECK_EQ(report.explanations.size(), size_t{2});
	CHECK_EQ(log_tail("a\nb\nc\n", 2), std::string("b\nc\n"));
	CHECK(is_api_set("api-ms-win-crt-runtime-l1-1-0.dll"));
	CHECK(!is_api_set("Qt6Core.dll"));
	CHECK(is_vc_runtime("MSVCP140.dll") && is_vc_runtime("vcruntime140_1.dll") && !is_vc_runtime("Qt6Core.dll"));
	CHECK(!read_pe_imports("not a pe").valid);
}

static void test_pe(const fs::path& file)
{
	std::string image;
	CHECK(read_file(file, image));
	const PeImports pe = read_pe_imports(image);
	CHECK(pe.valid);
	CHECK(pe.is_x64);
	bool kernel32 = false;
	for (const auto& dll : pe.dlls)
		kernel32 |= to_lower(dll) == "kernel32.dll";
	CHECK(kernel32);
	std::cout << "PE " << path_to_utf8(file) << ": " << pe.dlls.size() << " DLLs importadas:";
	for (const auto& dll : pe.dlls)
		std::cout << " " << dll;
	std::cout << "\n";
}

int main(int argc, char** argv)
{
	for (int i = 1; i < argc; i++)
		if (std::strcmp(argv[i], "--dump-yaml") == 0) {
			std::cout << rpcs3_yaml(Settings{});
			return 0;
		}
	test_sha256();
	test_psf();
	test_game();
	test_settings();
	test_runtime();
	test_diagnostics();
	test_contract_strings();
	for (int i = 1; i + 1 < argc; i++)
		if (std::strcmp(argv[i], "--pe") == 0)
			test_pe(argv[i + 1]);
	std::printf("%d verificações, %d falhas\n", checks, failures);
	return failures ? 1 : 0;
}
