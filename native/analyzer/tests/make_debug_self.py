#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""SELF de depuração (revisão de chave 0x8000) com o ELF inteiro depois do cabeçalho: o formato que
o RPCS3 converte sem chave nenhuma (Crypto/unself.cpp, CheckDebugSelf). Serve para testar no CI a
chamada `rpcs3 --decrypt` de verdade, sem arquivo do jogo.

    python make_debug_self.py entrada.elf saida.BIN
"""
import struct
import sys


def main():
    src, out = sys.argv[1:3]
    elf = open(src, "rb").read()
    header_len = 0x80
    hdr = struct.pack(">IIHHIQQ", 0x53434500, 2, 0x8000, 1, 0, header_len, len(elf))
    hdr += b"\0" * (header_len - len(hdr))
    open(out, "wb").write(hdr + elf)
    print(f"{out}: SELF de depuração com {len(elf)} bytes de ELF em 0x{header_len:X}")


if __name__ == "__main__":
    main()
