/* God of War III: executor nativo das listas EDGE (workloads 8-10 do SPURS) no lugar do gerenciador de jobs Wws
 * traduzido (o policy module pm_wwsjob), uma execução do policy module por vez.
 *
 * GOW3_WWS_EXEC=1 liga (o padrão é desligado); GOW3_WWS_EXEC_WIDS=<máscara hex> (padrão 700); GOW3_WWS_EXEC_STATS=<s>
 * imprime a cada <s> segundos quantas execuções foram nativas, recusadas (e por quê) e as divergências.
 *
 * Cada execução do gerenciador do GOW3 roda UM job da lista (LEIA-ME, "executor Wws próprio"). Esta faz a mesma
 * execução em C: os mesmos comandos MFC e as mesmas leituras e escritas de canal, na mesma ordem (atômicas,
 * coerência, eventos e DMAs saem pelo runtime, iguais), o tratador de interrupção do gerenciador no mesmo ponto
 * (depois de cada lista de sinal), o estado que ele deixa na LS na entrada do job e no fim, e o job chamado direto.
 * O que sai do C é o que as regras conferidas fora do jogo dão (GOW3_trabalho/wws_exec/gera_const.py: LS de entrada
 * e de fim idênticas em todas as execuções estáveis gravadas). Só toma uma execução quando:
 *   - a região do gerenciador na LS (0-0x1700 e o trampolim de interrupção) é o estado estável gravado, fora os
 *     campos que mudam a cada job;
 *   - a próxima entrada da lista é um job (0x00900001) com o cabeçalho de forma conhecida (só o EA da lista de
 *     entradas muda);
 *   - a reserva (PUTLLC) dá certo de primeira.
 * O resto -- lista vazia, entradas de espera/contador (tipos 2, 3), outra configuração, contexto novo -- roda o
 * gerenciador traduzido, que encontra a LS como ele mesmo a deixaria. Uma leitura de canal com valor diferente do
 * esperado antes da reserva também devolve a execução ao traduzido; depois dela é contada como divergência.
 *
 * As constantes do gerenciador ficam em gow3_wws_const.h, gerado das execuções gravadas e LOCAL (dados do jogo);
 * sem ele este arquivo compila vazio e o executor não existe. */
#if defined(__has_include)
#if __has_include("gow3_wws_const.h")
#define G3W_TEM 1
#endif
#endif

#ifdef G3W_TEM
#include "spu_context.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>
#include "gow3_wws_const.h"

extern uint8_t* vm_base;
extern int (*g_spurs_pm_native)(spu_context* ctx, uint32_t wid, uint32_t spu_num, uint32_t spurs_ea, int first);
extern SPU_THREAD_LOCAL volatile unsigned g_spurs_pm_polls;
extern SPU_THREAD_LOCAL volatile unsigned g_spurs_pm_exited;
extern u128 spu_rdch(spu_context* ctx, uint32_t channel);
extern void spu_wrch(spu_context* ctx, uint32_t channel, u128 value);
extern uint32_t spu_rchcnt(spu_context* ctx, uint32_t channel);
extern int spu_run_with_halt(void (*entry)(spu_context*), spu_context* ctx);
typedef void (*g3w_fn)(spu_context*);
extern g3w_fn spu_lifted_lookup(const spu_context* ctx, uint32_t lsa);
extern SPU_THREAD_LOCAL int g_wwstrace_on;
extern SPU_THREAD_LOCAL uint32_t g_spu_stop_pc;   /* spu_channels.c: o desvio para ele volta ao nosso laço */
extern void spu_wwstrace_branch(const spu_context* ctx);

enum { CH_EVSTAT = 0, CH_EVMASK = 1, CH_EVACK = 2, CH_DEC = 8, CH_CMD = 21, CH_TAGUPD = 23, CH_TAGSTAT = 24,
       CH_STALLSTAT = 25, CH_STALLACK = 26, CH_ATOMSTAT = 27 };
