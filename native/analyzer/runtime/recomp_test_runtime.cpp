// SPDX-License-Identifier: GPL-2.0-only
// GOW3_Native_RecompTest: executa funções PPU recompiladas (ps3recomp -> C++ -> x86-64) a partir de
// estados iniciais lidos de um arquivo e grava o estado final de cada caso.
//
// Uso: GOW3_Native_RecompTest <EBOOT.ELF> <casos.txt> <resultados.txt> [primeira_linha]
//
// Runtime mínimo e explícito (não é um emulador): memória do convidado big-endian por páginas
// (segmentos PT_LOAD do ELF, pilha e área de rascunho), despacho de chamadas indiretas pela tabela
// de funções recompiladas e falhas de acesso convertidas em resultado ("fault") em vez de travar.
// Syscalls e chamadas de biblioteca do sistema não são atendidas: viram falha, porque as funções
// escolhidas para este teste não as usam.

#include "ppu_recomp.h"

#include <algorithm>
#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

extern "C" PPU_THREAD_LOCAL void (*g_trampoline_fn)(void*);

namespace {

// Mesmos valores de gow3_analyzer/state.py
constexpr uint64_t kPage = 4096;
constexpr uint64_t kScratchBase = 0x30000000, kScratchSize = 0x40000;
constexpr uint64_t kStackBase = 0x0FF00000, kStackSize = 0x00100000;
constexpr uint64_t kMask = ~0ULL;

struct GuestFault {
	const char* kind;
	uint64_t addr;
};

struct Region {
	uint64_t begin, end;
};

using Page = std::unique_ptr<uint8_t[]>;
std::unordered_map<uint64_t, Page> pristine; // imagem do ELF, nunca alterada
std::unordered_map<uint64_t, Page> overlay;  // páginas escritas no caso atual
std::vector<Region> regions;
std::vector<uint64_t> written;

bool mapped(uint64_t addr)
{
	for (const auto& r : regions)
		if (addr >= r.begin && addr < r.end)
			return true;
	return false;
}

uint8_t read_byte(uint64_t addr)
{
	const uint64_t pn = addr / kPage;
	if (auto it = overlay.find(pn); it != overlay.end())
		return it->second[addr % kPage];
	if (auto it = pristine.find(pn); it != pristine.end())
		return it->second[addr % kPage];
	if (!mapped(addr))
		throw GuestFault{"read", addr};
	return 0;
}

uint8_t* write_slot(uint64_t addr)
{
	const uint64_t pn = addr / kPage;
	auto it = overlay.find(pn);
	if (it == overlay.end()) {
		if (!mapped(addr))
			throw GuestFault{"write", addr};
		Page p(new uint8_t[kPage]);
		if (auto src = pristine.find(pn); src != pristine.end())
			std::memcpy(p.get(), src->second.get(), kPage);
		else
			std::memset(p.get(), 0, kPage);
		it = overlay.emplace(pn, std::move(p)).first;
	}
	return &it->second[addr % kPage];
}

uint64_t read_be(uint64_t addr, int size)
{
	uint64_t v = 0;
	for (int i = 0; i < size; i++)
		v = (v << 8) | read_byte(addr + i);
	return v;
}

void write_be(uint64_t addr, uint64_t v, int size)
{
	// Verifica o intervalo inteiro antes de escrever (uma escrita que falha não muda nada).
	for (int i = 0; i < size; i++)
		write_slot(addr + i);
	for (int i = size - 1; i >= 0; i--) {
		*write_slot(addr + i) = static_cast<uint8_t>(v);
		written.push_back(addr + i);
		v >>= 8;
	}
}

// xorshift64* igual ao de state.py
struct XorShift {
	uint64_t s;
	explicit XorShift(uint64_t seed) : s((seed ^ 0x9E3779B97F4A7C15ULL) ? (seed ^ 0x9E3779B97F4A7C15ULL) : 1) {}
	uint64_t next()
	{
		uint64_t x = s;
		x ^= x >> 12;
		x ^= x << 25;
		x ^= x >> 27;
		s = x;
		return x * 0x2545F4914F6CDD1DULL;
	}
};

void reset_memory(uint64_t seed)
{
	overlay.clear();
	written.clear();
	XorShift rng(seed ^ 0x5C3A7C4ULL);
	for (uint64_t off = 0; off < kScratchSize; off += 8) {
		uint64_t v = rng.next();
		for (int i = 7; i >= 0; i--) {
			*write_slot(kScratchBase + off + i) = static_cast<uint8_t>(v);
			v >>= 8;
		}
	}
}

uint64_t be(const uint8_t* p, int n)
{
	uint64_t v = 0;
	for (int i = 0; i < n; i++)
		v = (v << 8) | p[i];
	return v;
}

void add_region(uint64_t begin, uint64_t end)
{
	// Granularidade de página, como o mapeamento da CPU de referência.
	regions.push_back({begin & ~(kPage - 1), (end + kPage - 1) & ~(kPage - 1)});
}

bool load_elf(const char* path)
{
	FILE* f = std::fopen(path, "rb");
	if (!f) {
		std::fprintf(stderr, "não foi possível abrir %s\n", path);
		return false;
	}
	std::vector<uint8_t> d;
	uint8_t chunk[1 << 16];
	size_t got;
	while ((got = std::fread(chunk, 1, sizeof(chunk), f)) > 0)
		d.insert(d.end(), chunk, chunk + got);
	std::fclose(f);
	if (d.size() < 64 || std::memcmp(d.data(), "\x7f" "ELF\x02\x02", 6) != 0) {
		std::fprintf(stderr, "%s não é um ELF64 big-endian\n", path);
		return false;
	}
	const uint64_t phoff = be(&d[0x20], 8);
	const uint64_t phentsize = be(&d[0x36], 2), phnum = be(&d[0x38], 2);
	for (uint64_t i = 0; i < phnum; i++) {
		const uint8_t* ph = &d[phoff + i * phentsize];
		if (be(ph, 4) != 1)
			continue;
		const uint64_t offset = be(ph + 8, 8), vaddr = be(ph + 16, 8), filesz = be(ph + 32, 8), memsz = be(ph + 40, 8);
		add_region(vaddr, vaddr + memsz);
		for (uint64_t k = 0; k < filesz && offset + k < d.size(); k++) {
			const uint64_t a = vaddr + k, pn = a / kPage;
			auto it = pristine.find(pn);
			if (it == pristine.end()) {
				Page p(new uint8_t[kPage]);
				std::memset(p.get(), 0, kPage);
				it = pristine.emplace(pn, std::move(p)).first;
			}
			it->second[a % kPage] = d[offset + k];
		}
	}
	add_region(kStackBase, kStackBase + kStackSize);
	add_region(kScratchBase, kScratchBase + kScratchSize);
	return true;
}

struct FuncIndex {
	std::unordered_map<uint64_t, void (*)(ppu_context*)> by_addr;
	FuncIndex()
	{
		for (uint64_t i = 0; i < function_table_count; i++)
			by_addr[function_table[i].addr] = function_table[i].func;
	}
};

const FuncIndex& funcs()
{
	static FuncIndex index;
	return index;
}

uint64_t fnv1a()
{
	uint64_t h = 0xCBF29CE484222325ULL;
	for (uint64_t a : written) {
		uint8_t bytes[9];
		for (int i = 0; i < 8; i++)
			bytes[i] = static_cast<uint8_t>(a >> (56 - 8 * i));
		bytes[8] = read_byte(a);
		for (uint8_t b : bytes) {
			h ^= b;
			h *= 0x100000001B3ULL;
		}
	}
	return h;
}

std::vector<std::string> split(const std::string& s)
{
	std::vector<std::string> out;
	size_t i = 0;
	while (i < s.size()) {
		while (i < s.size() && (s[i] == ' ' || s[i] == '\r' || s[i] == '\n'))
			i++;
		size_t j = i;
		while (j < s.size() && s[j] != ' ' && s[j] != '\r' && s[j] != '\n')
			j++;
		if (j > i)
			out.push_back(s.substr(i, j - i));
		i = j;
	}
	return out;
}

uint64_t hex(const std::string& s) { return std::strtoull(s.c_str(), nullptr, 16); }

// "run <addr> case <id> seed <s> gpr <32> fpr <32> cr <v> xer <v> ctr <v> lr <v>"
std::string run_line(const std::vector<std::string>& t)
{
	if (t.size() < 80 || t[0] != "run" || t[2] != "case" || t[6] != "gpr" || t[39] != "fpr")
		return "erro linha-invalida";
	const uint64_t addr = hex(t[1]);
	const std::string id = t[3];
	const uint64_t seed = hex(t[5]);
	char head[64];
	std::snprintf(head, sizeof head, "func %08" PRIX64 " case %s ", addr, id.c_str());
	auto it = funcs().by_addr.find(addr);
	if (it == funcs().by_addr.end())
		return std::string(head) + "missing";

	ppu_context ctx;
	std::memset(&ctx, 0, sizeof ctx);
	for (int i = 0; i < 32; i++) {
		ctx.gpr[i] = hex(t[7 + i]);
		uint64_t bits = hex(t[40 + i]);
		std::memcpy(&ctx.fpr[i], &bits, 8);
	}
	ctx.cr = static_cast<uint32_t>(hex(t[73]));
	ctx.xer = static_cast<uint32_t>(hex(t[75]));
	ctx.ctr = hex(t[77]);
	ctx.lr = hex(t[79]);
	reset_memory(seed);
	char buf[4096];
	try {
		it->second(&ctx);
		while (g_trampoline_fn) { // o lifter divide funções longas em pedaços encadeados
			auto next = g_trampoline_fn;
			g_trampoline_fn = nullptr;
			next(&ctx);
		}
	} catch (const GuestFault& f) {
		g_trampoline_fn = nullptr;
		std::snprintf(buf, sizeof buf, "fault %s %" PRIx64, f.kind, f.addr);
		return std::string(head) + buf;
	}
	std::sort(written.begin(), written.end());
	written.erase(std::unique(written.begin(), written.end()), written.end());
	std::string out = std::string(head) + "ok gpr";
	for (int i = 0; i < 32; i++) {
		std::snprintf(buf, sizeof buf, " %" PRIx64, ctx.gpr[i]);
		out += buf;
	}
	out += " fpr";
	for (int i = 0; i < 32; i++) {
		uint64_t bits;
		std::memcpy(&bits, &ctx.fpr[i], 8);
		std::snprintf(buf, sizeof buf, " %" PRIx64, bits);
		out += buf;
	}
	std::snprintf(buf, sizeof buf, " cr %x xer %x ctr %" PRIx64 " lr %" PRIx64 " mem %zu %" PRIx64 " first %" PRIx64,
	              ctx.cr, ctx.xer & 0xE0000000u, ctx.ctr, ctx.lr, written.size(), fnv1a(),
	              written.empty() ? 0 : written.front());
	return out + buf;
}

} // namespace

