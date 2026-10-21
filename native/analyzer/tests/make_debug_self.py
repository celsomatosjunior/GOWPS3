#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""SELF de depuração ("fake signed", se_flags 0x8000) no layout do make_fself: cabeçalho SCE,
cabeçalho estendido, app info, cópia do cabeçalho ELF e dos program headers, informação de
segmentos (sem compressão, sem cifra), cabeçalho de versão e, a partir de se_hsize, o ELF inteiro.

É o formato que o RPCS3 converte sem chave nenhuma (Crypto/unself.cpp: LoadMetadata sintetiza os
metadados a partir das informações de segmento; MakeElf copia também os bytes fora dos segmentos).
Serve para testar no CI a chamada `rpcs3 --decrypt` de verdade, sem arquivo do jogo.

    python make_debug_self.py entrada.elf saida.BIN
"""
import struct
import sys


def align(v, a):
    return (v + a - 1) // a * a


def main():
    src, out = sys.argv[1:3]
    elf = open(src, "rb").read()
    assert elf[:4] == b"\x7fELF" and elf[4] == 2 and elf[5] == 2, "esperado ELF64 big-endian"
    e_phoff, e_shoff = struct.unpack_from(">QQ", elf, 0x20)
    e_ehsize, e_phentsize, e_phnum = struct.unpack_from(">HHH", elf, 0x34)
    phdrs = [struct.unpack_from(">IIQQQQQQ", elf, e_phoff + i * e_phentsize) for i in range(e_phnum)]

    off_ext = 0x20
    off_app = off_ext + 0x50
    off_ehdr = off_app + 0x20
    off_phdr = off_ehdr + e_ehsize
    off_seg = align(off_phdr + e_phnum * e_phentsize, 0x10)
    off_ver = off_seg + e_phnum * 0x20
    off_sup = off_ver + 0x10
    hsize = align(off_sup, 0x100)

    h = bytearray(hsize)
    struct.pack_into(">IIHHIQQ", h, 0, 0x53434500, 2, 0x8000, 1, 0, hsize, len(elf))
    struct.pack_into(">10Q", h, off_ext, 3, off_app, off_ehdr, off_phdr,
                     hsize + e_shoff if e_shoff else 0, off_seg, off_ver, off_sup, 0, 0)
    # app info: autoridade/fornecedor genéricos de aplicativo, tipo 4 (aplicativo), versão 01.00
    struct.pack_into(">QIIQQ", h, off_app, 0x1010000001000003, 0x01000002, 4, 0x0001000000000000, 0)
    h[off_ehdr:off_ehdr + e_ehsize] = elf[:e_ehsize]
    h[off_phdr:off_phdr + e_phnum * e_phentsize] = elf[e_phoff:e_phoff + e_phnum * e_phentsize]
    for i, p in enumerate(phdrs):
        p_offset, p_filesz = p[2], p[5]
        struct.pack_into(">QQIIQ", h, off_seg + i * 0x20, hsize + p_offset, p_filesz, 1, 0, 0)
    struct.pack_into(">IIII", h, off_ver, 1, 0, 0x10, 0)
    open(out, "wb").write(bytes(h) + elf)
    print(f"{out}: SELF de depuração, cabeçalho de 0x{hsize:X} bytes, {e_phnum} segmentos, ELF de {len(elf)} bytes")


if __name__ == "__main__":
    main()