enum { JOB_ENTRY = 0xD200, JOB_RET = 0x32B0, LINE_LS = 0x80, ENT_LS = 0xD00, HDR_LS = 0xC00, SIG_LIST = 0x1540,
       MOD_EA = 0x444600, IN_LIST_LS = 0x1EF50, IN_LS = 0x13000 };

/* ---- estatística ---- */
enum { R_FRESH, R_MOLDE, R_ENTRADA, R_CAB, R_RESERVA, R_CANAL, R_N };
static const char* const k_rnome[R_N] = { "contexto novo", "LS fora do molde", "entrada não é job",
                                          "cabeçalho diferente", "reserva falhou", "canal antes da reserva" };
static volatile long s_nat, s_rec[R_N], s_div;
static int s_stats;

static void g3w_stats(void)
{
    static volatile LONG64 s_last;
    const LONG64 now = (LONG64)GetTickCount64() / 1000, l = s_last;
    if (now - l < s_stats || InterlockedCompareExchange64(&s_last, now, l) != l) return;
    if (!l) return;
    fprintf(stderr, "[wws-exec] nativas %ld, divergências %ld; recusadas:", s_nat, s_div);
    for (int i = 0; i < R_N; i++) if (s_rec[i]) fprintf(stderr, " %s %ld,", k_rnome[i], s_rec[i]);
    fprintf(stderr, "%c", 10);
}

/* ---- auxiliares ---- */
static inline uint32_t be32(const uint8_t* p) { return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3]; }
static inline void wbe32(uint8_t* p, uint32_t v) { p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v; }
static inline void wq(uint8_t* p, uint32_t a, uint32_t b, uint32_t c, uint32_t d) { wbe32(p, a); wbe32(p + 4, b); wbe32(p + 8, c); wbe32(p + 12, d); }
static inline u128 U(uint32_t v) { u128 r; memset(&r, 0, sizeof r); r._u32[0] = v; return r; }
static inline uint32_t RD(spu_context* c, uint32_t ch) { return spu_rdch(c, ch)._u32[0]; }
static inline void WR(spu_context* c, uint32_t ch, uint32_t v) { spu_wrch(c, ch, U(v)); }
static inline void dma(spu_context* c, uint32_t cmd, uint32_t lsa, uint32_t ea, uint32_t size, uint32_t tag)
{
    c->mfc_lsa = lsa; c->mfc_eah = 0; c->mfc_eal = ea; c->mfc_size = size; c->mfc_tag = tag;
    WR(c, CH_CMD, cmd);
}

/* espera de tag como o gerenciador a faz (máscara, atualização, leitura); devolve se veio o esperado */
static SPU_THREAD_LOCAL int t_div;
static SPU_THREAD_LOCAL uint32_t t_div_at, t_div_got, t_div_exp;   /* a primeira divergência: passo, lido, esperado */
static SPU_THREAD_LOCAL uint32_t t_step;
static inline void diverge(uint32_t got, uint32_t exp)
{
    if (!t_div) { t_div_at = t_step; t_div_got = got; t_div_exp = exp; }
    t_div = 1;
}
static inline void tagwait(spu_context* c, uint32_t upd, uint32_t expect)
{
    t_step++;
    c->mfc_tag_mask = expect;
    WR(c, CH_TAGUPD, upd);
    const uint32_t v = RD(c, CH_TAGSTAT);
    if (v != expect) diverge(v, expect);
}

/* o tratador de interrupção do gerenciador (0x2310): o evento lido e reconhecido; as listas paradas, cada tag
 * reconhecida da mais alta para a mais baixa; devolve as tags paradas */
static uint32_t irq(spu_context* c)
{
    const uint32_t v = RD(c, CH_EVSTAT);
    WR(c, CH_EVACK, v);
    uint32_t s = 0;
    if (spu_rchcnt(c, CH_STALLSTAT)) {
        s = RD(c, CH_STALLSTAT);
        for (uint32_t t = s; t; ) { const uint32_t b = 31u - (uint32_t)__builtin_clz(t); WR(c, CH_STALLACK, b); t ^= 1u << b; }
    }
    return s;
}

