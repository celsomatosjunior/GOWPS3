#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Guarda contra dados do jogo no repositório.

Percorre os arquivos versionados (git ls-files) e falha se encontrar qualquer coisa que possa ser
conteúdo do God of War III ou derivado direto dele: executáveis PS3 (SELF "SCE\\0", ELF PowerPC64 ou
SPU), pacotes/arquivos do jogo (.psarc, .pkg, .edat, .sdat, .sprx...), código gerado pelo lifter a
partir do jogo (ppu_recomp.c, pastas lifted/) ou arquivos binários grandes. Roda no CI a cada push.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

EXT_PROIBIDAS = {".self", ".sprx", ".prx", ".psarc", ".pkg", ".edat", ".sdat", ".pam", ".pup",
                 ".rap", ".ird", ".iso", ".elf", ".bin", ".sfo", ".trp", ".pak", ".wad", ".at3"}
NOMES_PROIBIDOS = {"eboot.bin", "eboot.elf", "param.sfo", "ppu_recomp.c", "ppu_recomp.h", "ppu_main.c",
                   "relatorio_gow3.json", "relatorio_gow3.html", "analise.log", "rpcs3_conversao.log"}
PASTAS_PROIBIDAS = {"lifted", "ps3_game", "usrdir", "dev_hdd0", "dev_flash"}
LIMITE = 8 * 1024 * 1024  # nenhum arquivo do projeto chega perto disso


def motivo(path: Path, rel: str) -> str | None:
    low = rel.lower()
    partes = low.split("/")
    if partes[-1] in NOMES_PROIBIDOS:
        return "nome de arquivo do jogo ou de saída do analisador"
    if any(p in PASTAS_PROIBIDAS for p in partes[:-1]):
        return "pasta de dados do jogo ou de código gerado"
    if path.suffix.lower() in EXT_PROIBIDAS:
        return f"extensão {path.suffix.lower()}"
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            head = f.read(64)
    except OSError:
        return None
    if head[:4] == b"SCE\0":
        return "cabeçalho SELF/SCE"
    if head[:4] == b"\x7fELF" and len(head) >= 20:
        machine = int.from_bytes(head[18:20], "big" if head[5] == 2 else "little")
        if machine in (21, 23):
            return f"ELF de PS3 (e_machine {machine})"
    if head[:4] == b"PSAR":
        return "arquivo PSARC"
    if head[:4] == b"\x7fPKG":
        return "pacote PKG"
    if size > LIMITE:
        return f"arquivo grande ({size // 1024 // 1024} MB)"
    return None


def main() -> int:
    root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    files = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"]).decode().split("\0")
    ruins = [(rel, m) for rel in files if rel and (m := motivo(root / rel, rel))]
    for rel, m in ruins:
        print(f"PROIBIDO: {rel}: {m}")
    if ruins:
        print(f"{len(ruins)} arquivo(s) parecem dados do jogo; remova-os do repositório.")
        return 1
    print(f"OK: {len(files) - 1} arquivos versionados, nenhum dado do jogo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
