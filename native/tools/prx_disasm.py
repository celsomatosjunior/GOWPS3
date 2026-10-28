"""Desmonta trechos de um PRX PPU convertido (capstone, PPC64 big-endian). Uso: prx_disasm.py PRX ini fim [ini fim ...]"""
import struct
import sys
from pathlib import Path

import capstone

buf = Path(sys.argv[1]).read_bytes()
phoff, = struct.unpack_from(">Q", buf, 0x20)
phentsize, phnum = struct.unpack_from(">HH", buf, 0x36)
segs = [struct.unpack_from(">IIQQQQQ", buf, phoff + i * phentsize) for i in range(phnum)]


def at(addr):
    for t, _f, off, vaddr, _p, fsz, _m in segs:
        if t == 1 and vaddr <= addr < vaddr + fsz:
            return off + addr - vaddr
    raise KeyError(hex(addr))


md = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
args = [int(a, 16) for a in sys.argv[2:]]
for lo, hi in zip(args[::2], args[1::2]):
    print(f"--- 0x{lo:X}..0x{hi:X}")
    code = buf[at(lo):at(lo) + (hi - lo)]
    for ins in md.disasm(code, lo):
        print(f"{ins.address:06X}: {ins.mnemonic:8s} {ins.op_str}")