/* os intervalos da região do gerenciador comparados com o molde (o complemento de g3w_var) */
static uint32_t s_fix[64][2]; static int s_nfix;
static void g3w_fix_init(void)
{
    uint8_t var[G3W_FIX_HI / 16] = { 0 };
    for (size_t i = 0; i < sizeof g3w_var / sizeof g3w_var[0]; i++)
        for (uint32_t o = g3w_var[i][0]; o < g3w_var[i][1] && o < G3W_FIX_HI; o += 16) var[o / 16] = 1;
    for (size_t i = 0; i < sizeof g3w_por_ctx / sizeof g3w_por_ctx[0]; i++) var[g3w_por_ctx[i] / 16] = 1;
    for (uint32_t q = 0; q < G3W_FIX_HI / 16; q++) {
        if (var[q]) continue;
        if (s_nfix && s_fix[s_nfix - 1][1] == q * 16) s_fix[s_nfix - 1][1] += 16;
        else if (s_nfix < 64) { s_fix[s_nfix][0] = q * 16; s_fix[s_nfix][1] = q * 16 + 16; s_nfix++; }
    }
}

static int s_debug;
static LONG64 s_debug_desde;   /* GOW3_WWS_EXEC_DEBUG_DESDE=<s>: só conta/mostra recusas depois disso */
static LONG64 s_t0;
/* os quadwords de cada contexto (lista, SPU) que não são do molde (EA da linha de estado, número da lista,
 * máscaras): o gerenciador não os muda numa execução estável; guardados no começo, repostos no fim */
enum { NCTX = sizeof g3w_por_ctx / sizeof g3w_por_ctx[0] };
static SPU_THREAD_LOCAL uint8_t t_ctxq[NCTX][16];
static void g3w_ctx(uint8_t* ls, int restore)
{
    for (int i = 0; i < NCTX; i++) {
        if (restore) memcpy(ls + g3w_por_ctx[i], t_ctxq[i], 16);
        else memcpy(t_ctxq[i], ls + g3w_por_ctx[i], 16);
    }
}
static int g3w_no_molde(const uint8_t* ls, uint32_t spu)
{
    int ok = 1; uint32_t at = 0;
    for (int i = 0; i < s_nfix && ok; i++)
        if (memcmp(ls + s_fix[i][0], g3w_molde + s_fix[i][0], s_fix[i][1] - s_fix[i][0])) {
            ok = 0;
            for (at = s_fix[i][0]; at < s_fix[i][1] && ls[at] == g3w_molde[at]; at++) {}
        }
    if (ok && be32(ls + 0x1330) != spu) { ok = 0; at = 0x1330; }
    if (ok && memcmp(ls + G3W_TOP_LO, g3w_topo, sizeof g3w_topo)) {
        ok = 0;
        for (at = 0; at < sizeof g3w_topo && ls[G3W_TOP_LO + at] == g3w_topo[at]; at++) {}
        at += G3W_TOP_LO;
    }
    if (!ok && s_debug && (!s_debug_desde || (LONG64)GetTickCount64() / 1000 - s_t0 >= s_debug_desde)) {
        static volatile long s_n;
        if (__atomic_add_fetch(&s_n, 1, __ATOMIC_RELAXED) <= s_debug) {
            const uint32_t q = at & ~15u;
            const uint8_t* m = q >= G3W_TOP_LO ? g3w_topo + (q - G3W_TOP_LO) : g3w_molde + q;
            fprintf(stderr, "[wws-exec] fora do molde em 0x%05X: LS", at);
            for (int k = 0; k < 16; k++) fprintf(stderr, "%s%02X", k % 4 ? "" : " ", ls[q + k]);
            fprintf(stderr, " molde");
            for (int k = 0; k < 16; k++) fprintf(stderr, "%s%02X", k % 4 ? "" : " ", m[k]);
            fprintf(stderr, "%c", 10);
        }
    }
    return ok;
}

