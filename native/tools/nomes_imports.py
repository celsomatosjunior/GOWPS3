"""Nomes das importações do EBOOT (EBOOT.imports.json do ppu_loader) pelo NID, com o banco do ps3recomp e,
se dado, uma lista extra de nomes (ex.: REG_FUNC do RPCS3). Uso: nomes_imports.py imports.json ps3recomp [biblioteca] [nomes.txt]"""
import json
import sys

sys.path.insert(0, sys.argv[2] + "/tools")
from nid_database import compute_nid  # noqa: E402
import nid_database as d  # noqa: E402

lib = sys.argv[3] if len(sys.argv) > 3 else None
names = set()
for v in vars(d).values():
    if isinstance(v, (list, tuple)):
        for e in v:
            if isinstance(e, tuple) and len(e) == 2 and isinstance(e[1], str):
                names.add(e[1])
if len(sys.argv) > 4:
    names |= set(open(sys.argv[4]).read().split())
by_nid = {compute_nid(n): n for n in names}
for imp in json.load(open(sys.argv[1])):
    if lib and imp["library"] != lib:
        continue
    nid = int(imp["nid"], 16)
    print(f'{imp["library"]:14s} 0x{nid:08X} {by_nid.get(nid, "?")}')
