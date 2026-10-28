"""Lista as exportações (biblioteca, NID, OPD, endereço do código) de um PRX PPU já convertido."""
import struct
import sys
from pathlib import Path

buf = Path(sys.argv[1]).read_bytes()
want = {int(x, 16) for x in sys.argv[2:]}
phoff, = struct.unpack_from(">Q", buf, 0x20)
phentsize, phnum = struct.unpack_from(">HH", buf, 0x36)
segs = []
for i in range(phnum):
    p_type, flags, off, vaddr, paddr, filesz, memsz = struct.unpack_from(">IIQQQQQ", buf, phoff + i * phentsize)
    segs.append((p_type, off, vaddr, paddr, filesz))
seg0 = next(s for s in segs if s[0] == 1)


def at(addr):  # endereço do PRX (base 0) -> offset no arquivo
    for t, off, vaddr, _p, fsz in segs:
        if t == 1 and vaddr <= addr < vaddr + fsz:
            return off + addr - vaddr
    raise KeyError(hex(addr))


mi = seg0[3]  # p_paddr do 1º segmento = offset do module_info no arquivo
name = buf[mi + 4:mi + 32].split(b"\0")[0].decode()
toc, exp_s, exp_e = struct.unpack_from(">III", buf, mi + 32)
print(f"módulo {name}  toc=0x{toc:X}")
p = exp_s
while p < exp_e:
    o = at(p)
    size = buf[o]
    nfunc, nvar = struct.unpack_from(">HH", buf, o + 6)
    lname_p, nids_p, addrs_p = struct.unpack_from(">III", buf, o + 0x10)
    lib = buf[at(lname_p):at(lname_p) + 64].split(b"\0")[0].decode() if lname_p else "(module)"
    for k in range(nfunc):
        nid, = struct.unpack_from(">I", buf, at(nids_p + 4 * k))
        opd, = struct.unpack_from(">I", buf, at(addrs_p + 4 * k))
        code, rtoc = struct.unpack_from(">II", buf, at(opd))
        if not want or nid in want:
            print(f"{lib:24s} NID 0x{nid:08X}  opd=0x{opd:X}  code=0x{code:X}  toc=0x{rtoc:X}")
    p += size
