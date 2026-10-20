#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Gera um ELF de teste com a FORMA de um EBOOT de PS3 a partir do corpus do projeto.

Um EBOOT de PS3 tem descritores de função (OPD) de 8 bytes {u32 código, u32 TOC} numa seção que
contém o e_entry; o ELF do gcc Linux usa descritores ELFv1 de 24 bytes. Este script copia o
código e os dados do corpus.elf (gerado por native/ppu_diff/run.py) e acrescenta uma tabela OPD
no formato do PS3, para que o analisador seja testado no CI sem nenhum arquivo do jogo.

    python make_ps3_test_elf.py corpus.elf meta.json saida.elf
    python make_ps3_test_elf.py corpus.elf --todas saida.elf   (descritor para TODAS as funções do
        .opd, inclusive a glibc: ~900 funções, para testar a recompilação de poucas funções num
        executável grande, como o do jogo)
"""

import json
import struct
import sys

OPD_BASE = 0x20000000


def all_functions(d: bytes) -> dict:
    """Funções a partir dos descritores ELFv1 (.opd, 24 bytes) que apontam para o .text."""
    shoff, = struct.unpack_from(">Q", d, 0x28)
    shentsize, shnum, shstrndx = struct.unpack_from(">HHH", d, 0x3A)
    secs = [struct.unpack_from(">IIQQQQIIQQ", d, shoff + i * shentsize) for i in range(shnum)]
    stroff = secs[shstrndx][4]

    def name(s):
        return d[stroff + s[0]:d.index(b"\0", stroff + s[0])].decode()

    by = {name(s): s for s in secs}
    opd, text = by[".opd"], by[".text"]
    t_lo, t_hi = text[3], text[3] + text[5]
    codes, toc = set(), None
    for o in range(0, opd[5] - 23, 24):
        code, t, _env = struct.unpack_from(">QQQ", d, opd[4] + o)
        if t_lo <= code < t_hi:
            codes.add(code)
            toc = toc or t
    codes = sorted(codes)
    ends = codes[1:] + [t_hi]
    return {f"f_{c:x}": {"code": c, "size": e - c, "toc": toc} for c, e in zip(codes, ends)}


def main():
    src, meta_path, out_path = sys.argv[1:4]
    d = open(src, "rb").read()
    meta = all_functions(d) if meta_path == "--todas" else json.load(open(meta_path))["functions"]
    phoff, = struct.unpack_from(">Q", d, 0x20)
    phentsize, phnum = struct.unpack_from(">HH", d, 0x36)
    loads = []
    for i in range(phnum):
        p = struct.unpack_from(">IIQQQQQQ", d, phoff + i * phentsize)
        if p[0] == 1:
            loads.append(p)
    # OPD no formato do PS3, na ordem dos endereços de código
    funcs = sorted(meta.values(), key=lambda m: m["code"])
    # Um descritor extra marca o fim do código do corpus: sem ele, a última função "engoliria" o resto
    # do segmento (a libc do gcc). Os segmentos ficam inteiros, com as tabelas e constantes que as
    # funções leem.
    code_hi = max(m["code"] + m["size"] for m in funcs)
    code_hi = (code_hi + 3) & ~3
    opd = b"".join(struct.pack(">II", m["code"], m["toc"]) for m in funcs)
    opd += struct.pack(">II", code_hi, funcs[0]["toc"])
    entry = OPD_BASE  # primeiro descritor
    segments = []  # (p_type, flags, vaddr, data, memsz)
    for p_type, flags, off, vaddr, _pa, filesz, memsz, _al in loads:
        segments.append((1, flags, vaddr, d[off:off + filesz], memsz))
    segments.append((1, 0x6, OPD_BASE, opd, len(opd)))

    shstr = b"\0.text\0.opd\0.shstrtab\0"
    n_ph = len(segments)
    off = 0x40 + 0x38 * n_ph
    body = b""
    placed = []
    for seg in segments:
        pad = (-off - len(body)) % 0x10
        body += b"\0" * pad
        placed.append(off + len(body))
        body += seg[3]
    shstr_off = off + len(body)
    body += shstr
    pad = (-(off + len(body))) % 8
    body += b"\0" * pad
    shoff = off + len(body)

    text_seg = next(i for i, s in enumerate(segments) if s[1] & 1)
    sections = [
        struct.pack(">IIQQQQIIQQ", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        struct.pack(">IIQQQQIIQQ", 1, 1, 0x6, segments[text_seg][2], placed[text_seg], len(segments[text_seg][3]), 0, 0, 4, 0),
        struct.pack(">IIQQQQIIQQ", 7, 1, 0x3, OPD_BASE, placed[-1], len(opd), 0, 0, 8, 0),
        struct.pack(">IIQQQQIIQQ", 12, 3, 0, 0, shstr_off, len(shstr), 0, 0, 1, 0),
    ]
    ehdr = bytearray(0x40)
    ehdr[0:16] = b"\x7fELF\x02\x02\x01\x66" + b"\0" * 8  # OSABI 0x66 = CELL LV2
    struct.pack_into(">HHIQQQIHHHHHH", ehdr, 16, 2, 21, 1, entry, 0x40, shoff, 0, 0x40, 0x38, n_ph, 0x40,
                     len(sections), 3)
    phdrs = b""
    for (p_type, flags, vaddr, data, memsz), offset in zip(segments, placed):
        phdrs += struct.pack(">IIQQQQQQ", p_type, flags, offset, vaddr, vaddr, len(data), memsz, 0x10)
    with open(out_path, "wb") as f:
        f.write(bytes(ehdr) + phdrs + body + b"".join(sections))
    print(f"{out_path}: {len(funcs) + 1} descritores OPD de 8 bytes em 0x{OPD_BASE:X}, {n_ph} segmentos")


if __name__ == "__main__":
    main()
