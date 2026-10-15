// SPDX-License-Identifier: GPL-2.0-only
#include "platform.hpp"

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <shellapi.h>

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <map>
#include <thread>

#include "../core/runtime.hpp"

namespace gow3::win {

std::wstring widen(std::string_view utf8)
{
	if (utf8.empty())
		return {};
	const int size = MultiByteToWideChar(CP_UTF8, 0, utf8.data(), static_cast<int>(utf8.size()), nullptr, 0);
	std::wstring out(static_cast<size_t>(size), L'\0');
	MultiByteToWideChar(CP_UTF8, 0, utf8.data(), static_cast<int>(utf8.size()), out.data(), size);
	return out;
}

std::string narrow(std::wstring_view wide)
{
	if (wide.empty())
		return {};
	const int size = WideCharToMultiByte(CP_UTF8, 0, wide.data(), static_cast<int>(wide.size()), nullptr, 0, nullptr, nullptr);
	std::string out(static_cast<size_t>(size), '\0');
	WideCharToMultiByte(CP_UTF8, 0, wide.data(), static_cast<int>(wide.size()), out.data(), size, nullptr, nullptr);
	return out;
}

fs::path executable_dir()
{
	std::wstring buffer(MAX_PATH, L'\0');
	while (true) {
		const DWORD size = GetModuleFileNameW(nullptr, buffer.data(), static_cast<DWORD>(buffer.size()));
		if (size < buffer.size()) {
			buffer.resize(size);
			break;
		}
		buffer.resize(buffer.size() * 2);
	}
	return fs::path(buffer).parent_path();
}

fs::path system_dir()
{
	wchar_t buffer[MAX_PATH] = {};
	GetSystemDirectoryW(buffer, MAX_PATH);
	return fs::path(buffer);
}

std::string file_version(const fs::path& file)
{
	DWORD ignored = 0;
	const DWORD size = GetFileVersionInfoSizeW(file.c_str(), &ignored);
	if (!size)
		return {};
	std::vector<unsigned char> data(size);
	if (!GetFileVersionInfoW(file.c_str(), 0, size, data.data()))
		return {};
	VS_FIXEDFILEINFO* info = nullptr;
	UINT length = 0;
	if (!VerQueryValueW(data.data(), L"\\", reinterpret_cast<void**>(&info), &length) || !info)
		return {};
	return std::to_string(HIWORD(info->dwFileVersionMS)) + "." + std::to_string(LOWORD(info->dwFileVersionMS)) + "." +
	       std::to_string(HIWORD(info->dwFileVersionLS)) + "." + std::to_string(LOWORD(info->dwFileVersionLS));
}

bool directory_writable(const fs::path& dir)
{
	std::error_code ec;
	fs::create_directories(dir, ec);
	const fs::path probe = dir / L".gow3_write_test";
	HANDLE file = CreateFileW(probe.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS,
	                          FILE_ATTRIBUTE_TEMPORARY | FILE_FLAG_DELETE_ON_CLOSE, nullptr);
	if (file == INVALID_HANDLE_VALUE)
		return false;
	CloseHandle(file);
	return true;
}

namespace {

std::string last_error_text(DWORD code)
{
	wchar_t* text = nullptr;
	FormatMessageW(FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS, nullptr, code,
	               0, reinterpret_cast<wchar_t*>(&text), 0, nullptr);
	std::string out = text ? trim(narrow(text)) : std::string();
	if (text)
		LocalFree(text);
	return out + " (código " + std::to_string(code) + ")";
}

std::wstring environment_block(const std::vector<std::pair<std::string, std::string>>& extra)
{
	auto less = [](const std::wstring& a, const std::wstring& b) { return _wcsicmp(a.c_str(), b.c_str()) < 0; };
	std::map<std::wstring, std::wstring, decltype(less)> vars(less);
	if (wchar_t* block = GetEnvironmentStringsW()) {
		for (const wchar_t* p = block; *p; p += wcslen(p) + 1) {
			const std::wstring entry(p);
			const auto eq = entry.find(L'=', 1); // variáveis especiais começam com '='
			if (eq != std::wstring::npos)
				vars[entry.substr(0, eq)] = entry.substr(eq + 1);
		}
		FreeEnvironmentStringsW(block);
	}
	for (const auto& [key, value] : extra)
		vars[widen(key)] = widen(value);
	std::wstring out;
	for (const auto& [key, value] : vars) {
		out += key + L"=" + value;
		out.push_back(L'\0');
	}
	out.push_back(L'\0');
	return out;
}

HANDLE create(const fs::path& exe, const std::vector<std::string>& args,
              const std::vector<std::pair<std::string, std::string>>& env, HANDLE output, std::string& error,
              HANDLE job = nullptr)
{
	std::wstring command = widen(windows_command_line(exe, args));
	std::wstring block = environment_block(env);
	const std::wstring cwd = exe.parent_path().wstring();
	STARTUPINFOW startup{};
	startup.cb = sizeof(startup);
	if (output) {
		startup.dwFlags = STARTF_USESTDHANDLES;
		startup.hStdOutput = startup.hStdError = output;
		startup.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
	}
	PROCESS_INFORMATION info{};
	if (!CreateProcessW(exe.c_str(), command.data(), nullptr, nullptr, output != nullptr,
	                    CREATE_UNICODE_ENVIRONMENT | (output ? CREATE_NO_WINDOW : 0) | (job ? CREATE_SUSPENDED : 0),
	                    block.data(), cwd.c_str(), &startup, &info)) {
		error = last_error_text(GetLastError());
		return nullptr;
	}
	if (job) {
		// Todos os processos que ele abrir (ex.: o "rpcs3 --error" que mostra erros fatais) ficam no mesmo grupo.
		AssignProcessToJobObject(job, info.hProcess);
		ResumeThread(info.hThread);
	}
	CloseHandle(info.hThread);
	return info.hProcess;
}

} // namespace

ProcessResult run_elevated(const fs::path& exe, const std::vector<std::string>& args)
{
	ProcessResult result;
	std::string params;
	for (const auto& arg : args)
		params += (params.empty() ? "" : " ") + quote_windows_argument(arg);
	const std::wstring wide_params = widen(params);
	SHELLEXECUTEINFOW info{};
	info.cbSize = sizeof(info);
	info.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NOASYNC;
	info.lpVerb = L"runas";
	info.lpFile = exe.c_str();
	info.lpParameters = wide_params.c_str();
	info.nShow = SW_SHOWNORMAL;
	if (!ShellExecuteExW(&info) || !info.hProcess) {
		result.error = last_error_text(GetLastError());
		return result;
	}
	result.started = true;
	WaitForSingleObject(info.hProcess, INFINITE);
	DWORD code = 0;
	GetExitCodeProcess(info.hProcess, &code);
	result.exit_code = code;
	CloseHandle(info.hProcess);
	return result;
}

void* start_process(const fs::path& exe, const std::vector<std::string>& args,
                    const std::vector<std::pair<std::string, std::string>>& env, std::string& error)
{
	return create(exe, args, env, nullptr, error);
}

unsigned long wait_process(void* handle)
{
	WaitForSingleObject(handle, INFINITE);
	DWORD code = 0;
	GetExitCodeProcess(handle, &code);
	CloseHandle(handle);
	return code;
}

namespace {

struct WindowScan {
	std::vector<DWORD> pids;
	std::string text;
};

BOOL CALLBACK collect_child_text(HWND child, LPARAM param)
{
	wchar_t text[1024] = {};
	if (GetWindowTextW(child, text, 1023) > 0) {
		auto* scan = reinterpret_cast<WindowScan*>(param);
		scan->text += " | " + narrow(text);
	}
	return TRUE;
}

BOOL CALLBACK collect_window_text(HWND window, LPARAM param)
{
	auto* scan = reinterpret_cast<WindowScan*>(param);
	DWORD pid = 0;
	GetWindowThreadProcessId(window, &pid);
	if (!IsWindowVisible(window) || std::find(scan->pids.begin(), scan->pids.end(), pid) == scan->pids.end())
		return TRUE;
	wchar_t title[512] = {};
	GetWindowTextW(window, title, 511);
	scan->text += "\n    janela \"" + narrow(title) + "\"";
	EnumChildWindows(window, collect_child_text, param);
	return TRUE;
}

// Texto das janelas abertas pelos processos do grupo (para explicar um travamento).
std::string job_windows(HANDLE job)
{
	struct {
		JOBOBJECT_BASIC_PROCESS_ID_LIST list;
		ULONG_PTR more[63];
	} ids{};
	WindowScan scan;
	if (QueryInformationJobObject(job, JobObjectBasicProcessIdList, &ids, sizeof(ids), nullptr))
		for (DWORD i = 0; i < ids.list.NumberOfProcessIdsInList; i++)
			scan.pids.push_back(static_cast<DWORD>(ids.list.ProcessIdList[i]));
	EnumWindows(collect_window_text, reinterpret_cast<LPARAM>(&scan));
	return std::to_string(scan.pids.size()) + " processo(s) ainda abertos" +
	       (scan.text.empty() ? std::string(", nenhuma janela visível") : scan.text);
}

} // namespace

ProcessResult run_process(const fs::path& exe, const std::vector<std::string>& args,
                          const std::vector<std::pair<std::string, std::string>>& env, unsigned timeout_ms)
{
	ProcessResult result;
	SECURITY_ATTRIBUTES security{sizeof(security), nullptr, TRUE};
	HANDLE read_end = nullptr, write_end = nullptr;
	if (!CreatePipe(&read_end, &write_end, &security, 0)) {
		result.error = last_error_text(GetLastError());
		return result;
	}
	SetHandleInformation(read_end, HANDLE_FLAG_INHERIT, 0);
	// Grupo de processos: ao fechar, o Windows encerra o RPCS3 e tudo o que ele abriu.
	HANDLE job = CreateJobObjectW(nullptr, nullptr);
	if (job) {
		JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
		limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
		SetInformationJobObject(job, JobObjectExtendedLimitInformation, &limits, sizeof(limits));
	}
	HANDLE process = create(exe, args, env, write_end, result.error, job);
	CloseHandle(write_end);
	if (!process) {
		CloseHandle(read_end);
		if (job)
			CloseHandle(job);
		return result;
	}
	result.started = true;
	std::thread reader([&] {
		char buffer[4096];
		DWORD got = 0;
		while (ReadFile(read_end, buffer, sizeof(buffer), &got, nullptr) && got)
			result.output.append(buffer, got);
	});
	if (WaitForSingleObject(process, timeout_ms ? timeout_ms : INFINITE) == WAIT_TIMEOUT) {
		result.timed_out = true;
		if (job)
			result.error = job_windows(job);
		TerminateProcess(process, 1);
		WaitForSingleObject(process, 5000);
	}
	DWORD code = 0;
	GetExitCodeProcess(process, &code);
	result.exit_code = code;
	CloseHandle(process);
	if (job) {
		TerminateJobObject(job, 1); // processos que sobraram seguram o pipe aberto
		CloseHandle(job);
	}
	reader.join();
	CloseHandle(read_end);
	return result;
}

void open_folder(const fs::path& dir)
{
	std::error_code ec;
	fs::create_directories(dir, ec);
	ShellExecuteW(nullptr, L"open", dir.c_str(), nullptr, nullptr, SW_SHOWNORMAL);
}

// ---------------- informações do sistema ----------------

namespace {

// Somente as partes da API do Vulkan usadas aqui, com o layout da especificação.
using VkResult = int;
using VkInstance = struct VkInstance_T*;
using VkPhysicalDevice = struct VkPhysicalDevice_T*;
using PFN_vkVoidFunction = void (*)();
using PFN_vkGetInstanceProcAddr = PFN_vkVoidFunction (*)(VkInstance, const char*);

struct VkApplicationInfo {
	int sType;
	const void* pNext;
	const char* pApplicationName;
	std::uint32_t applicationVersion;
	const char* pEngineName;
	std::uint32_t engineVersion;
	std::uint32_t apiVersion;
};

struct VkInstanceCreateInfo {
	int sType;
	const void* pNext;
	std::uint32_t flags;
	const VkApplicationInfo* pApplicationInfo;
	std::uint32_t enabledLayerCount;
	const char* const* ppEnabledLayerNames;
	std::uint32_t enabledExtensionCount;
	const char* const* ppEnabledExtensionNames;
};

using PFN_vkCreateInstance = VkResult (*)(const VkInstanceCreateInfo*, const void*, VkInstance*);
using PFN_vkDestroyInstance = void (*)(VkInstance, const void*);
using PFN_vkEnumeratePhysicalDevices = VkResult (*)(VkInstance, std::uint32_t*, VkPhysicalDevice*);
using PFN_vkGetPhysicalDeviceProperties = void (*)(VkPhysicalDevice, void*);
using PFN_vkGetPhysicalDeviceMemoryProperties = void (*)(VkPhysicalDevice, void*);

void query_vulkan(SystemInfo& info)
{
	HMODULE loader = LoadLibraryW(L"vulkan-1.dll");
	if (!loader) {
		info.vulkan_error = "vulkan-1.dll não encontrada (o driver de vídeo instala esse arquivo)";
		return;
	}
	info.vulkan_loader = true;
	auto get_proc = reinterpret_cast<PFN_vkGetInstanceProcAddr>(reinterpret_cast<void*>(GetProcAddress(loader, "vkGetInstanceProcAddr")));
	auto create_instance = get_proc ? reinterpret_cast<PFN_vkCreateInstance>(get_proc(nullptr, "vkCreateInstance")) : nullptr;
	if (!create_instance) {
		info.vulkan_error = "vulkan-1.dll inválida";
		FreeLibrary(loader);
		return;
	}
	VkApplicationInfo app{0, nullptr, "GOW3 PS3 PC", 1, "GOW3 PS3 PC", 1, (1u << 22) | (1u << 12)}; // Vulkan 1.1
	VkInstanceCreateInfo create{1, nullptr, 0, &app, 0, nullptr, 0, nullptr};
	VkInstance instance = nullptr;
	const VkResult created = create_instance(&create, nullptr, &instance);
	if (created != 0 || !instance) {
		info.vulkan_error = "o driver recusou criar uma instância Vulkan (erro " + std::to_string(created) + ")";
		FreeLibrary(loader);
		return;
	}
	auto destroy = reinterpret_cast<PFN_vkDestroyInstance>(get_proc(instance, "vkDestroyInstance"));
	auto enumerate = reinterpret_cast<PFN_vkEnumeratePhysicalDevices>(get_proc(instance, "vkEnumeratePhysicalDevices"));
	auto properties = reinterpret_cast<PFN_vkGetPhysicalDeviceProperties>(get_proc(instance, "vkGetPhysicalDeviceProperties"));
	auto memory = reinterpret_cast<PFN_vkGetPhysicalDeviceMemoryProperties>(
		get_proc(instance, "vkGetPhysicalDeviceMemoryProperties"));
	std::uint32_t count = 0;
	if (enumerate && properties && enumerate(instance, &count, nullptr) == 0 && count) {
		std::vector<VkPhysicalDevice> devices(count);
		enumerate(instance, &count, devices.data());
		for (auto device : devices) {
			// VkPhysicalDeviceProperties: apiVersion@0, deviceType@16, deviceName[256]@20 (estrutura < 1 KB).
			alignas(8) unsigned char props[2048] = {};
			properties(device, props);
			GpuInfo gpu;
			std::uint32_t api = 0, type = 0;
			std::memcpy(&api, props, 4);
			std::memcpy(&type, props + 16, 4);
			gpu.name = std::string(reinterpret_cast<const char*>(props + 20), strnlen(reinterpret_cast<const char*>(props + 20), 256));
			gpu.api_version = std::to_string(api >> 22) + "." + std::to_string((api >> 12) & 0x3ff) + "." + std::to_string(api & 0xfff);
			static const char* types[] = {"outro", "integrada", "dedicada", "virtual", "CPU (software)"};
			gpu.type = type < 5 ? types[type] : "?";
			if (memory) {
				// VkPhysicalDeviceMemoryProperties: heapCount@260, heaps[16]@264 (size u64, flags u32, 16 bytes).
				alignas(8) unsigned char mem[1024] = {};
				memory(device, mem);
				std::uint32_t heaps = 0;
				std::memcpy(&heaps, mem + 260, 4);
				for (std::uint32_t i = 0; i < heaps && i < 16; i++) {
					std::uint64_t size = 0;
					std::uint32_t flags = 0;
					std::memcpy(&size, mem + 264 + i * 16, 8);
					std::memcpy(&flags, mem + 264 + i * 16 + 8, 4);
					if (flags & 1) // VK_MEMORY_HEAP_DEVICE_LOCAL_BIT
						gpu.vram_bytes += size;
				}
			}
			info.gpus.push_back(gpu);
		}
	}
	if (destroy)
		destroy(instance, nullptr);
	FreeLibrary(loader);
}

} // namespace

SystemInfo collect_system_info()
{
	SystemInfo info;
	SYSTEM_INFO system{};
	GetNativeSystemInfo(&system);
	info.threads = system.dwNumberOfProcessors;
	info.avx2 = IsProcessorFeaturePresent(40) != 0;   // PF_AVX2_INSTRUCTIONS_AVAILABLE
	info.avx512 = IsProcessorFeaturePresent(41) != 0; // PF_AVX512F_INSTRUCTIONS_AVAILABLE
	MEMORYSTATUSEX memory{};
	memory.dwLength = sizeof(memory);
	if (GlobalMemoryStatusEx(&memory))
		info.ram_gb = static_cast<double>(memory.ullTotalPhys) / (1024.0 * 1024 * 1024);

	HKEY key;
	if (RegOpenKeyExW(HKEY_LOCAL_MACHINE, L"HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0", 0, KEY_READ, &key) == ERROR_SUCCESS) {
		wchar_t name[256] = {};
		DWORD size = sizeof(name) - sizeof(wchar_t);
		if (RegQueryValueExW(key, L"ProcessorNameString", nullptr, nullptr, reinterpret_cast<BYTE*>(name), &size) == ERROR_SUCCESS)
			info.cpu_name = trim(narrow(name));
		RegCloseKey(key);
	}
	// RtlGetVersion informa a versão real, sem a "mentira" de compatibilidade do GetVersionEx.
	using RtlGetVersionFn = LONG(WINAPI*)(OSVERSIONINFOW*);
	if (auto rtl = reinterpret_cast<RtlGetVersionFn>(reinterpret_cast<void*>(GetProcAddress(GetModuleHandleW(L"ntdll.dll"), "RtlGetVersion")))) {
		OSVERSIONINFOW version{};
		version.dwOSVersionInfoSize = sizeof(version);
		if (rtl(&version) == 0) {
			info.os_build = version.dwBuildNumber;
			info.os = version.dwMajorVersion == 10 ? (version.dwBuildNumber >= 22000 ? "Windows 11" : "Windows 10")
			                                       : "Windows " + std::to_string(version.dwMajorVersion) + "." +
			                                             std::to_string(version.dwMinorVersion);
		}
	}
	query_vulkan(info);
	return info;
}

Findings evaluate_system(const SystemInfo& info)
{
	// Limites do launcher para avisar o usuário; não são requisitos oficiais do RPCS3.
	Findings out;
	char text[160];
	out.push_back({info.os_build >= 10240 ? Level::ok : Level::error,
	               info.os + " (build " + std::to_string(info.os_build) + ")" +
	                   (info.os_build >= 10240 ? "" : ": o RPCS3 exige Windows 10 ou mais novo")});
	out.push_back({info.threads >= 4 ? Level::ok : Level::warning,
	               (info.cpu_name.empty() ? std::string("CPU") : info.cpu_name) + ", " + std::to_string(info.threads) +
	                   " threads" + (info.threads >= 4 ? "" : ": God of War III usa muito os SPUs e deve ficar lento")});
	if (!info.avx2)
		out.push_back({Level::warning, "CPU sem AVX2: a tradução de código fica mais lenta."});
	if (info.avx512)
		out.push_back({Level::ok, "CPU com AVX-512 (o RPCS3 usa essas instruções nos SPUs)."});
	std::snprintf(text, sizeof(text), "%.1f GB de RAM", info.ram_gb);
	out.push_back({info.ram_gb >= 7.5 ? Level::ok : Level::warning,
	               std::string(text) + (info.ram_gb >= 7.5 ? "" : ": abaixo de 8 GB o jogo pode travar")});
	if (!info.vulkan_error.empty())
		out.push_back({Level::error, "Vulkan: " + info.vulkan_error + ". Instale ou atualize o driver de vídeo."});
	else if (info.gpus.empty())
		out.push_back({Level::error, "Nenhuma placa com Vulkan encontrada. Atualize o driver de vídeo."});
	for (const auto& gpu : info.gpus) {
		std::snprintf(text, sizeof(text), "%.1f GB", static_cast<double>(gpu.vram_bytes) / (1024.0 * 1024 * 1024));
		out.push_back({gpu.type == "CPU (software)" ? Level::warning : Level::ok,
		               "Vulkan " + gpu.api_version + ": " + gpu.name + " (" + gpu.type + ", " + text + " de memória de vídeo)"});
	}
	return out;
}

DllLocation resolve_dll(const std::string& dll, const fs::path& exe_dir)
{
	std::error_code ec;
	const fs::path name = widen(dll);
	if (fs::is_regular_file(exe_dir / name, ec))
		return {DllSource::local, exe_dir / name};
	wchar_t system_dir[MAX_PATH] = {}, windows_dir[MAX_PATH] = {};
	GetSystemDirectoryW(system_dir, MAX_PATH);
	GetWindowsDirectoryW(windows_dir, MAX_PATH);
	for (const fs::path& dir : {fs::path(system_dir), fs::path(windows_dir)})
		if (fs::is_regular_file(dir / name, ec))
			return {DllSource::system, dir / name};
	wchar_t found[MAX_PATH] = {};
	if (SearchPathW(nullptr, name.c_str(), nullptr, MAX_PATH, found, nullptr))
		return {DllSource::path, fs::path(found)};
	return {};
}

} // namespace gow3::win
