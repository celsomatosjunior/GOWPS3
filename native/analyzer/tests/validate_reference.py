#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Valida o executor de referência (Unicorn) contra o QEMU nos casos do corpus.

O corpus.elf e o ref_qemu.txt vêm do job ppu_diff_generate (gcc PowerPC + qemu-ppc64). Se o
Unicorn reproduzir os mesmos 97 resultados, ele serve de referência para o teste das candidatas.

    python validate_reference.py corpus.elf meta.json ref_qemu.txt [saida.txt]
"""

import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "ppu_diff"))

from cases import CASES, parse  # noqa: E402
from gow3_analyzer import state as S  # noqa: E402
from gow3_analyzer.analysis import ElfImage  # noqa: E402
from gow3_analyzer.reference import Reference  # noqa: E402


def dbits(x):
    return int.from_bytes(struct.pack(">d", float(x)), "big")


def main():
    elf, meta_path, ref_path = sys.argv[1:4]
    out_path = sys.argv[4] if len(sys.argv) > 4 else None
    meta = json.load(open(meta_path))["functions"]
    ref = Reference(ElfImage(elf))
    lines = []
    for name, sig, inputs in CASES:
        args, ret = parse(sig)
        m = meta[name]
        for inp in inputs:
            case = {"seed": 0, "gpr": [0] * 32, "fpr": [0] * 32, "cr": 0, "xer": 0, "ctr": 0, "lr": S.RETURN_SENTINEL}
            case["gpr"][1], case["gpr"][2] = S.STACK_TOP, m["toc"]
            fi = 1
            for position, (kind, value) in enumerate(zip(args, inp)):
                if kind in "df":
                    case["fpr"][fi] = dbits(value)
                    fi += 1
                else:
                    case["gpr"][3 + position] = int(value) & S.MASK
            # reset=False: um "processo" só, como o main do QEMU (variáveis globais persistem)
            r = ref.run(m["code"], case, code_end=m["code"] + m["size"], reset=False)
            text = ",".join(repr(x) if isinstance(x, float) else str(x) for x in inp)
            if r.get("fault"):
                lines.append(f"{name}({text})=FALHA {r['fault']} {r['addr']:x}")
                continue
            g3, f1 = r["gpr"][3], r["fpr"][1]
            if ret == "i":
                v = struct.unpack(">i", struct.pack(">I", g3 & 0xFFFFFFFF))[0]
            elif ret == "u":
                v = g3 & 0xFFFFFFFF
            elif ret == "l":
                v = struct.unpack(">q", struct.pack(">Q", g3))[0]
            elif ret == "d":
                v = f"{f1:016x}"
            else:
                d = struct.unpack(">d", f1.to_bytes(8, "big"))[0]
                v = f"{int.from_bytes(struct.pack('>f', d), 'big'):08x}"
            lines.append(f"{name}({text})={v}")
    expected = [ln.rstrip("\n") for ln in open(ref_path) if ln.strip()]
    same = sum(a == b for a, b in zip(lines, expected))
    if out_path:
        open(out_path, "w").write("\n".join(lines) + "\n")
    for a, b in zip(lines, expected):
        if a != b:
            print(f"DIVERGE unicorn: {a}   qemu: {b}")
    total = max(len(lines), len(expected))
    print(f"Unicorn x QEMU: {same}/{total} idênticos")
    return 0 if same == total else 1


if __name__ == "__main__":
    sys.exit(main())
