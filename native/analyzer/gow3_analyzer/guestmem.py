# SPDX-License-Identifier: GPL-2.0-only
"""Memória do convidado no Unicorn com endereços efetivos de 32 bits, como no PS3 sob o RPCS3 e no
runtime do ps3recomp (os acessos usam (uint32_t)ea).

O Unicorn roda o PowerPC em modo de 64 bits, em que um ponteiro estendido com sinal
(0xFFFFFFFF_D0012340, comum para a pilha em 0xD0000000 e a memória de vídeo em 0xC0000000) seria um
endereço diferente. Aqui cada região é um buffer nosso mapeado com mem_map_ptr; quando o código toca
um endereço acima de 4 GB, a página correspondente vira um espelho (o mesmo buffer) da página
endereço & 0xFFFFFFFF. Leitura e escrita caem no mesmo lugar, como no PS3.
"""

from __future__ import annotations

import ctypes
import mmap

from unicorn import UC_PROT_ALL

PAGE = 0x1000
LOW_MASK = 0xFFFFFFFF


class GuestMemory:
    def __init__(self, mu):
        self.mu = mu
        self.regions: list[dict] = []
        self.aliases: list[tuple[int, dict]] = []

    def map(self, base: int, size: int) -> dict:
        size = (size + PAGE - 1) & ~(PAGE - 1)
        mm = mmap.mmap(-1, size)
        cbuf = ctypes.c_char.from_buffer(mm)
        region = {"base": base, "size": size, "mm": mm, "cbuf": cbuf, "ptr": ctypes.addressof(cbuf)}
        self.mu.mem_map_ptr(base, size, UC_PROT_ALL, region["ptr"])
        self.regions.append(region)
        return region

    def unmap(self, base: int) -> None:
        for r in list(self.regions):
            if r["base"] == base:
                for high, target in list(self.aliases):
                    if target is r:
                        self.mu.mem_unmap(high, PAGE)
                        self.aliases.remove((high, target))
                self.mu.mem_unmap(r["base"], r["size"])
                self.regions.remove(r)
                del r["cbuf"]
                r["mm"].close()

    def find(self, addr: int) -> dict | None:
        for r in self.regions:
            if r["base"] <= addr < r["base"] + r["size"]:
                return r
        return None

    def alias(self, addr: int) -> bool:
        """Mapeia a página de `addr` (acima de 4 GB) como espelho da página de 32 bits; False se a
        página de 32 bits não estiver mapeada (o acesso falha, como no PS3)."""
        high = addr & ~(PAGE - 1)
        low = high & LOW_MASK
        r = self.find(low)
        if r is None or high == low:
            return False
        self.mu.mem_map_ptr(high, PAGE, UC_PROT_ALL, r["ptr"] + (low - r["base"]))
        self.aliases.append((high, r))
        return True
