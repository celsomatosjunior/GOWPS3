"""Resolve RVAs (0x...) do watchdog do GOW3 com o .map do link (lld-link/MSVC /MAP).

    python resolve_map.py GOW3Native.map rodar.log     -> reescreve as linhas [GOW3-WD] com nomes
"""
import bisect
import re
import sys

syms = []
base = 0x140000000
with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
    for ln in f:
        m = re.match(r"\s*Preferred load address is ([0-9a-fA-F]+)", ln)
        if m:
            base = int(m.group(1), 16)
        # lld-link: "Address  Size  Align Out In Symbol" ou MSVC: " 0001:00000000  sym  0000000140001000 f obj"
        m = re.match(r"\s*[0-9a-fA-F]{4}:[0-9a-fA-F]{8}\s+(\S+)\s+([0-9a-fA-F]{16})\s", ln)
        if m:
            syms.append((int(m.group(2), 16) - base, m.group(1)))
syms.sort()
addrs = [a for a, _ in syms]


def name(rva):
    i = bisect.bisect_right(addrs, rva) - 1
    if i < 0:
        return hex(rva)
    a, s = syms[i]
    return f"{s}+0x{rva - a:X}"


print(f"{len(syms)} símbolos", file=sys.stderr)
for ln in open(sys.argv[2], encoding="utf-8", errors="replace"):
    if "[GOW3-WD] tid" not in ln:
        continue
    ln = re.sub(r"GOW3Native\.exe\+0x([0-9A-Fa-f]+)", lambda m: "EXE:" + name(int(m.group(1), 16)), ln)
    head, _, rets = ln.partition("ret:")
    out = [name(int(x, 16)) for x in re.findall(r"0x([0-9A-Fa-f]+)", rets)]
    print(head.strip(), "ret:", " | ".join(out[:8]))
