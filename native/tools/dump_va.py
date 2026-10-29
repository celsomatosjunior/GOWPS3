"""Dump (hex + ASCII) de N bytes no vaddr V do EBOOT.ELF (só leitura local). Uso: dump_va.py EBOOT.ELF 0x588E40 0x80"""
import struct, sys
e = open(sys.argv[1], "rb").read(); va = int(sys.argv[2], 16); n = int(sys.argv[3], 16)
ph, = struct.unpack_from(">Q", e, 0x20); pe, pn = struct.unpack_from(">HH", e, 0x36)
for i in range(pn):
    t, f, o, v, p, fs, ms = struct.unpack_from(">IIQQQQQ", e, ph + i * pe)
    if t == 1 and v <= va < v + ms:
        print(f"segmento vaddr {v:#x} filesz {fs:#x} memsz {ms:#x}")
        for a in range(va, va + n, 16):
            row = bytes(e[o + a - v + k] if a - v + k < fs else 0 for k in range(16))
            print(f"{a:08X}: {row.hex(' ')}  {''.join(chr(c) if 32 <= c < 127 else '.' for c in row)}")
