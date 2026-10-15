# SPDX-License-Identifier: GPL-2.0-only
"""Leitor e gravador do formato PSF (PARAM.SFO) do PS3.

Layout (little-endian), o mesmo que o RPCS3 lê em rpcs3/Loader/PSF.cpp:
  header (20 bytes): magic "\\0PSF", version u32, key_table u32, data_table u32, count u32
  entrada (16 bytes): key_off u16, fmt u16, size u32, max_size u32, data_off u32
Formatos: 0x0004 string especial, 0x0204 string UTF-8, 0x0404 inteiro u32.
"""

from __future__ import annotations

import struct

MAGIC = b"\x00PSF"
FMT_STRING_SPECIAL = 0x0004
FMT_STRING = 0x0204
FMT_INTEGER = 0x0404


class PsfError(ValueError):
    pass


def parse(data: bytes) -> dict[str, str | int]:
    if len(data) < 20 or data[:4] != MAGIC:
        raise PsfError("não é um arquivo PARAM.SFO (assinatura PSF ausente)")
    _version, key_table, data_table, count = struct.unpack_from("<IIII", data, 4)
    if 20 + count * 16 > len(data) or key_table > len(data) or data_table > len(data):
        raise PsfError("PARAM.SFO truncado ou corrompido")

    result: dict[str, str | int] = {}
    for i in range(count):
        key_off, fmt, size, max_size, data_off = struct.unpack_from("<HHIII", data, 20 + i * 16)
        key_start = key_table + key_off
        key_end = data.find(b"\x00", key_start)
        if key_end < 0:
            raise PsfError("tabela de chaves corrompida")
        key = data[key_start:key_end].decode("ascii", "replace")
        start = data_table + data_off
        if start + max(size, 0) > len(data) or size > max_size:
            raise PsfError(f"valor de {key} fora dos limites do arquivo")
        raw = data[start:start + size]
        if fmt == FMT_INTEGER:
            if size != 4:
                raise PsfError(f"inteiro {key} com tamanho {size}")
            result[key] = struct.unpack("<I", raw)[0]
        elif fmt in (FMT_STRING, FMT_STRING_SPECIAL):
            result[key] = raw.split(b"\x00", 1)[0].decode("utf-8", "replace")
        else:
            raise PsfError(f"formato desconhecido 0x{fmt:04x} em {key}")
    return result


def load(path) -> dict[str, str | int]:
    with open(path, "rb") as stream:
        return parse(stream.read())


def build(entries: dict[str, str | int]) -> bytes:
    """Gera um PARAM.SFO (usado nos testes; o launcher nunca grava nos arquivos do jogo)."""
    keys = sorted(entries)
    key_blob = b""
    key_offsets = []
    for key in keys:
        key_offsets.append(len(key_blob))
        key_blob += key.encode("ascii") + b"\x00"
    while len(key_blob) % 4:
        key_blob += b"\x00"

    data_blob = b""
    table = b""
    for key, key_off in zip(keys, key_offsets):
        value = entries[key]
        if isinstance(value, int):
            raw, fmt = struct.pack("<I", value), FMT_INTEGER
            size = max_size = 4
        else:
            raw = value.encode("utf-8") + b"\x00"
            fmt, size = FMT_STRING, len(raw)
            max_size = (size + 3) & ~3
            raw = raw.ljust(max_size, b"\x00")
        table += struct.pack("<HHIII", key_off, fmt, size, max_size, len(data_blob))
        data_blob += raw

    key_table = 20 + len(table)
    data_table = key_table + len(key_blob)
    header = MAGIC + struct.pack("<IIII", 0x0101, key_table, data_table, len(keys))
    return header + table + key_blob + data_blob
