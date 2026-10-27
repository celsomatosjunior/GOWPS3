# SPDX-License-Identifier: GPL-2.0-only
"""Executor de referência: roda o código de máquina PowerPC original no Unicorn (motor derivado do
QEMU, GPL-2.0), a partir do mesmo estado inicial dado ao código recompilado.

Modelo de CPU: o padrão de 64 bits do Unicorn (POWER10), com tradução de endereços desligada
(TLB "virtual": endereço do convidado = endereço mapeado). Observação verificada no código do
Unicorn 2.1.4: `ctl_set_cpu_model` com um modelo PPC64 (ex.: 970) seleciona por engano uma CPU de
32 bits (o índice não recebe o deslocamento da tabela), e o MSR[SF] não pode ser ligado; por isso o
modelo padrão é usado. O conjunto de instruções do PPU (PowerPC 2.02, sem VMX) é um subconjunto do
ISA do POWER10. A validação contra o QEMU (casos do corpus) é feita no CI.
Limitações documentadas: o Unicorn não expõe registradores vetoriais (VMX), por isso funções com
VMX ficam fora; o FPSCR não é comparado.
"""

from __future__ import annotations

import math
import struct

from unicorn import UC_ARCH_PPC, UC_HOOK_CODE, UC_HOOK_INTR, UC_HOOK_MEM_WRITE, UC_MODE_BIG_ENDIAN, UC_MODE_PPC64, Uc, UcError
from unicorn.unicorn_const import UC_TLB_VIRTUAL
from unicorn import ppc_const as P

from . import state as S


MSR_FP = 1 << 13
# fctiw=14, fctiwz=15, fctid=814, fctidz=815 (opcode primário 63, campo XO de 10 bits)
FCTI_FORMS = {14: (32, False), 15: (32, True), 814: (64, False), 815: (64, True)}


def _fcti_isa(bits: int, width: int, toward_zero: bool):
    """Resultado do Book I 4.6.7 quando o valor não cabe no inteiro: satura (positivo -> máximo,
    negativo -> mínimo). Devolve None quando o valor cabe ou é NaN (aí a CPU de referência acerta)."""
    v = struct.unpack(">d", bits.to_bytes(8, "big"))[0]
    if math.isnan(v):
        return None
    if math.isinf(v):
        r = 1 << 70 if v > 0 else -(1 << 70)
    else:
        r = math.trunc(v) if toward_zero else round(v)  # round(): meio para o par (RN padrão)
    lo, hi = -(1 << (width - 1)), (1 << (width - 1)) - 1
    if lo <= r <= hi:
        return None
    r = hi if r > hi else lo
    return r & S.MASK  # inteiro de 32 bits com extensão de sinal, como o QEMU monta o registrador