/* ---- a execução ---- */
typedef struct { uint32_t wid, spu, line_ea, idx, base, hdr_ea, inl, cnt; int recusa, etapa; } g3w_run;   /* etapa: até onde o corpo chegou */
static SPU_THREAD_LOCAL g3w_run t_run;
static SPU_THREAD_LOCAL g3w_fn t_job;

static void g3w_body(spu_context* c)
{
    g3w_run* r = &t_run;
    uint8_t* ls = c->ls;
    c->host_depth++;
    t_div = 0; t_step = 0;
    WR(c, CH_EVMASK, 2);
    (void)RD(c, CH_DEC);
    /* GETLLAR da linha de estado, as entradas, a reserva */
    dma(c, 0xD0, LINE_LS, r->line_ea, 0x80, 0);
    {   const uint32_t a = RD(c, CH_ATOMSTAT); if (a != 4) diverge(a, 4); }
    const uint32_t w70 = be32(ls + LINE_LS + 0x70);
    r->idx = w70 >> 16;
    r->base = be32(ls + LINE_LS + 0x3C);
    const uint32_t eline = r->base + 8 * (r->idx & ~15u);
    dma(c, 0x40, ENT_LS, eline, 0x80, 8);
    tagwait(c, 2, 0x100);
    const uint8_t* e = ls + ENT_LS + 8 * (r->idx & 15);
    if (be32(e) != 0x00900001) { r->recusa = R_ENTRADA; goto out; }
    r->hdr_ea = be32(e + 4);
    {   const uint8_t* h = vm_base + r->hdr_ea;
        if (memcmp(h, g3w_cab, 0x24) || memcmp(h + 0x28, g3w_cab + 0x28, 0x18)) { r->recusa = R_CAB; goto out; } }
    if (t_div) { r->recusa = R_CANAL; goto out; }
    wbe32(ls + LINE_LS + 0x70, ((r->idx + 1) & 0xFFFF) << 16 | ((w70 + 1) & 0xFFFF));
    ls[LINE_LS + 0x74 + 2 * r->spu] = (uint8_t)(r->idx >> 8);
    ls[LINE_LS + 0x75 + 2 * r->spu] = (uint8_t)r->idx;
    r->etapa = 1;
    dma(c, 0xB4, LINE_LS, r->line_ea, 0x80, 0);
    if (RD(c, CH_ATOMSTAT) != 0) { r->recusa = R_RESERVA; goto out; }
    /* daqui em diante a execução é nossa */
    r->etapa = 2; r->recusa = -1;
    dma(c, 0x40, HDR_LS, r->hdr_ea, 0x90, 0);
    r->inl = be32(ls + HDR_LS + 0x24);
    dma(c, 0x45, 0, SIG_LIST, 0x10, 0);
    { t_step += 100; const uint32_t q = irq(c); if (q != 1) diverge(q, 1); }
    tagwait(c, 0, 0x100); tagwait(c, 0, 0x8);
    tagwait(c, 0, 0x8); tagwait(c, 0, 0x20);
    dma(c, 0x40, 0x4000, MOD_EA, 0x4000, 1);
    dma(c, 0x40, 0x8000, MOD_EA + 0x4000, 0x4000, 1);
    dma(c, 0x40, 0xC000, MOD_EA + 0x8000, 0x4000, 1);
    dma(c, 0x40, 0x10000, MOD_EA + 0xC000, 0x3000, 1);
    tagwait(c, 0, 0x20); tagwait(c, 0, 0x20);
    dma(c, 0x40, IN_LIST_LS, r->inl, 0xB0, 1);
    dma(c, 0x45, IN_LS, IN_LIST_LS, 0xB0, 1);
    { t_step += 100; const uint32_t q = irq(c); if (q != 0) diverge(q, 0); }
    tagwait(c, 0, 0x20); tagwait(c, 0, 0x2);
    (void)RD(c, CH_DEC);
    tagwait(c, 2, 0x80);
    /* o estado que o gerenciador deixa na entrada do job */
    for (size_t i = 0; i < sizeof g3w_entrada / sizeof g3w_entrada[0]; i++) memcpy(ls + g3w_entrada[i].off, g3w_entrada[i].v, 16);
    memset(ls + HDR_LS, 0, 0x38);
    r->cnt = be32(ls + 0x1400) + 1;
    const uint32_t cb = r->cnt & 0xFF, idx = r->idx, le = r->line_ea;
    wq(ls + 0xEB0, 0x480F0000 | cb, MOD_EA, 0x08000B00 | cb, r->inl | 1);
    wq(ls + 0xEC0, 0x80000000, 1, 0x08000000 | cb, 2);
    wq(ls + 0x1340, r->wid << 16 | idx, 0, le | 0x08000003, r->wid << 16 | 0xFFFF);
    wq(ls + 0x1500, 0, le, 0, 0);
    wq(ls + 0x13A0, le | 3, 0xFFFF, idx, 0);
    wq(ls + 0x13B0, idx, 0, 0, 0);
    wq(ls + 0x1400, r->cnt, r->cnt, r->cnt, r->cnt);
    wq(ls + 0x1430, idx, 0, 0, 0);
    {   const uint8_t* p = ls + ENT_LS + 8 * (idx & 14);
        uint8_t pair[16];
        if (idx & 1) { memcpy(pair, p + 8, 8); memcpy(pair + 8, p, 8); } else memcpy(pair, p, 16);
        memcpy(ls + 0x1440, pair, 16);
        for (int k = 0; k < 4; k++) {
            const uint32_t s28 = be32(pair + 4 * k) >> 28;
            wbe32(ls + 0x13F0 + 4 * k, s28); wbe32(ls + 0x1680 + 4 * k, s28);
        } }
    wq(ls + 0x1460, le | 3, 0xFFFF, idx, 0);
    wq(ls + 0x14C0, eline, 0, 0, 0);
    /* os registros que o job lê; r5 = o cabeçalho do módulo, r8 = LS 0x1620, r4 = 0x13F0 */
    memset(&c->gpr[0], 0, sizeof c->gpr[0]); c->gpr[0]._u32[0] = JOB_RET;
    memset(&c->gpr[1], 0, sizeof c->gpr[1]); c->gpr[1]._u32[0] = 0x3F990; c->gpr[1]._u32[1] = 0x1980;
    for (int k = 0; k < 4; k++) {
        c->gpr[3]._u32[k] = 0x1330;
        c->gpr[4]._u32[k] = be32(ls + 0x13F0 + 4 * k);
        c->gpr[5]._u32[k] = be32(ls + 0x4000 + 4 * k);
        c->gpr[8]._u32[k] = be32(ls + 0x1620 + 4 * k);
    }
    /* o job, com interrupções ligadas (máscara 2) como o gerenciador o chama */
    t_job = spu_lifted_lookup(c, JOB_ENTRY);
    if (!t_job) { fprintf(stderr, "[wws-exec] job sem código traduzido em 0x%X%c", JOB_ENTRY, 10); t_div = 1; goto out; }
    c->pc = JOB_ENTRY;
    if (g_wwstrace_on) spu_wwstrace_branch(c);
    c->int_enable = 1;
    r->etapa = 3;
    g_spu_stop_pc = JOB_RET;
    t_job(c);
    spu_drain_call(c, JOB_RET);
    r->etapa = 4;
out:
    c->host_depth--;
}

