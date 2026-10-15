# SPDX-License-Identifier: GPL-2.0-only
"""Gera pastas falsas para os testes. Nenhum arquivo real do jogo é usado ou necessário."""

from __future__ import annotations

import os
import stat
import sys
import textwrap
from pathlib import Path

from gow3ps3 import psf


def make_game(root: Path, serial="BCUS98111", eboot=b"SCE\x00" + b"\x00" * 60, layout="disc",
              system_ver="03.1500") -> Path:
    game_dir = root / "PS3_GAME" if layout == "disc" else root
    (game_dir / "USRDIR").mkdir(parents=True, exist_ok=True)
    (game_dir / "PARAM.SFO").write_bytes(psf.build({
        "TITLE_ID": serial, "TITLE": "GOD OF WAR® III", "CATEGORY": "DG",
        "APP_VER": "01.00", "PS3_SYSTEM_VER": system_ver, "ATTRIBUTE": 0,
    }))
    if eboot is not None:
        (game_dir / "USRDIR" / "EBOOT.BIN").write_bytes(eboot)
    (game_dir / "USRDIR" / "data.psarc").write_bytes(b"conteudo-falso")
    if layout == "disc":
        (root / "PS3_DISC.SFB").write_bytes(b".SFB")
    return root


def make_firmware(emu_dir: Path, version="04.9200") -> None:
    external = emu_dir / "dev_flash" / "sys" / "external"
    external.mkdir(parents=True, exist_ok=True)
    (external / "liblv2.sprx").write_bytes(b"falso")
    etc = emu_dir / "dev_flash" / "vsh" / "etc"
    etc.mkdir(parents=True, exist_ok=True)
    (etc / "version.txt").write_text(f"release:{version}:\nbuild:00000:\n")


def make_fake_rpcs3(folder: Path, record: Path, exit_code=0) -> Path:
    """Um 'rpcs3' de mentira que grava os argumentos e o ambiente que recebeu."""
    folder.mkdir(parents=True, exist_ok=True)
    script = folder / "fake_rpcs3.py"
    script.write_text(textwrap.dedent(f"""
        import json, os, sys
        keys = ("RPCS3_CONFIG_DIR", "XDG_CONFIG_HOME", "XDG_CACHE_HOME")
        json.dump({{"argv": sys.argv[1:], "cwd": os.getcwd(),
                   "env": {{k: os.environ.get(k) for k in keys}}}}, open({str(record)!r}, "w"))
        sys.exit({exit_code})
    """))
    executable = folder / "rpcs3"
    executable.write_text(f"#!/bin/sh\nexec {sys.executable} {script} \"$@\"\n")
    executable.chmod(executable.stat().st_mode | stat.S_IEXEC)
    return executable
