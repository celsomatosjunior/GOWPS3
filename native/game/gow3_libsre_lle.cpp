// SPDX-License-Identifier: GPL-2.0-only
/*
 * GOW3 Native: LLE seletivo da libsre (SPURS) para a fila LFQueue.
 *
 * O ps3recomp não implementa _cellSpursLFQueuePushBody, e o caminho ANY2ANY do CellSyncLFQueue
 * (GetPushPointer2/CompletePushPointer2) também não existe no RPCS3, que roda a libsre original.
 * O consumidor é o código SPU do próprio jogo (Edge Zlib), que lê e grava a linha de 128 bytes da
 * fila com GETLLAR/PUTLLC. Por isso a fila precisa ser exatamente a da Sony: em vez de reescrevê-la,
 * as funções da libsre do firmware do usuário são recompiladas (tools/lift_prx.py + ppu_lifter.py,
 * base 0x30000000) e só os NIDs da LFQueue são ligados a elas. O resto do SPURS continua no HLE.
 *
 * A imagem relocada (derivada do firmware do usuário) é lida em tempo de execução de um arquivo
 * local, nunca embutida no executável: GOW3_LIBSRE_IMAGE ou libsre_image.bin ao lado do .exe.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "prx_loader.h"
#include "ppu_recomp.h"   /* ppu_context */

#ifdef _WIN32
#include <windows.h>
#endif

extern "C" {
extern const prx_func_entry libsre_function_table[];
extern const uint64_t       libsre_function_table_count;
void ppu_register_function(uint64_t addr, void (*fn)(ppu_context*));
void spu_taskset_signal_task(uint32_t taskset_ea, uint32_t taskId);
uint32_t spurs_taskset_find(uint32_t spurs_ea, uint32_t wid, uint32_t taskId);
}

/* A função de sinal que a LFQueue recebe (fpSendSignal, libsre 0x300127CC) procura o taskset nas
 * estruturas internas do SPURS da libsre, que aqui não existem: o SPURS é o do HLE. Ela é trocada por
 * esta, que entrega o sinal pelo mecanismo do runtime (bit em CSTS_SIGNALLED + acordar a tarefa). */
static const uint32_t LIBSRE_SEND_SIGNAL = 0x300127CCu;

static void gow3_lfqueue_send_signal(ppu_context* ctx)
{
    uint32_t ea = (uint32_t)ctx->gpr[3], id = (uint32_t)ctx->gpr[4];
    static int n = 0;
    if (n++ < 16)
        fprintf(stderr, "[gow3-lle] LFQueue sinal: eaSignal=0x%08X id=0x%08X\n", ea, id);
    /* Como a libsre (0x127CC): eaSignal & 0xF == 1 -> dono é a instância SPURS e o id é
     * (wid << 8) | taskId; senão o dono é o próprio taskset. */
    uint32_t taskset = 0, task = id & 0xFF;
    if ((ea & 0xF) == 1)
        taskset = spurs_taskset_find(ea & ~0xFu, (id >> 8) & 0xFFFFFFu, task);
    else if ((ea & 0xF) == 0)
        taskset = ea;
    if (taskset && task <= 0x7F) {
        spu_taskset_signal_task(taskset, task);
        ctx->gpr[3] = 0;
    } else {
        fprintf(stderr, "[gow3-lle] LFQueue sinal sem taskset conhecido (ea=0x%08X id=0x%08X)\n", ea, id);
        ctx->gpr[3] = 0;
    }
}

static const uint32_t LIBSRE_BASE = 0x30000000u;

/* NID -> OPD (absoluto, base 0x30000000) das exportações cellSpurs da fila, conferidos no
 * libsre_exports.json do firmware 4.x do usuário. */
static const struct { uint32_t nid; uint32_t opd; const char* name; } k_lfqueue[] = {
    {0x011EE38Bu, 0x30031844u, "_cellSpursLFQueueInitialize"},
    {0x8A85674Du, 0x3003184Cu, "_cellSpursLFQueuePushBody"},
    {0x35DAE22Bu, 0x30031854u, "_cellSpursLFQueuePopBody"},
};

static void register_one(uint32_t guest_addr, void (*host)(void*))
{
    ppu_register_function(guest_addr, (void (*)(ppu_context*))host);
}

static int image_path(char* out, size_t n)
{
    const char* env = getenv("GOW3_LIBSRE_IMAGE");
    if (env && *env) { snprintf(out, n, "%s", env); return 1; }
#ifdef _WIN32
    char exe[1024];
    DWORD len = GetModuleFileNameA(NULL, exe, sizeof exe);
    if (!len || len >= sizeof exe) return 0;
    char* slash = strrchr(exe, '\\');
    if (slash) slash[1] = 0;
    snprintf(out, n, "%slibsre_image.bin", exe);
    return 1;
#else
    snprintf(out, n, "libsre_image.bin");
    return 1;
#endif
}

extern "C" void gow3_watch_install(void);   /* gow3_diag.cpp */

extern "C" void ps3_load_prx_modules(void)
{
    gow3_watch_install();   /* depois do vm_base existir, antes do jogo rodar */
    if (getenv("GOW3_LIBSRE_OFF")) {
        fprintf(stderr, "[gow3-lle] GOW3_LIBSRE_OFF: LFQueue no HLE\n");
        return;
    }
    char path[1100];
    uint32_t size = 0;
    uint8_t* image = image_path(path, sizeof path) ? prx_image_load_file(path, &size) : NULL;
    if (!image) {
        fprintf(stderr, "[gow3-lle] sem imagem da libsre (%s): LFQueue fica no HLE\n", path);
        return;
    }
    /* Confere que a imagem é a mesma da recompilação: o OPD de cada exportação aponta para uma
     * função registrada na tabela lifted. */
    prx_export exports[sizeof k_lfqueue / sizeof k_lfqueue[0]];
    uint32_t n = 0;
    for (const auto& e : k_lfqueue) {
        uint32_t off = e.opd - LIBSRE_BASE;
        if (off + 8 > size) continue;
        uint32_t code = ((uint32_t)image[off] << 24) | ((uint32_t)image[off + 1] << 16) |
                        ((uint32_t)image[off + 2] << 8) | image[off + 3];
        bool lifted = false;
        for (uint64_t i = 0; i < libsre_function_table_count; i++)
            if ((uint32_t)libsre_function_table[i].addr == code) { lifted = true; break; }
        if (!lifted) {
            fprintf(stderr, "[gow3-lle] %s: código 0x%08X não está na libsre recompilada; imagem diferente?\n",
                    e.name, code);
            continue;
        }
        exports[n++] = prx_export{e.nid, off};
        fprintf(stderr, "[gow3-lle] %s (NID 0x%08X) -> libsre real, OPD 0x%08X, código 0x%08X\n",
                e.name, e.nid, e.opd, code);
    }
    prx_module m = {};
    m.name = "libsre";
    m.base = LIBSRE_BASE;
    m.image = image;
    m.image_size = size;
    m.funcs = libsre_function_table;
    m.func_count = libsre_function_table_count;
    m.exports = exports;
    m.export_count = n;
    prx_load_result r = prx_load_module(&m, register_one);
    if (!r.ok) fprintf(stderr, "[gow3-lle] falha ao carregar a libsre\n");
    else ppu_register_function(LIBSRE_SEND_SIGNAL, gow3_lfqueue_send_signal);
    free(image);
}
