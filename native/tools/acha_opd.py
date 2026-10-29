"""Acha o OPD {code, toc} de uma função no EBOOT.ELF e onde o endereço do OPD aparece (dados e TOC).
Só leitura local. Uso: acha_opd.py EBOOT.ELF 0x1E51AC"""
import struct, sys
e = open(sys.argv[1], "rb").read()
code = int(sys.argv[2], 16)
ph, = struct.unpack_from(">Q", e, 0x20); pe, pn = struct.unpack_from(">HH", e, 0x36)
segs = [struct.unpack_from(">IIQQQQ", e, ph + i * pe) for i in range(pn)]
def scan(val):
    out = []
    for t, f, o, v, p, fs in segs:
        if t != 1: continue
        b = struct.pack(">I", val)
        i = e.find(b, o, o + fs)
        while i != -1:
            if (i - o) % 4 == 0: out.append(v + i - o)
            i = e.find(b, i + 1, o + fs)
    return out
opds = [a for a in scan(code) if struct.unpack_from(">I", e, a - [v for t,f,o,v,p,fs in segs if t==1 and v<=a<v+fs][0] + [o for t,f,o,v,p,fs in segs if t==1 and v<=a<v+fs][0] + 4)[0] == 0x52D6C8]
print("OPDs:", [hex(a) for a in opds])
for a in opds:
    refs = scan(a)
    print(f"  OPD {a:#x} citado em: {[hex(r) for r in refs]}  (TOC off: {[hex(r-0x52D6C8) for r in refs]})")
