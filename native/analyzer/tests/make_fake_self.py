#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Gera um arquivo com o CABEÇALHO de um SELF de varejo e conteúdo aleatório, para testar que o
analisador reconhece um EBOOT.BIN cifrado e se recusa a analisá-lo. Não há criptografia aqui: os
"segmentos" são bytes aleatórios marcados como cifrados, sem chave nenhuma.

    python make_fake_self.py base.elf saida.BIN
"""

import os
import struct
import sys


def main():
    src, out = sys.argv[1:3]
    elf = open(src, "rb").read()
    phoff, = struct.unpack_from(">Q", elf, 0x20)
    phentsize, phnum = struct.unpack_from(">HH", elf, 0x36)
    phdrs = elf[phoff:phoff + phentsize * phnum]
    ehdr = bytearray(elf[:0x40])
    struct.pack_into(">Q", ehdr, 0x20, 0)  # e_phoff dentro do SELF não é usado aqui
    appinfo_off, elf_off = 0x60, 0x80
    phdr_off = elf_off + 0x40
    seginfo_off = phdr_off + len(phdrs)
    data_off = seginfo_off + 0x20 * phnum
    data_off = (data_off + 0xF) & ~0xF
    seginfo = b""
    payload = b""
    for i in range(phnum):
        size = struct.unpack_from(">Q", phdrs, i * phentsize + 32)[0]
        size = min(size, 0x4000)
        seginfo += struct.pack(">QQIIII", data_off + len(payload), size, 1, 0, 0, 1)  # 1 = cifrado
        payload += os.urandom(size)
    header_len = data_off
    sce = struct.pack(">IIHHIQQ", 0x53434500, 2, 0x001C, 1, 0x200, header_len, len(elf))
    ext = struct.pack(">8Q", 3, appinfo_off, elf_off, phdr_off, 0, seginfo_off, 0, 0)
    app = struct.pack(">QIIQQ", 0x1010000001000003, 0x01000002, 4, 0x0001000000000000, 0)  # 0x20 bytes
    body = sce + ext + app + bytes(ehdr) + phdrs + seginfo
    body += b"\0" * (data_off - len(body))
    open(out, "wb").write(body + payload)
    print(f"{out}: SELF de teste (revisão de chave 0x001C, {phnum} segmentos marcados como cifrados)")


if __name__ == "__main__":
    main()
