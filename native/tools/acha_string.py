"""Endereço (vaddr) de um texto no EBOOT.ELF e as funções recompiladas que montam esse endereço
(lis/addi viram constantes no C). Só leitura local. Uso: acha_string.py EBOOT.ELF <recompiled> texto"""
import re
import struct
import sys
from pathlib import Path

elf = Path(sys.argv[1]).read_bytes()
needle = sys.argv[3].encode() + b"\0"
phoff, = struct.unpack_from(">Q", elf, 0x20)
phentsize, phnum = struct.unpack_from(">HH", elf, 0x36)
hits = []
for i in range(phnum):
    p_type, _f, off, vaddr, _p, filesz = struct.unpack_from(">IIQQQQ", elf, phoff + i * phentsize)
    if p_type != 1:
        continue
    seg = elf[off:off + filesz]
    for m in re.finditer(re.escape(needle), seg):
        hits.append(vaddr + m.start())
print("vaddr:", ", ".join(hex(h) for h in hits))
rx_fn = re.compile(r"^void (func_[0-9A-F]{8})\(ppu_context\* ctx\) \{")
for h in hits:
    hi, lo = (h + 0x8000) >> 16, h & 0xFFFF
    lo_s = lo - 0x10000 if lo >= 0x8000 else lo
    pats = [f"0x{h:X}", f"0x{hi:X} << 16", f"+ (int64_t)({lo_s})", f"(int64_t)(0x{lo:X})"]
    for p in sorted(Path(sys.argv[2]).glob("*.cpp")):
        fn = None
        with open(p, encoding="utf-8", errors="replace") as f:
            for n, ln in enumerate(f):
                m = rx_fn.match(ln)
                if m:
                    fn = m.group(1)
                if f"0x{hi:X} << 16" in ln or f"0x{h:X}" in ln:
                    print(f"  {fn} ({p.name}:{n + 1}): {ln.strip()[:120]}")