/* a volta do job (numa execução própria do runtime: um job que redefine a pilha volta pelo laço de cima do
 * spu_run_with_halt, não por g3w_body): esperas, a liberação da lane, a lista de sinal da tag 5, o estado do fim */
static void g3w_tail(spu_context* c)
{
    g3w_run* r = &t_run;
    uint8_t* ls = c->ls;
    c->host_depth++;
    c->pc = JOB_RET;
    if (g_wwstrace_on) spu_wwstrace_branch(c);   /* SPU_WWSDUMP: o registro do retorno */
    tagwait(c, 2, 0x80);
    (void)RD(c, CH_DEC);
    tagwait(c, 0, 0x80); tagwait(c, 0, 0x20);
    tagwait(c, 0, 0x20); tagwait(c, 0, 0x80000000);
    for (int tries = 0; ; tries++) {
        dma(c, 0xD0, LINE_LS, r->line_ea, 0x80, 0);
        { const uint32_t a = RD(c, CH_ATOMSTAT); if (a != 4) diverge(a, 4); }
        ls[LINE_LS + 0x74 + 2 * r->spu] = 0xFF; ls[LINE_LS + 0x75 + 2 * r->spu] = 0xFF;
        dma(c, 0xB4, LINE_LS, r->line_ea, 0x80, 0);
        if (RD(c, CH_ATOMSTAT) == 0) break;
        if (tries > 100000) { t_div = 1; break; }
    }
    dma(c, 0x45, 0, SIG_LIST, 0x10, 5);
    { t_step += 100; const uint32_t q = irq(c); if (q != 0x20) diverge(q, 0x20); }
    tagwait(c, 0, 0x80000000); tagwait(c, 0, 0x20);
    if (spu_rchcnt(c, CH_EVSTAT)) (void)irq(c);
    tagwait(c, 0, 0x20); tagwait(c, 0, 0x20);
    tagwait(c, 2, 0x80);
    (void)RD(c, CH_DEC);
    WR(c, CH_EVMASK, 0);
    /* o estado do fim: o molde fora dos campos variáveis; 0xEB0; a linha da liberação já está em 0x80 */
    for (int i = 0; i < s_nfix; i++) memcpy(ls + s_fix[i][0], g3w_molde + s_fix[i][0], s_fix[i][1] - s_fix[i][0]);
    for (size_t i = 0; i < sizeof g3w_fim_molde / sizeof g3w_fim_molde[0]; i++)
        memcpy(ls + g3w_fim_molde[i], g3w_molde + g3w_fim_molde[i], 16);
    g3w_ctx(ls, 1);
    wq(ls + 0xEB0, 0, MOD_EA, 0, r->inl | 1);
    g_spurs_pm_polls = 1;
    g_spurs_pm_exited = 1;
    c->gpr[3]._u32[0] = 0xB00;
    c->pc = SPURS_PM_EXIT_TO_KERNEL_LS;
    c->status = SPU_STATUS_STOPPED_BY_STOP;
    r->etapa = 5;
    c->host_depth--;
}

