"""Fecho de chamadas de funções lifted de um PRX: TODOs, chamadas HLE e syscalls em cada uma.

    python fecho_lle.py ppu_recomp.c PREFIXO ADDR [ADDR ...]
"""
import re
import sys

src = open(sys.argv[1], encoding="utf-8", errors="replace").read()
prefix = sys.argv[2]
funcs = {m.group(1): m.start() for m in re.finditer(rf"^void {prefix}func_([0-9A-F]{{8}})\(ppu_context\* ctx\) \{{", src, re.M)}
order = sorted(funcs.items(), key=lambda kv: kv[1])
bodies = {n: src[s:(order[i + 1][1] if i + 1 < len(order) else len(src))] for i, (n, s) in enumerate(order)}
seen, stack = set(), [a.upper().replace("0X", "") for a in sys.argv[3:]]
while stack:
    f = stack.pop()
    if f in seen or f not in bodies:
        continue
    seen.add(f)
    stack += re.findall(rf"{prefix}func_([0-9A-F]{{8}})\(ctx\)", bodies[f])
print("fecho:", len(seen), "funções")
for f in sorted(seen):
    b = bodies[f]
    todos = re.findall(r"/\* TODO:?\s*([^*]*)\*/", b)
    hle = sorted(set(re.findall(r"ps3_hle_call\(ctx,\s*(0x[0-9A-Fa-f]+)", b)))
    sc = len(re.findall(r"\bsc\b|syscall", b))
    ind = len(re.findall(r"ps3_indirect_call", b))
    print(f"{f}: {len(b):6d} B  TODO={len(todos)} {todos[:3]}  hle={hle}  syscall={sc}  indirect={ind}")
