"""Mostra, no código recompilado, as linhas antes de um endereço de retorno (lr) do PS3: a chamada que
a thread está fazendo. Só leitura local. Uso: contexto_lr.py <pasta recompiled> 0x266D74 [0x... ...]"""
import re
import sys
from pathlib import Path

targets = {int(a, 16) for a in sys.argv[2:]}
rx_fn = re.compile(r"^void (func_[0-9A-F]{8})\(ppu_context\* ctx\) \{")
for p in sorted(Path(sys.argv[1]).glob("*.cpp")):
    fn, buf = None, []
    with open(p, encoding="utf-8", errors="replace") as f:
        for ln in f:
            m = rx_fn.match(ln)
            if m:
                fn, buf = m.group(1), []
                continue
            buf = (buf + [ln.rstrip()])[-14:]
            for t in list(targets):
                if f"ctx->lr = 0x{t:08X};" in ln:
                    print(f"=== lr 0x{t:08X} em {fn}")
                    print("\n".join(buf))
                    targets.discard(t)
    if not targets:
        break
for t in targets:
    print(f"(0x{t:08X} não achado como endereço de retorno)")