extern "C" {
uint8_t* vm_base = nullptr; // acesso plano não é usado pelas funções testadas (elas são filtradas)
uint8_t vm_read8(uint64_t a) { return static_cast<uint8_t>(read_be(a, 1)); }
uint16_t vm_read16(uint64_t a) { return static_cast<uint16_t>(read_be(a, 2)); }
uint32_t vm_read32(uint64_t a) { return static_cast<uint32_t>(read_be(a, 4)); }
uint64_t vm_read64(uint64_t a) { return read_be(a, 8); }
void vm_write8(uint64_t a, uint8_t v) { write_be(a, v, 1); }
void vm_write16(uint64_t a, uint16_t v) { write_be(a, v, 2); }
void vm_write32(uint64_t a, uint32_t v) { write_be(a, v, 4); }
void vm_write64(uint64_t a, uint64_t v) { write_be(a, v, 8); }
int ppu_stwcx32(uint64_t a, uint32_t expected, uint32_t v)
{
	if (vm_read32(a) != expected)
		return 0;
	vm_write32(a, v);
	return 1;
}
int ppu_stdcx64(uint64_t a, uint64_t expected, uint64_t v)
{
	if (vm_read64(a) != expected)
		return 0;
	vm_write64(a, v);
	return 1;
}
uint64_t ppu_timebase_now() { throw GuestFault{"cpu", 0}; }
void lv2_syscall(ppu_context* ctx) { throw GuestFault{"cpu", ctx->gpr[11]}; }
void ps3_hle_call(unsigned nid, ppu_context*) { throw GuestFault{"cpu", nid}; }
void ps3_indirect_call(ppu_context* ctx)
{
	auto it = funcs().by_addr.find(ctx->ctr);
	if (it == funcs().by_addr.end())
		throw GuestFault{"fetch", ctx->ctr};
	it->second(ctx);
}
PPU_THREAD_LOCAL void (*g_trampoline_fn)(void*) = nullptr;
}

int main(int argc, char** argv)
{
	if (argc < 4) {
		std::fprintf(stderr, "uso: %s <EBOOT.ELF> <casos.txt> <resultados.txt> [primeira_linha]\n", argv[0]);
		return 2;
	}
	if (!load_elf(argv[1]))
		return 2;
	const long first = argc > 4 ? std::atol(argv[4]) : 0;
	FILE* in = std::fopen(argv[2], "rb");
	FILE* out = std::fopen(argv[3], first > 0 ? "ab" : "wb");
	if (!in || !out) {
		std::fprintf(stderr, "não foi possível abrir os arquivos de casos/resultados\n");
		return 2;
	}
	std::string line;
	long n = 0;
	int c;
	while (true) {
		line.clear();
		while ((c = std::fgetc(in)) != EOF && c != '\n')
			line.push_back(static_cast<char>(c));
		if (line.empty() && c == EOF)
			break;
		if (!line.empty() && n++ >= first) {
			const std::string result = run_line(split(line));
			std::fprintf(out, "%s\n", result.c_str());
			std::fflush(out); // se um caso travar, os anteriores já estão gravados
		}
		if (c == EOF)
			break;
	}
	std::fclose(in);
	std::fclose(out);
	return 0;
}
