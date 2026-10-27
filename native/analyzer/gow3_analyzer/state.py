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


MODES = ("aleatória", "só ponteiros", "mista", "mista")


def mixed_word(h: int) -> int:
    """Palavra de 32 bits "realista": metade ponteiros válidos (para a 1ª metade da área de rascunho,
    deixando espaço para deslocamentos), um quarto números pequenos (índices, contadores) e um quarto
    floats pequenos. Funções que seguem um ponteiro e usam o valor lido como índice executam."""
    sel, v = h & 3, h >> 2
    if sel < 2:
        return SCRATCH_BASE + (v % (SCRATCH_SIZE // 2)) // 16 * 16
    if sel == 2:
        return v % 16
    import struct
    return int.from_bytes(struct.pack(">f", (v % 17 - 8) / 2.0), "big")


def word_for(mode: int, h: int) -> int:
    return scratch_word_pointer(h) if mode == 1 else mixed_word(h)


def scratch_bytes(seed: int) -> bytes:
    """Modo = 2 bits baixos da semente. 0: bytes aleatórios; 1: cada palavra de 32 bits é um ponteiro
    válido para a própria área (os ponteiros do PS3 são de 32 bits); 2 e 3: palavras mistas
    (mixed_word)."""
    rng = XorShift(seed ^ 0x5C3A7C4)
    out = bytearray(SCRATCH_SIZE)
    mode = seed & 3
    for i in range(0, SCRATCH_SIZE, 8):
        v = rng.next()
        if mode:
            v = (word_for(mode, v >> 32) << 32) | word_for(mode, v & 0xFFFFFFFF)
        out[i:i + 8] = v.to_bytes(8, "big")
    return bytes(out)


def bss_word(addr: int, mode: int) -> int:
    """Conteúdo sintético da área .bss (variáveis globais que o jogo só preenche em execução) nos
    modos 1-3; no modo 0 ela fica zerada, como na imagem do ELF. Depende só do endereço e do modo."""
    if mode == 0:
        return 0
    h = XorShift((addr & ~3) ^ (mode << 40)).next() & 0xFFFFFFFF
    return word_for(mode, h)


def bss_bytes(lo: int, hi: int, mode: int) -> bytes:
    """Bytes de [lo, hi) da .bss no modo dado (lo e hi quaisquer; palavras alinhadas a 4)."""
    out = bytearray()
    a = lo & ~3
    while a < hi:
        out += bss_word(a, mode).to_bytes(4, "big")
        a += 4
    return bytes(out[lo - (lo & ~3):lo - (lo & ~3) + (hi - lo)])


def make_cases(toc: int, count: int, base_seed: int) -> list[dict]:
    """Variantes: ponteiros válidos para a área de rascunho, inteiros pequenos, inteiros de 32 bits e
    combinações. Assim funções que recebem ponteiros e funções que recebem números são exercitadas."""
    cases = []
    for k in range(count):
        # 2 bits baixos da semente = modo da memória (scratch_bytes/bss_word): casos 0-3 aleatória,
        # 4-7 só ponteiros, 8-15 mista; cada variante de registradores aparece em todos os modos
        mode = (k // 4) % 4
        seed = ((base_seed * 1000003 + k) * 4 + mode) & 0xFFFFFFFF
        rng = XorShift(seed)
        variant = k % 4
        gpr = [rng.next() for _ in range(32)]
        for r in range(3, 11):
            v = rng.next()
            if variant == 0 or (variant == 3 and r == 3):
                gpr[r] = SCRATCH_BASE + (v % (SCRATCH_SIZE // 2)) // 16 * 16
                if (k // 16) % 2:
                    # ponteiro com os 32 bits de cima preenchidos (como um estendido com sinal): no PS3
                    # o endereço efetivo é de 32 bits, então acessa a mesma memória (ver guestmem.py)
                    gpr[r] |= 0xFFFFFFFF00000000
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
    line = (f"case {c['id']} seed {c['seed']:x} gpr " + " ".join(f"{v:x}" for v in c["gpr"]) +
            " fpr " + " ".join(f"{v:x}" for v in c["fpr"]) +
            f" cr {c['cr']:x} xer {c['xer']:x} ctr {c['ctr']:x} lr {c['lr']:x}")
    if c.get("pages"):
        line += f" pages {len(c['pages'])} " + " ".join(f"{a:x}:{d.hex()}" for a, d in sorted(c["pages"].items()))
    return line


def real_case(n: int, captured: dict) -> dict | None:
    """Caso de teste a partir de um estado capturado do jogo (capture.py). Retorno vai para a
    sentinela; XER entra zerado (o servidor GDB do RPCS3 não o informa), igual nos dois lados."""
    pages = {int(a, 16): bytes.fromhex(d) for a, d in captured["pages"].items()}
    if any(a <= RETURN_SENTINEL < a + 0x1000 for a in pages):
        return None  # página do jogo coincide com a sentinela de retorno do teste
    return {"id": f"r{n}", "seed": 0, "real": True, "gpr": list(captured["gpr"]), "fpr": list(captured["fpr"]),
            "cr": captured["cr"], "xer": 0, "ctr": captured["ctr"], "lr": RETURN_SENTINEL, "pages": pages}


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