class Reference:
    """Uma única máquina Unicorn por executável (criada uma vez). Entre casos, a memória volta ao
    estado original restaurando só os bytes escritos, e o XER (inclusive CA) é reposto por `mtxer`."""

    def __init__(self, image):
        self.image = image
        self.mu = None
        self.dirty: set[int] = set()   # bytes escritos desde a última restauração
        self.written: set[int] = set()  # bytes escritos na chamada atual
        self.exceptions: list = []
        self.fcti_hooked: set[int] = set()
        self.seed = None

    def _create(self):
        mu = Uc(UC_ARCH_PPC, UC_MODE_PPC64 | UC_MODE_BIG_ENDIAN)
        mu.ctl_set_tlb_mode(UC_TLB_VIRTUAL)
        mapped = []
        for seg in self.image.loads:
            lo = seg["vaddr"] & ~0xFFF
            hi = (seg["vaddr"] + seg["memsz"] + 0xFFF) & ~0xFFF
            # segmentos vizinhos podem dividir a mesma página
            for a, b in mapped:
                if lo < b and hi > a:
                    lo = max(lo, b)
            if hi > lo:
                mu.mem_map(lo, hi - lo)
                mapped.append((lo, hi))
            if seg["filesz"]:
                mu.mem_write(seg["vaddr"], self.image.data[seg["offset"]:seg["offset"] + seg["filesz"]])
        mu.mem_map(S.STACK_BASE, S.STACK_SIZE)
        mu.mem_map(S.SCRATCH_BASE, S.SCRATCH_SIZE)
        mu.mem_map(S.RETURN_SENTINEL, 0x1000)
        # sentinela: nop; mfxer r3 (leitura do XER completo); mtxer r3 (preparo do XER); nop
        mu.mem_write(S.RETURN_SENTINEL, bytes.fromhex("60000000" "7c6102a6" "7c6103a6" "60000000"))
        # Os callbacks ficam guardados no objeto: vivem tanto quanto a máquina.
        self._on_write_cb = self._on_write
        self._on_intr_cb = self._on_intr
        self._on_fcti_cb = self._on_fcti
        mu.hook_add(UC_HOOK_MEM_WRITE, self._on_write_cb)
        mu.hook_add(UC_HOOK_INTR, self._on_intr_cb)
        self.mu = mu

    def _on_write(self, uc, access, address, size, value, data):
        for k in range(size):
            self.written.add(address + k)
            self.dirty.add(address + k)

    def _on_intr(self, uc, intno, data):
        # Qualquer exceção da CPU (instrução ilegal, trap, sc) encerra a execução como falha.
        self.exceptions.append((intno, uc.reg_read(P.UC_PPC_REG_PC)))
        uc.emu_stop()

    def _on_fcti(self, uc, address, size, data):
        # Correção documentada da referência: o QEMU 5 que o Unicorn 2.1 usa devolve 0x80000000 em
        # TODA conversão fcti* inválida, inclusive estouro positivo; o ISA manda saturar. Nesses
        # endereços a conversão é refeita conforme o ISA e a instrução é pulada.
        _a, w, width, toward_zero = data
        frt, frb = (w >> 21) & 31, (w >> 11) & 31
        fixed = _fcti_isa(uc.reg_read(getattr(P, f"UC_PPC_REG_FPR{frb}")) & S.MASK, width, toward_zero)
        if fixed is not None:
            uc.reg_write(getattr(P, f"UC_PPC_REG_FPR{frt}"), fixed)
            uc.reg_write(P.UC_PPC_REG_PC, address + 4)

    def _original_byte(self, addr: int) -> int:
        for seg in self.image.loads:
            if seg["vaddr"] <= addr < seg["vaddr"] + seg["filesz"]:
                return self.image.data[seg["offset"] + addr - seg["vaddr"]]
        return 0

    def _reset_memory(self, seed: int):
        mu = self.mu
        for a in self.dirty:
            if not S.SCRATCH_BASE <= a < S.SCRATCH_BASE + S.SCRATCH_SIZE:
                try:
                    mu.mem_write(a, bytes([self._original_byte(a)]))
                except UcError:
                    pass  # o gancho de escrita dispara antes da falha: endereço não mapeado
        if self.dirty or self.seed != seed:
            mu.mem_write(S.SCRATCH_BASE, S.scratch_bytes(seed))
        self.seed = seed
        self.dirty.clear()

    def _fcti_sites(self, start: int, end: int) -> list[tuple[int, int, int, bool]]:
        out = []
        for a in range(start, end, 4):
            raw = self.image.read(a, 4)
            if len(raw) != 4:
                continue
            w = int.from_bytes(raw, "big")
            xo = (w >> 1) & 0x3FF
            if w >> 26 == 63 and xo in FCTI_FORMS and not w & 1:  # sem Rc (a forma com ponto altera CR1)
                width, toward_zero = FCTI_FORMS[xo]
                out.append((a, w, width, toward_zero))
        return out

    def run(self, code_addr: int, case: dict, code_end: int | None = None, reset: bool = True,
            limit: int | None = None) -> dict:
        """Executa a função a partir do estado `case`. Com reset=False a memória continua da chamada
        anterior, como num processo único (usado na validação contra o QEMU)."""
        if self.mu is None:
            self._create()
            self.seed = None
            self._reset_memory(case.get("seed", 0))
        elif reset:
            self._reset_memory(case["seed"])
        mu = self.mu
        if code_end and code_addr not in self.fcti_hooked:
            self.fcti_hooked.add(code_addr)
            for site in self._fcti_sites(code_addr, code_end):
                mu.hook_add(UC_HOOK_CODE, self._on_fcti_cb, site, site[0], site[0])
        mu.reg_write(P.UC_PPC_REG_MSR, mu.reg_read(P.UC_PPC_REG_MSR) | MSR_FP)
        msr = mu.reg_read(P.UC_PPC_REG_MSR)
        if not msr >> 63 or not msr & MSR_FP:
            raise RuntimeError("Unicorn sem modo de 64 bits ou sem ponto flutuante (MSR=%x)" % msr)
        # XER completo (SO/OV/CA) pelo próprio processador: mtxer r3
        mu.reg_write(P.UC_PPC_REG_3, case["xer"])
        mu.emu_start(S.RETURN_SENTINEL + 8, S.RETURN_SENTINEL + 12, count=1)
        for i in range(32):
            mu.reg_write(getattr(P, f"UC_PPC_REG_{i}"), case["gpr"][i])
            mu.reg_write(getattr(P, f"UC_PPC_REG_FPR{i}"), case["fpr"][i])
        mu.reg_write(P.UC_PPC_REG_CR, case["cr"])
        mu.reg_write(P.UC_PPC_REG_CTR, case["ctr"])
        mu.reg_write(P.UC_PPC_REG_LR, case["lr"])
        self.written = set()
        self.exceptions = []
        try:
            mu.emu_start(code_addr, S.RETURN_SENTINEL, count=limit or S.INSTRUCTION_LIMIT)
        except UcError as error:
            msg = str(error).upper()
            kind = "read" if "READ" in msg else "write" if "WRITE" in msg else "fetch" if "FETCH" in msg else "cpu"
            return {"fault": kind, "addr": mu.reg_read(P.UC_PPC_REG_PC)}
        if self.exceptions:
            return {"fault": f"cpu-excecao-{self.exceptions[0][0]}", "addr": self.exceptions[0][1]}
        if mu.reg_read(P.UC_PPC_REG_PC) != S.RETURN_SENTINEL:
            return {"fault": "timeout", "addr": mu.reg_read(P.UC_PPC_REG_PC)}
        result_gpr = [mu.reg_read(getattr(P, f"UC_PPC_REG_{i}")) & S.MASK for i in range(32)]
        # O Unicorn devolve em UC_PPC_REG_XER só o campo bruto, sem SO/OV/CA (o QEMU guarda esses bits
        # à parte). O XER completo é lido executando `mfxer r3` na página sentinela, depois de todos
        # os outros registradores já terem sido lidos.
        mu.emu_start(S.RETURN_SENTINEL + 4, S.RETURN_SENTINEL + 8, count=1)
        xer = mu.reg_read(P.UC_PPC_REG_3) & 0xFFFFFFFF
        mu.reg_write(P.UC_PPC_REG_3, result_gpr[3])
        pairs = [(a, mu.mem_read(a, 1)[0]) for a in sorted(self.written)]
        return {
            "gpr": result_gpr,
            "fpr": [mu.reg_read(getattr(P, f"UC_PPC_REG_FPR{i}")) & S.MASK for i in range(32)],
            "cr": mu.reg_read(P.UC_PPC_REG_CR) & 0xFFFFFFFF,
            "xer": xer & 0xE0000000,
            "ctr": mu.reg_read(P.UC_PPC_REG_CTR) & S.MASK,
            "lr": mu.reg_read(P.UC_PPC_REG_LR) & S.MASK,
            "mem_count": len(pairs), "mem_hash": S.fnv1a(pairs), "mem_first": pairs[0][0] if pairs else 0,
        }
