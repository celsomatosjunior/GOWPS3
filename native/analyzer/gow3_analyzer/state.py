# SPDX-License-Identifier: GPL-2.0-only
"""Estados iniciais determinísticos do teste diferencial, compartilhados pelos dois executores.

O mesmo gerador (xorshift64*) é implementado em runtime/state_runtime.cpp: a memória de rascunho é
preenchida igual nos dois lados a partir da semente do caso, sem precisar gravar os bytes.
"""

from __future__ import annotations

MASK = (1 << 64) - 1
SCRATCH_BASE, SCRATCH_SIZE = 0x30000000, 0x40000
STACK_BASE, STACK_SIZE = 0x0FF00000, 0x00100000
STACK_TOP = STACK_BASE + STACK_SIZE - 0x1000
RETURN_SENTINEL = 0x0E000000
TLS_POINTER = SCRATCH_BASE + 0x38000
INSTRUCTION_LIMIT = 5_000_000
# 2ª tentativa, só para os casos em que o recompilado terminou e a referência atingiu o limite
INSTRUCTION_LIMIT_LONG = 400_000_000


class XorShift:
    def __init__(self, seed: int):
        self.s = (seed ^ 0x9E3779B97F4A7C15) & MASK or 1

    def next(self) -> int:
        x = self.s
        x ^= (x >> 12)
        x ^= (x << 25) & MASK
        x ^= (x >> 27)
        self.s = x
        return (x * 0x2545F4914F6CDD1D) & MASK


def scratch_word_pointer(v: int) -> int:
    """Endereço válido (alinhado a 16) dentro da área de rascunho."""
    return SCRATCH_BASE + (v % SCRATCH_SIZE) // 16 * 16


def scratch_bytes(seed: int) -> bytes:
    """Semente par: bytes aleatórios. Semente ímpar: cada palavra de 32 bits é um ponteiro válido
    para dentro da própria área, para que funções que seguem ponteiros de estruturas (comuns no
    jogo; os ponteiros do PS3 são de 32 bits) executem em vez de falhar no primeiro acesso."""
    rng = XorShift(seed ^ 0x5C3A7C4)
    out = bytearray(SCRATCH_SIZE)
    pointers = seed & 1
    for i in range(0, SCRATCH_SIZE, 8):
        v = rng.next()
        if pointers:
            v = (scratch_word_pointer(v >> 32) << 32) | scratch_word_pointer(v & 0xFFFFFFFF)
        out[i:i + 8] = v.to_bytes(8, "big")
    return bytes(out)


def make_cases(toc: int, count: int, base_seed: int) -> list[dict]:
    """Variantes: ponteiros válidos para a área de rascunho, inteiros pequenos, inteiros de 32 bits e
    combinações. Assim funções que recebem ponteiros e funções que recebem números são exercitadas."""
    cases = []
    for k in range(count):
        # bit 0 da semente = modo da área de rascunho (ver scratch_bytes): casos 4-7, 12-15... usam
        # ponteiros, e cada variante de registradores aparece com os dois modos.
        seed = (base_seed * 1000003 + 2 * k + ((k // 4) & 1)) & 0xFFFFFFFF
        rng = XorShift(seed)
        variant = k % 4
        gpr = [rng.next() for _ in range(32)]
        for r in range(3, 11):
            v = rng.next()
            if variant == 0 or (variant == 3 and r == 3):
                gpr[r] = SCRATCH_BASE + (v % (SCRATCH_SIZE // 2)) // 16 * 16
            elif variant == 1:
                gpr[r] = (v % 2001 - 1000) & MASK
            elif variant == 2:
                gpr[r] = (v & 0xFFFFFFFF) if v & 1 else ((v & 0xFFFFFFFF) - (1 << 32)) & MASK
        gpr[1] = STACK_TOP
        gpr[2] = toc
        gpr[13] = TLS_POINTER
        fpr = []
        for i in range(32):
            v = rng.next()
            if 1 <= i <= 8:
                # números "normais": de -1000 a 1000 com frações
                import struct
                fpr.append(int.from_bytes(struct.pack(">d", ((v % 2_000_000) - 1_000_000) / 1000.0), "big"))
            else:
                fpr.append(v & 0x7FEFFFFFFFFFFFFF)  # finito
        cases.append({"id": k, "seed": seed, "gpr": gpr, "fpr": fpr,
                      "cr": rng.next() & 0xFFFFFFFF, "xer": 0, "ctr": rng.next() & 0xFFFFFFFF,
                      "lr": RETURN_SENTINEL})
    return cases


def format_case(c: dict) -> str:
    return (f"case {c['id']} seed {c['seed']:x} gpr " + " ".join(f"{v:x}" for v in c["gpr"]) +
            " fpr " + " ".join(f"{v:x}" for v in c["fpr"]) +
            f" cr {c['cr']:x} xer {c['xer']:x} ctr {c['ctr']:x} lr {c['lr']:x}")


def fnv1a(pairs) -> int:
    """Resumo dos bytes escritos: (endereço, valor final) em ordem de endereço."""
    h = 0xCBF29CE484222325
    for addr, value in pairs:
        for b in addr.to_bytes(8, "big") + bytes([value]):
            h ^= b
            h = (h * 0x100000001B3) & MASK
    return h


def format_result(case_id: int, outcome: dict) -> str:
    if outcome.get("fault"):
        return f"case {case_id} fault {outcome['fault']} {outcome['addr']:x}"
    return (f"case {case_id} ok gpr " + " ".join(f"{v:x}" for v in outcome["gpr"]) +
            " fpr " + " ".join(f"{v:x}" for v in outcome["fpr"]) +
            f" cr {outcome['cr']:x} xer {outcome['xer']:x} ctr {outcome['ctr']:x} lr {outcome['lr']:x}"
            f" mem {outcome['mem_count']} {outcome['mem_hash']:x} first {outcome['mem_first']:x}")
