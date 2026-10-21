// SPDX-License-Identifier: GPL-2.0-only
#include "guest_runtime.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <unordered_map>
#include <vector>

namespace {

constexpr uint64_t page_size = 4096;
constexpr uint64_t stack_base = 0x0F000000, stack_size = 0x00100000;

struct Region {
	uint64_t begin, end;
};

std::unordered_map<uint64_t, std::unique_ptr<uint8_t[]>> pages;
std::vector<Region> regions; // onde o convidado pode ler/escrever (segmentos do ELF + pilha)
int failures = 0;

[[noreturn]] void fault(const char* what, uint64_t addr)
{
	std::fprintf(stderr, "ERRO: %s no endereço 0x%llX fora da memória mapeada\n", what, (unsigned long long)addr);
	std::exit(3);
}

uint8_t* byte_at(uint64_t addr, const char* what)
{
	auto it = pages.find(addr / page_size);
	if (it == pages.end()) {
		bool allowed = false;
		for (const auto& r : regions)
			allowed |= addr >= r.begin && addr < r.end;
		if (!allowed)
			fault(what, addr);
		auto page = std::make_unique<uint8_t[]>(page_size);
		std::memset(page.get(), 0, page_size);
		it = pages.emplace(addr / page_size, std::move(page)).first;
	}
	return it->second.get() + addr % page_size;
}

uint64_t read_be(uint64_t addr, int size)
{
	uint64_t v = 0;
	for (int i = 0; i < size; i++)
		v = (v << 8) | *byte_at(addr + i, "leitura");
	return v;
}

void write_be(uint64_t addr, uint64_t v, int size)
{
	for (int i = size - 1; i >= 0; i--) {
		*byte_at(addr + i, "escrita") = static_cast<uint8_t>(v);
		v >>= 8;
	}
}

uint64_t be64(const uint8_t* p)
{
	uint64_t v = 0;
	for (int i = 0; i < 8; i++)
		v = (v << 8) | p[i];
	return v;
}

uint32_t be32(const uint8_t* p) { return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3]; }
uint16_t be16(const uint8_t* p) { return (uint16_t)(p[0] << 8 | p[1]); }

} // namespace

extern "C" {
uint8_t vm_read8(uint64_t a) { return (uint8_t)read_be(a, 1); }
uint16_t vm_read16(uint64_t a) { return (uint16_t)read_be(a, 2); }
uint32_t vm_read32(uint64_t a) { return (uint32_t)read_be(a, 4); }
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
uint64_t ppu_timebase_now() { return 0; }
void lv2_syscall(ppu_context* ctx)
{
	std::fprintf(stderr, "ERRO: syscall inesperada (r11=%llu)\n", (unsigned long long)ctx->gpr[11]);
	std::exit(4);
}
void ps3_hle_call(unsigned nid, ppu_context*)
{
	std::fprintf(stderr, "ERRO: chamada de biblioteca do sistema inesperada (NID 0x%08X)\n", nid);
	std::exit(4);
}
void ps3_indirect_call(ppu_context* ctx)
{
	for (uint64_t i = 0; i < function_table_count; i++)
		if (function_table[i].addr == ctx->ctr) {
			function_table[i].func(ctx);
			return;
		}
	std::fprintf(stderr, "ERRO: chamada indireta para 0x%llX, que não foi recompilada\n", (unsigned long long)ctx->ctr);
	std::exit(5);
}
PPU_THREAD_LOCAL void (*g_trampoline_fn)(void*) = nullptr;
// Símbolos que o código gerado pelo ps3recomp >= v0.16 referencia (atalho de leitura em linha,
// desligado aqui; acesso plano por vm_base não é usado pelo corpus).
uint8_t* vm_base = nullptr;
int vm_inline_ok = 0;
uint32_t ppu_vm_size = 0;
uint32_t ppu_hle_inject_base = 0;
void ps3_indirect_call_to(ppu_context* ctx, uint32_t target)
{
	// destino explícito (b<cond>lrl): o CTR do convidado não muda
	for (uint64_t i = 0; i < function_table_count; i++)
		if (function_table[i].addr == target) {
			function_table[i].func(ctx);
			return;
		}
	std::fprintf(stderr, "ERRO: chamada indireta para 0x%X, que não foi recompilada\n", target);
	std::exit(5);
}
}

bool guest_load_elf(const char* path)
{
	FILE* f = std::fopen(path, "rb");
	if (!f) {
		std::fprintf(stderr, "não foi possível abrir %s\n", path);
		return false;
	}
	std::vector<uint8_t> d;
	uint8_t chunk[65536];
	size_t got;
	while ((got = std::fread(chunk, 1, sizeof(chunk), f)) > 0)
		d.insert(d.end(), chunk, chunk + got);
	std::fclose(f);
	if (d.size() < 64 || std::memcmp(d.data(), "\x7f" "ELF\x02\x02", 6) != 0) {
		std::fprintf(stderr, "%s não é ELF64 big-endian\n", path);
		return false;
	}
	const uint64_t phoff = be64(&d[0x20]);
	const uint16_t phentsize = be16(&d[0x36]), phnum = be16(&d[0x38]);
	for (uint16_t i = 0; i < phnum; i++) {
		const uint8_t* ph = &d[phoff + (uint64_t)i * phentsize];
		if (be32(ph) != 1) // PT_LOAD
			continue;
		const uint64_t offset = be64(ph + 8), vaddr = be64(ph + 16), filesz = be64(ph + 32), memsz = be64(ph + 40);
		regions.push_back({vaddr, vaddr + memsz});
		for (uint64_t k = 0; k < filesz; k++)
			*byte_at(vaddr + k, "carga") = d[offset + k];
	}
	regions.push_back({stack_base, stack_base + stack_size});
	return true;
}

void guest_prepare(ppu_context* ctx, uint64_t toc)
{
	std::memset(ctx, 0, sizeof(*ctx));
	ctx->gpr[1] = stack_base + stack_size - 0x1000; // pilha alinhada, com espaço para o "back chain"
	ctx->gpr[2] = toc;
	ctx->gpr[13] = 0;
	ctx->lr = 0;
}

void guest_call(ppu_context* ctx, void (*fn)(ppu_context*))
{
	const uint64_t sp = ctx->gpr[1];
	fn(ctx);
	// O lifter divide funções longas e encadeia os pedaços por g_trampoline_fn.
	while (g_trampoline_fn) {
		auto next = g_trampoline_fn;
		g_trampoline_fn = nullptr;
		next(ctx);
	}
	if (ctx->gpr[1] != sp) {
		std::fprintf(stderr, "ERRO: ponteiro de pilha não foi restaurado (0x%llX != 0x%llX)\n",
		             (unsigned long long)ctx->gpr[1], (unsigned long long)sp);
		failures++;
	}
}

int guest_failures() { return failures; }
