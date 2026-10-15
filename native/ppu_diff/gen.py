#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Gerador do teste diferencial PPU.

  gen.py mains   --out DIR                 cases_main.c: chama cada função e imprime o resultado
                                            (compilado para PowerPC -> QEMU, e para o host)
  gen.py symbols --elf corpus.elf --out DIR functions.json (para o lifter) e meta.json
                                            (endereço de código e TOC de cada função, lidos da .opd)
  gen.py driver  --meta meta.json --out DIR driver.cpp: chama as funções RECOMPILADAS (func_XXXXXXXX)
                                            com os mesmos argumentos e imprime no mesmo formato

Formato de saída (uma linha por caso):  nome(arg1,arg2)=valor
Inteiros em decimal; float/double como padrão de bits em hexadecimal (comparação exata).
"""

import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cases import CASES, CTYPE, literal, parse  # noqa: E402

CORPUS_FUNCS = [name for name, _sig, _inputs in CASES] + ["helper_square"]


def fmt_value(kind):
    """printf para o valor de retorno; floats viram bits."""
    return {"i": ('"%d"', "{v}"), "u": ('"%u"', "{v}"), "l": ('"%lld"', "(long long){v}"),
            "d": ('"%016llx"', "bits64({v})"), "f": ('"%08x"', "bits32({v})")}[kind]


def arg_text(inp):
    return ",".join(repr(x) if isinstance(x, float) else str(x) for x in inp)


def cmd_mains(out):
    lines = ['#include <stdint.h>', '#include <stdio.h>', '#include <string.h>', '']
    lines.append('static unsigned long long bits64(double d){unsigned long long u; memcpy(&u,&d,8); return u;}')
    lines.append('static unsigned bits32(float f){unsigned u; memcpy(&u,&f,4); return u;}')
    for name, sig, _ in CASES:
        args, ret = parse(sig)
        params = ",".join(CTYPE[a] for a in args)
        lines.append(f"{CTYPE[ret]} {name}({params});")
    lines += ["", "int main(void)", "{"]
    for name, sig, inputs in CASES:
        args, ret = parse(sig)
        fmt, expr = fmt_value(ret)
        for inp in inputs:
            call = f"{name}({','.join(literal(k, v) for k, v in zip(args, inp))})"
            lines.append(f'\tprintf("{name}({arg_text(inp)})=" {fmt} "\\n", {expr.format(v=call)});')
    lines += ["\treturn 0;", "}"]
    with open(os.path.join(out, "cases_main.c"), "w") as f:
        f.write("\n".join(lines) + "\n")


class Elf64BE:
    def __init__(self, path):
        self.data = open(path, "rb").read()
        d = self.data
        if d[:4] != b"\x7fELF" or d[4] != 2 or d[5] != 2:
            raise SystemExit(f"{path}: não é ELF64 big-endian")
        (self.e_shoff,) = struct.unpack_from(">Q", d, 0x28)
        self.e_shentsize, self.e_shnum, self.e_shstrndx = struct.unpack_from(">HHH", d, 0x3A)
        self.sections = []
        for i in range(self.e_shnum):
            o = self.e_shoff + i * self.e_shentsize
            name, stype, flags, addr, off, size, link, info, align, entsize = struct.unpack_from(">IIQQQQIIQQ", d, o)
            self.sections.append(dict(name_off=name, type=stype, addr=addr, off=off, size=size, link=link,
                                      entsize=entsize))
        shstr = self.sections[self.e_shstrndx]
        for s in self.sections:
            s["name"] = self.cstr(shstr["off"] + s["name_off"])

    def cstr(self, off):
        end = self.data.index(b"\0", off)
        return self.data[off:end].decode()

    def section(self, name):
        return next(s for s in self.sections if s["name"] == name)

    def read(self, addr, size):
        for s in self.sections:
            if s["type"] != 8 and s["addr"] <= addr < s["addr"] + s["size"]:
                o = s["off"] + addr - s["addr"]
                return self.data[o:o + size]
        raise KeyError(hex(addr))

    def symbols(self):
        symtab = self.section(".symtab")
        strtab = self.sections[symtab["link"]]
        for i in range(symtab["size"] // 24):
            o = symtab["off"] + i * 24
            name, info, other, shndx, value, size = struct.unpack_from(">IBBHQQ", self.data, o)
            yield self.cstr(strtab["off"] + name), info & 0xF, value, size


def cmd_symbols(elf_path, out):
    elf = Elf64BE(elf_path)
    found = {}
    for name, stype, value, size in elf.symbols():
        if stype == 2 and name in CORPUS_FUNCS:
            # ELFv1 (Linux ppc64): o símbolo aponta para o descritor na .opd {code, toc, env};
            # o toolchain do PS3 usa {u32 code, u32 toc}. Aqui lemos o descritor de 64 bits.
            code, toc = struct.unpack(">QQ", elf.read(value, 16))
            found[name] = {"opd": value, "code": code, "toc": toc, "size": size}
    missing = sorted(set(CORPUS_FUNCS) - set(found))
    if missing:
        raise SystemExit(f"funções não encontradas no ELF: {missing}")
    text = elf.section(".text")
    funcs = [{"start": hex(m["code"]), "end": hex(m["code"] + m["size"])} for m in found.values()]
    json.dump(sorted(funcs, key=lambda f: int(f["start"], 16)), open(os.path.join(out, "functions.json"), "w"), indent=1)
    json.dump({"functions": found, "text_end": text["addr"] + text["size"]},
              open(os.path.join(out, "meta.json"), "w"), indent=1)
    for name in CORPUS_FUNCS:
        m = found[name]
        print(f"{name:14s} código 0x{m['code']:08X}  TOC 0x{m['toc']:08X}  {m['size']} bytes")


def cmd_driver(meta_path, out):
    meta = json.load(open(meta_path))["functions"]
    lines = ['#include "ppu_recomp.h"', '#include "guest_runtime.h"', "#include <cstdio>", "#include <cstring>", "",
             "static unsigned long long bits64(double d){unsigned long long u; memcpy(&u,&d,8); return u;}",
             "static unsigned bits32(float f){unsigned u; memcpy(&u,&f,4); return u;}", "",
             "int main(int argc, char** argv)", "{",
             '\tif (argc < 2) { fprintf(stderr, "uso: lifted corpus.elf\\n"); return 2; }',
             "\tif (!guest_load_elf(argv[1])) return 2;"]
    for name, sig, inputs in CASES:
        args, ret = parse(sig)
        m = meta[name]
        fmt, expr = fmt_value(ret)
        for inp in inputs:
            # ABI PowerPC64 ELFv1 (a mesma ideia do PPU): cada argumento ocupa uma posição de GPR
            # (r3, r4...); argumentos float/double vão para f1, f2... e também "gastam" a posição.
            set_regs, fi = [], 1
            for position, (kind, value) in enumerate(zip(args, inp)):
                if kind in "df":
                    set_regs.append(f"ctx.fpr[{fi}] = {literal(kind, value)};")
                    fi += 1
                else:
                    set_regs.append(f"ctx.gpr[{3 + position}] = (uint64_t)(int64_t)({literal(kind, value)});")
            read = {"i": "(int)(int32_t)ctx.gpr[3]", "u": "(unsigned)(uint32_t)ctx.gpr[3]",
                    "l": "(int64_t)ctx.gpr[3]", "d": "(double)ctx.fpr[1]", "f": "(float)ctx.fpr[1]"}[ret]
            lines += ["\t{", "\t\tppu_context ctx; guest_prepare(&ctx, 0x%XULL);" % m["toc"],
                      "\t\t" + " ".join(set_regs),
                      f"\t\tguest_call(&ctx, func_{m['code']:08X});",
                      f'\t\tprintf("{name}({arg_text(inp)})=" {fmt} "\\n", {expr.format(v=read)});', "\t}"]
    lines += ["\treturn guest_failures();", "}"]
    with open(os.path.join(out, "driver.cpp"), "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["mains", "symbols", "driver"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--elf")
    ap.add_argument("--meta")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if a.command == "mains":
        cmd_mains(a.out)
    elif a.command == "symbols":
        cmd_symbols(a.elf, a.out)
    else:
        cmd_driver(a.meta, a.out)


if __name__ == "__main__":
    main()
