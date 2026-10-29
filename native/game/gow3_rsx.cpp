// SPDX-License-Identifier: GPL-2.0-only
/*
 * GOW3 Native: escolha do motor de desenho do RSX em tempo de execução (Windows).
 *
 * O main.cpp do modelo do ps3recomp liga só o backend D3D12. Ele grava os desenhos e só os executa
 * no flip, então não devolve um quadro à memória do PS3 no meio dele, e o God of War III precisa
 * disso: copia o buffer de tela para a memória principal com o NV3089, filtra-o com o MLAA nos SPUs
 * e o usa de volta como textura. RSX_LIVE_DRAW=1 troca pelo motor "live draw"
 * (libs/video/rsx_live_draw.c), que desenha na hora: a janela fica com o backend nulo e o live
 * draw apresenta nela, como faz o boot_main do ps3recomp. Sem a variável, nada muda.
 *
 * O gow3_build.py troca os três rsx_backend_* do main.cpp por gow3_rsx_init/present/pump.
 */
#ifdef _WIN32
#include <stdint.h>
#include <stdio.h>

extern "C" uint8_t* vm_base;

extern "C" int  rsx_d3d12_backend_init(uint32_t w, uint32_t h, const char* title);
extern "C" void rsx_d3d12_backend_present(void);
extern "C" int  rsx_d3d12_backend_pump_messages(void);
extern "C" int  rsx_live_draw_enabled(void);
extern "C" int  rsx_live_draw_init(void* hwnd, uint32_t w, uint32_t h,
                                   const uint8_t* (*guest_ptr)(void*, uint32_t, uint32_t, uint32_t),
                                   void* user);
extern "C" void rsx_live_draw_present(uint32_t buffer_id);
extern "C" int  rsx_null_backend_init(uint32_t w, uint32_t h, const char* title);
extern "C" int  rsx_null_backend_pump_messages(void);
extern "C" void* rsx_null_backend_get_hwnd(void);
extern "C" void rsx_null_backend_suppress_present(int on);
extern "C" uint32_t cellGcmResolveLocated(int local, uint32_t offset);
extern "C" uint32_t cellGcmResolveIO(uint32_t offset);
extern "C" unsigned cellGcmGetCurrentDisplayBufferId(void);

static int s_live = 0;   /* live draw escolhido E inicializado */

/* (location, offset) -> memória do host. location 0 é a memória local do RSX, 1 a principal (pela
 * tabela de IO). O intervalo inteiro precisa ser válido. Igual ao boot_main. */
static const uint8_t* live_guest_ptr(void*, uint32_t location, uint32_t offset, uint32_t min_bytes)
{
    if (!vm_base) return nullptr;
    uint32_t ea;
    if (location == 0) {
        ea = cellGcmResolveLocated(1, offset);
    } else {
        ea = cellGcmResolveIO(offset);
        if (!ea) ea = cellGcmResolveLocated(0, offset);
    }
    if (!ea || ea == 0xFFFFFFFFu || (uint64_t)ea + min_bytes > 0x100000000ull) return nullptr;
    return vm_base + ea;
}

extern "C" int gow3_rsx_init(uint32_t w, uint32_t h, const char* title)
{
    if (rsx_live_draw_enabled()) {
        if (rsx_null_backend_init(w, h, title) == 0 &&
            rsx_live_draw_init(rsx_null_backend_get_hwnd(), w, h, live_guest_ptr, nullptr) == 0) {
            s_live = 1;
            rsx_null_backend_suppress_present(1);
            fprintf(stderr, "[gow3-rsx] live draw ligado (D3D12)\n");
            return 0;
        }
        fprintf(stderr, "[gow3-rsx] live draw falhou; voltando ao backend D3D12\n");
    }
    return rsx_d3d12_backend_init(w, h, title);
}

/* Apresenta o buffer para o qual o jogo virou (o live draw procura a superfície registrada nele). */
extern "C" void gow3_rsx_present(void)
{
    if (s_live) rsx_live_draw_present(cellGcmGetCurrentDisplayBufferId());
    else        rsx_d3d12_backend_present();
}

extern "C" int gow3_rsx_pump(void)
{
    return s_live ? rsx_null_backend_pump_messages() : rsx_d3d12_backend_pump_messages();
}
#endif