static int g3w_native(spu_context* c, uint32_t wid, uint32_t spu, uint32_t spurs_ea, int first)
{
    static uint32_t s_wids = 0;
    (void)spurs_ea;
    if (!s_wids) {
        const char* e = getenv("GOW3_WWS_EXEC_WIDS");
        s_wids = e ? (uint32_t)strtoul(e, NULL, 16) : 0x700;
        g3w_fix_init();
    }
    if (wid >= 32 || !(s_wids & (1u << wid)) || spu > 5) return -1;
    if (s_stats) g3w_stats();
    if (first) { __atomic_add_fetch(&s_rec[R_FRESH], 1, __ATOMIC_RELAXED); return -1; }
    uint8_t* ls = c->ls;
    if (!g3w_no_molde(ls, spu)) { __atomic_add_fetch(&s_rec[R_MOLDE], 1, __ATOMIC_RELAXED); return -1; }
    /* olhada sem efeito: a próxima entrada da lista */
    g3w_run* r = &t_run;
    memset(r, 0, sizeof *r);
    r->wid = wid; r->spu = spu; r->line_ea = c->gpr[4]._u32[1];
    {   const uint8_t* L = vm_base + r->line_ea;
        const uint32_t idx = be32(L + 0x70) >> 16, base = be32(L + 0x3C);
        const uint8_t* e = vm_base + base + 8 * idx;
        if (be32(e) != 0x00900001) { __atomic_add_fetch(&s_rec[R_ENTRADA], 1, __ATOMIC_RELAXED); return -1; } }
    g3w_ctx(ls, 0);
    u128 keep[6]; memcpy(keep, c->gpr, sizeof keep);
    const uint32_t keep_pc = (uint32_t)c->pc;
    r->recusa = R_CANAL;
    int halted = spu_run_with_halt(g3w_body, c);
    g_spu_stop_pc = 0;
    /* o job voltou a 0x32B0 (direto ou pelo laço de cima depois de redefinir a pilha): a volta */
    if (r->recusa < 0 && r->etapa == 3 && !halted && ((uint32_t)c->pc & SPU_LS_MASK) == JOB_RET) r->etapa = 4;
    if (r->recusa < 0 && r->etapa == 4) {
        c->int_enable = 0;
        halted = spu_run_with_halt(g3w_tail, c);
    }
    if (r->recusa < 0 && r->etapa < 5) {
        /* parou depois da reserva (no job ou na volta): não há como devolver ao traduzido; fica como o SPU parou */
        static volatile long s_n;
        if (__atomic_add_fetch(&s_n, 1, __ATOMIC_RELAXED) <= 16)
            fprintf(stderr, "[wws-exec] parou na etapa %d (halted=%d, pc 0x%05X): wid %u spu %u job %X%c", r->etapa, halted,
                    (uint32_t)c->pc & SPU_LS_MASK, wid, spu, r->idx, 10);
        __atomic_add_fetch(&s_nat, 1, __ATOMIC_RELAXED);
        return halted;
    }
    if (r->recusa >= 0 && halted) {
        static volatile long s_n;
        if (__atomic_add_fetch(&s_n, 1, __ATOMIC_RELAXED) <= 16)
            fprintf(stderr, "[wws-exec] parou antes da reserva (etapa %d, pc 0x%05X, status 0x%X)%c", r->etapa,
                    (uint32_t)c->pc & SPU_LS_MASK, c->status, 10);
    }
    if (r->recusa >= 0) {   /* nada foi reservado: o gerenciador traduzido faz esta execução do começo */
        __atomic_add_fetch(&s_rec[r->recusa], 1, __ATOMIC_RELAXED);
        if (s_debug && r->recusa == R_CANAL) {
            static volatile long s_n;
            if (__atomic_add_fetch(&s_n, 1, __ATOMIC_RELAXED) <= s_debug)
                fprintf(stderr, "[wws-exec] canal antes da reserva: passo %u lido %08X esperado %08X (wid %u spu %u)%c",
                        t_div_at, t_div_got, t_div_exp, wid, spu, 10);
        }
        memcpy(c->gpr, keep, sizeof keep);
        c->pc = keep_pc;
        c->status = 0;
        return -1;
    }
    __atomic_add_fetch(&s_nat, 1, __ATOMIC_RELAXED);
    if (t_div) {
        const long n = __atomic_add_fetch(&s_div, 1, __ATOMIC_RELAXED);
        if (n <= 8) fprintf(stderr, "[wws-exec] divergência num canal: wid %u spu %u job %X passo %u lido %08X esperado %08X%c",
                            wid, spu, r->idx, t_div_at, t_div_got, t_div_exp, 10);
    }
    return halted;
}

__attribute__((constructor)) static void g3w_register(void)
{
    const char* e = getenv("GOW3_WWS_EXEC");
    if (!e || e[0] != '1') return;
    const char* s = getenv("GOW3_WWS_EXEC_STATS");
    s_stats = s ? atoi(s) : 0;
    const char* d = getenv("GOW3_WWS_EXEC_DEBUG");
    s_debug = d ? atoi(d) : 0;
    const char* dd = getenv("GOW3_WWS_EXEC_DEBUG_DESDE");
    s_debug_desde = dd ? atoi(dd) : 0;
    s_t0 = (LONG64)GetTickCount64() / 1000;
    g_spurs_pm_native = g3w_native;
    fprintf(stderr, "[wws-exec] executor nativo das listas EDGE ligado%c", 10);
}
#endif
