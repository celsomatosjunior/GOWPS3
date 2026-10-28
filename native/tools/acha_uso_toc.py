"""Funções recompiladas que leem um slot da TOC (gpr[2] + OFF) e o que fazem com ele (só leitura local,
o código é derivado do jogo). Uso: acha_uso_toc.py <pasta recompiled> -0x6C2C"""
import re
import sys
from pathlib import Path

off = sys.argv[2]
rx_fn = re.compile(r"^void (func_[0-9A-F]{8})\(ppu_context\* ctx\) \{")
pat = f"vm_read32(ctx->gpr[2] + {off})"
for p in sorted(Path(sys.argv[1]).glob("*.cpp")):
    cur, lines = None, []
    with open(p, encoding="utf-8", errors="replace") as f:
        for ln in f:
            m = rx_fn.match(ln)
            if m:
                if cur and any(pat in x for x in lines):
                    hits = [x.strip() for x in lines if pat in x]
                    writes = [x.strip() for x in lines if "vm_write32(" in x and "+ 0x0," in x]
                    print(f"{cur}: {len(lines)} linhas; carrega o slot {len(hits)}x; vm_write32(...+0x0) {len(writes)}x")
                cur, lines = m.group(1), []
            elif cur:
                lines.append(ln)
