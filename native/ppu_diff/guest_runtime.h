// SPDX-License-Identifier: GPL-2.0-only
// Runtime mínimo para executar código PowerPC recompilado pelo ps3recomp fora de um jogo:
// memória do convidado (big-endian, por páginas), carga do ELF, pilha e despacho de chamadas.
#pragma once

#include "ppu_recomp.h"

bool guest_load_elf(const char* path);
void guest_prepare(ppu_context* ctx, uint64_t toc);
void guest_call(ppu_context* ctx, void (*fn)(ppu_context*));
int guest_failures();
