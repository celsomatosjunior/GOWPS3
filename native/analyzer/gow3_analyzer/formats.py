# SPDX-License-Identifier: GPL-2.0-only
"""Identificação de arquivos do PS3: SELF (EBOOT.BIN, .sprx), ELF e PARAM.SFO.

Só lê campos que o formato guarda em texto aberto. Nunca decifra nada e não contém chaves.
"""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path

SCE_MAGIC = b"SCE\x00"
KEY_REV_DEBUG = 0x8000
PT_NAMES = {1: "LOAD", 4: "NOTE", 7: "TLS", 0x60000001: "PROC_PARAM", 0x60000002: "PROC_PRX_PARAM",
            0x700000A4: "SCE_PPURELA", 0x700000A8: "SCE_SEGSYM"}
SELF_TYPES = {1: "LV0", 2: "LV1", 3: "LV2", 4: "aplicativo", 5: "módulo SPU isolado", 6: "secure loader",
              8: "NPDRM (PSN)"}
MACHINES = {21: "PowerPC 64 (PPU do Cell)", 23: "SPU do Cell"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_sfo(path: Path) -> dict:
    d = Path(path).read_bytes()
    if d[:4] != b"\x00PSF":
        return {}
    key_table, data_table, count = struct.unpack_from("<III", d, 8)
    out = {}
    for i in range(count):
        key_off, fmt, size, _max, data_off = struct.unpack_from("<HHIII", d, 20 + i * 16)
        end = d.index(b"\0", key_table + key_off)
        key = d[key_table + key_off:end].decode("ascii", "replace")
        raw = d[data_table + data_off:data_table + data_off + size]
        out[key] = struct.unpack("<I", raw)[0] if fmt == 0x0404 else raw.split(b"\0")[0].decode("utf-8", "replace")
    return out


def _flags(f):
    return "".join(c for c, bit in (("R", 4), ("W", 2), ("X", 1)) if f & bit)


def elf_header(d: bytes, base: int = 0) -> dict | None:
    if d[base:base + 4] != b"\x7fELF":
        return None
    if d[base + 4] != 2 or d[base + 5] != 2:
        return {"error": "ELF que não é 64 bits big-endian (não é um executável PPU de PS3)"}
    e_type, e_machine = struct.unpack_from(">HH", d, base + 16)
    e_entry, e_phoff, e_shoff = struct.unpack_from(">QQQ", d, base + 24)
    e_phentsize, e_phnum, e_shentsize, e_shnum = struct.unpack_from(">HHHH", d, base + 54)
    return {"type": {2: "EXEC", 3: "DYN (PRX)"}.get(e_type, str(e_type)), "machine": MACHINES.get(e_machine, str(e_machine)),
            "machine_id": e_machine, "osabi": d[base + 7], "entry": e_entry, "phoff": e_phoff, "phnum": e_phnum,
            "phentsize": e_phentsize, "shoff": e_shoff, "shnum": e_shnum, "shentsize": e_shentsize}


def program_headers(d: bytes, phoff: int, phnum: int, phentsize: int = 0x38) -> list[dict]:
    out = []
    for i in range(phnum):
        p_type, p_flags, p_offset, p_vaddr, _pa, p_filesz, p_memsz, _al = struct.unpack_from(">IIQQQQQQ", d, phoff + i * phentsize)
        out.append({"type": PT_NAMES.get(p_type, hex(p_type)), "flags": _flags(p_flags), "offset": p_offset,
                    "vaddr": p_vaddr, "filesz": p_filesz, "memsz": p_memsz})
    return out


def section_headers(d: bytes, hdr: dict) -> list[dict]:
    out = []
    if not hdr.get("shoff") or not hdr.get("shnum"):
        return out
    raw = []
    for i in range(hdr["shnum"]):
        o = hdr["shoff"] + i * hdr["shentsize"]
        if o + 64 > len(d):
            break
        raw.append(struct.unpack_from(">IIQQQQIIQQ", d, o))
    strtab = None
    try:
        e_shstrndx, = struct.unpack_from(">H", d, 62)
        strtab = raw[e_shstrndx][4] if e_shstrndx < len(raw) else None
    except struct.error:
        pass
    for name, stype, flags, addr, off, size, *_ in raw:
        label = ""
        if strtab is not None and strtab + name < len(d):
            end = d.find(b"\0", strtab + name)
            label = d[strtab + name:end].decode("ascii", "replace") if end > 0 else ""
        out.append({"name": label, "type": stype, "addr": addr, "size": size,
                    "exec": bool(flags & 0x4), "alloc": bool(flags & 0x2)})
    return out


def identify(path) -> dict:
    """Formato, cifra, arquitetura, segmentos e se o arquivo está pronto para a análise PPU."""
    path = Path(path)
    d = path.read_bytes()
    info = {"file": str(path), "name": path.name, "size": len(d), "sha256": hashlib.sha256(d).hexdigest()}
    if d[:4] == b"\x7fELF":
        hdr = elf_header(d)
        info["format"] = "ELF"
        info["elf"] = hdr
        if hdr and "error" not in hdr:
            info["segments"] = program_headers(d, hdr["phoff"], hdr["phnum"], hdr["phentsize"])
            info["sections"] = section_headers(d, hdr)
            info["encrypted"] = False
            ok = hdr["machine_id"] == 21
            info["ready"] = ok
            info["status"] = ("ELF PPU sem cifra: pronto para análise." if ok else
                              f"ELF de outra arquitetura ({hdr['machine']}): a análise PPU não se aplica.")
        else:
            info["ready"] = False
            info["status"] = (hdr or {}).get("error", "ELF inválido")
        return info
    if d[:4] != SCE_MAGIC:
        info.update(format="desconhecido", ready=False,
                    status="Não é SELF nem ELF. Escolha o PS3_GAME/USRDIR/EBOOT.BIN ou um EBOOT.ELF.")
        return info
    _magic, version, key_rev, hdr_type, _meta, header_len, elf_size = struct.unpack_from(">IIHHIQQ", d, 0)
    info.update(format="SELF", sce_version=version, key_revision=key_rev, header_type=hdr_type, elf_size=elf_size)
    debug = key_rev == KEY_REV_DEBUG
    if hdr_type == 1:
        _ext, appinfo_off, elf_off, phdr_off, _shdr_off, seginfo_off, _v, _c = struct.unpack_from(">8Q", d, 0x20)
        auth_id, vendor_id, self_type, app_version = struct.unpack_from(">QIIQ", d, appinfo_off)
        info.update(auth_id=hex(auth_id), self_type=SELF_TYPES.get(self_type, hex(self_type)),
                    app_version="%d.%02d" % ((app_version >> 48) & 0xFFFF, (app_version >> 32) & 0xFFFF))
        hdr = elf_header(d, elf_off)
        if hdr and "error" not in hdr:
            info["elf"] = {k: v for k, v in hdr.items() if k in ("type", "machine", "machine_id", "entry", "phnum", "shnum")}
            segs = program_headers(d, phdr_off, hdr["phnum"])
            any_encrypted = False
            for i, s in enumerate(segs):
                _f_off, f_size, compressed, _u1, _u2, encrypted = struct.unpack_from(">QQIIII", d, seginfo_off + i * 0x20)
                s.update(stored_size=f_size, compressed=compressed == 2, encrypted=encrypted == 1)
                any_encrypted |= encrypted == 1
            info["segments"] = segs
            info["segments_marked_encrypted"] = any_encrypted
        # SELF de varejo: o conteúdo dos segmentos é cifrado; só o fSELF de depuração não é.
        info["encrypted"] = not debug
    else:
        info["encrypted"] = not debug
    info["fself_debug"] = debug
    if debug:
        info["ready"] = True
        info["status"] = "fSELF de depuração (sem cifra): será desembrulhado para ELF e analisado."
    else:
        info["ready"] = False
        info["status"] = ("SELF de varejo cifrado (revisão de chave 0x%04X). A análise precisa do EBOOT.ELF, que o "
                          "analisador pede ao RPCS3 instalado no seu computador para gerar a partir da sua cópia. "
                          "Este programa não decifra e não contorna proteções." % key_rev)
    return info
