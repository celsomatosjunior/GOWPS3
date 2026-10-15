#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Cria uma pasta FALSA com a estrutura de um disco de PS3 (para testar o reconhecimento do jogo).
Não contém nada do jogo real: PARAM.SFO gerado aqui e um EBOOT.BIN de 64 bytes vazios com o cabeçalho SELF."""
import struct, sys
from pathlib import Path

def build_sfo(entries):
    keys = sorted(entries)
    key_blob, offsets = b"", []
    for k in keys:
        offsets.append(len(key_blob)); key_blob += k.encode() + b"\0"
    key_blob += b"\0" * (-len(key_blob) % 4)
    table, data = b"", b""
    for k, off in zip(keys, offsets):
        v = entries[k]
        if isinstance(v, int):
            raw, fmt, size, maxs = struct.pack("<I", v), 0x0404, 4, 4
        else:
            raw = v.encode() + b"\0"; size = len(raw); maxs = (size + 3) & ~3; raw = raw.ljust(maxs, b"\0"); fmt = 0x0204
        table += struct.pack("<HHIII", off, fmt, size, maxs, len(data)); data += raw
    kt = 20 + len(table)
    return b"\0PSF" + struct.pack("<IIII", 0x101, kt, kt + len(key_blob), len(keys)) + table + key_blob + data

root = Path(sys.argv[1]); serial = sys.argv[2] if len(sys.argv) > 2 else "BCES00510"
game = root / "PS3_GAME"; (game / "USRDIR").mkdir(parents=True, exist_ok=True)
(game / "PARAM.SFO").write_bytes(build_sfo({"TITLE_ID": serial, "TITLE": "GOD OF WAR III (TESTE)", "CATEGORY": "DG",
                                            "APP_VER": "01.00", "PS3_SYSTEM_VER": "03.1500", "ATTRIBUTE": 0}))
(game / "USRDIR" / "EBOOT.BIN").write_bytes(b"SCE\0" + b"\0" * 60)
(root / "PS3_DISC.SFB").write_bytes(b".SFB")
print(root)
