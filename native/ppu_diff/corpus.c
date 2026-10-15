/* SPDX-License-Identifier: GPL-2.0-only
 * Corpus do teste diferencial PPU: código NOSSO, compilado para PowerPC/Cell (gcc -mcpu=cell).
 * Não contém nada do God of War III. Serve para provar que o caminho
 *   código de máquina PowerPC -> lifter (ps3recomp) -> C -> x86-64 (Linux/Windows)
 * reproduz exatamente o que o próprio código PowerPC faz (executado no QEMU).
 *
 * Cobre: aritmética 32/64 bits, desvios, deslocamentos/rotações, divisão, multiplicação alta,
 * laços com pilha, recursão (bl), chamadas entre funções, tabela de salto (switch, via TOC),
 * dados globais (TOC), constantes de ponto flutuante (.rodata), conversões int<->float,
 * bswap, contagem de zeros e escrita em memória global.
 */
#include <stdint.h>

#define NOINLINE __attribute__((noinline))

NOINLINE int arith(int a, int b)
{
	int x = a * 3 + (b << 2) - (a >> 1);
	x ^= (a & b);
	x += (a > b) ? a : b;
	return x * 2 - 7;
}

NOINLINE int branches(int a, int b)
{
	int r = 0;
	if (a < b) r += 1;
	if (a <= b) r += 2;
	if (a == b) r += 4;
	if (a >= b) r += 8;
	if (a > b) r += 16;
	if ((unsigned)a < (unsigned)b) r += 32;
	return r;
}

NOINLINE int rotates(int a, int b)
{
	unsigned u = (unsigned)a;
	int n = b & 31;
	return (int)((u << n) | (u >> ((32 - n) & 31))) + (a >> (n & 15)) - (int)(u >> n);
}

NOINLINE int64_t mul64(int64_t a, int64_t b)
{
	return a * b - (a >> 3) + (b << 5);
}

NOINLINE int64_t mulhigh(int64_t a, int64_t b)
{
	__int128 p = (__int128)a * b;
	uint64_t up = (uint64_t)(((unsigned __int128)(uint64_t)a * (uint64_t)b) >> 64);
	return (int64_t)(p >> 64) ^ (int64_t)up;
}

NOINLINE int64_t divmod(int64_t a, int64_t b)
{
	if (b == 0)
		return -1;
	int64_t q = a / b, r = a % b;
	uint64_t uq = (uint64_t)a / (uint64_t)b;
	return q * 1000003 + r + (int64_t)(uq & 0xff);
}

NOINLINE int clz_bswap(int x)
{
	unsigned u = (unsigned)x | 1u;
	return __builtin_clz(u) + (int)(__builtin_bswap32(u) >> 24) + (int)(__builtin_bswap32(u) & 0xff);
}

NOINLINE int stack_loop(int n)
{
	volatile int buf[32];
	int count = (n & 31) + 1;
	for (int i = 0; i < count; i++)
		buf[i] = i * n + (i ^ n);
	int s = 0;
	for (int i = count - 1; i >= 0; i--)
		s = s * 31 + buf[i];
	return s;
}

NOINLINE int fib(int n)
{
	return n < 2 ? n : fib(n - 1) + fib(n - 2);
}

NOINLINE int helper_square(int x)
{
	return x * x + 1;
}

NOINLINE int calls(int a, int b)
{
	return helper_square(a) - helper_square(b) + helper_square(a ^ b);
}

/* Muitos casos contíguos: o GCC gera tabela de salto (lida pelo TOC). */
NOINLINE int jump_table(int op, int v)
{
	switch (op) {
	case 0: return v + 11;
	case 1: return v * 7;
	case 2: return v - 300;
	case 3: return v ^ 0x5a5a;
	case 4: return v << 3;
	case 5: return v >> 2;
	case 6: return -v;
	case 7: return v & 0xff0;
	case 8: return v | 0x1001;
	case 9: return v % 97;
	default: return 12345;
	}
}

static const int primes[16] = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53};
static const char text[] = "God of War III / static recompilation";

NOINLINE int table_lookup(int i, int j)
{
	return primes[i & 15] * 100 + primes[j & 15] + text[(i * 7 + j) % (int)(sizeof(text) - 1)];
}

NOINLINE unsigned hash_text(int seed)
{
	unsigned h = 2166136261u ^ (unsigned)seed;
	for (const char* p = text; *p; p++)
		h = (h ^ (unsigned char)*p) * 16777619u;
	return h;
}

int g_counter[4];

NOINLINE int global_rw(int i, int v)
{
	g_counter[i & 3] += v;
	return g_counter[0] - g_counter[1] + g_counter[2] * 2 + g_counter[3];
}

NOINLINE double poly(double x, double y)
{
	return 0.5 * x * x + 1.25 * x - 3.0 + y / 7.0;
}

NOINLINE float fmix(float a, float b)
{
	return a * b + b - a / (b + 2.5f) + a * a;
}

NOINLINE int conv(double d, int i)
{
	float f = (float)i * 0.75f;
	return (int)(d * 3.0) + (int)f + (int)(unsigned)(d < 0 ? -d : d);
}
