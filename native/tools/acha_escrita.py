"""Funções recompiladas, numa faixa de endereços, com uma escrita vm_writeN(ctx->gpr[R] + OFF, ...).
Só leitura local (o código é derivado do jogo).
Uso: acha_escrita.py <pasta recompiled> <ini hex> <fim hex> <vm_write8|vm_write32> <OFF ex. 0x1>"""
import re
import sys
from pathlib import Path

lo, hi = int(sys.argv[2], 16), int(sys.argv[3], 16)
fn_w, off = sys.argv[4], sys.argv[5]
rx_fn = re.compile(r"^void func_([0-9A-F]{8})\(ppu_context\* ctx\) \{")
rx_w = re.compile(rf"{fn_w}\(ctx->gpr\[(\d+)\] \+ {re.escape(off)}, ctx->gpr\[(\d+)\]\)")
for p in sorted(Path(sys.argv[1]).glob("*.cpp")):
    cur = None
    prev = []
    with open(p, encoding="utf-8", errors="replace") as f:
        for ln in f:
            m = rx_fn.match(ln)
            if m:
                a = int(m.group(1), 16)
                cur = a if lo <= a < hi else None
                prev = []
                continue
            if cur is None:
                continue
            prev = (prev + [ln.strip()])[-4:]
            w = rx_w.search(ln)
            if w:
                print(f"func_{cur:08X}: {ln.strip()}   <- antes: {' | '.join(prev[:-1])[:200]}")
