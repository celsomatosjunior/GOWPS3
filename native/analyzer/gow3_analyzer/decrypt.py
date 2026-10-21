# SPDX-License-Identifier: GPL-2.0-only
"""Gera o EBOOT.ELF a partir do EBOOT.BIN usando o RPCS3 instalado no computador do usuário.

Este programa não decifra nada e não contém chaves: quem converte é o próprio RPCS3 do usuário
(`rpcs3 --no-gui --decrypt <arquivo>`, a mesma função de "Utilities > Decrypt PS3 Binaries"), sobre
a cópia do jogo do usuário. O EBOOT.BIN original não é alterado: o RPCS3 trabalha numa cópia dentro
da pasta de trabalho do analisador.
"""

from __future__ import annotations

import json
import os
import shutil
import string
import subprocess
import sys
from pathlib import Path

from . import formats

# Versões conferidas (SHA-256). O EBOOT.ELF é o que o RPCS3 gera a partir do EBOOT.BIN.
KNOWN = {
    "49e894c2c9ca9d87824292a93eded16b733bdaf0eef4d28918483007f9bc35b0": {
        "title": "God of War III", "title_id": "BCES00510", "version": "01.00",
        "elf_sha256": "931ccd9bb11014efd2ef6b3dc51f421a029f9256da6b9de6b8cf2fdbb948b2ae",
    },
}

TIMEOUT = 300


class DecryptError(RuntimeError):
    pass


def settings_path() -> Path:
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()
    return base / "configuracoes.json"


def load_settings() -> dict:
    try:
        return json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(data: dict) -> None:
    try:
        cur = load_settings()
        cur.update(data)
        settings_path().write_text(json.dumps(cur, indent=1, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _exe_name() -> str:
    return "rpcs3.exe" if os.name == "nt" else "rpcs3"


def _valid(p: Path | None) -> bool:
    return bool(p) and p.is_file() and p.name.lower() in ("rpcs3.exe", "rpcs3", "rpcs3.appimage")


def candidates() -> list[Path]:
    """Lugares comuns de instalação do RPCS3 e o RPCS3 do pacote GOW3_PS3_PC."""
    out: list[Path] = []
    exe = _exe_name()
    env = os.environ.get("GOW3_RPCS3")
    if env:
        out.append(Path(env))
    here = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()
    # pacote GOW3_PS3_PC (o primeiro programa do projeto) ao lado do analisador
    for root in (here, here.parent, here.parent.parent):
        try:
            for d in root.iterdir():
                if d.is_dir() and d.name.upper().startswith("GOW3_PS3_PC"):
                    out += [d / "runtime" / "rpcs3" / exe, d / "GOW3_PS3_PC" / "runtime" / "rpcs3" / exe]
        except OSError:
            pass
    home = Path.home()
    for base in (home, home / "Desktop", home / "Downloads", home / "Documents",
                 Path(os.environ.get("LOCALAPPDATA", home)), Path(os.environ.get("ProgramFiles", "C:/Program Files"))):
        out += [base / "RPCS3" / exe, base / "rpcs3" / exe]
    if os.name == "nt":  # pastas na raiz de cada disco com "rpcs3" no nome (até dois níveis)
        for letter in string.ascii_uppercase:
            root = Path(f"{letter}:/")
            try:
                if not root.exists():
                    continue
                for d in root.iterdir():
                    if not d.is_dir():
                        continue
                    if "rpcs3" in d.name.lower():
                        out.append(d / exe)
                    elif d.name.lower() in ("games", "jogos", "emuladores", "emulators", "emulador"):
                        for sub in d.iterdir():
                            if sub.is_dir() and "rpcs3" in sub.name.lower():
                                out.append(sub / exe)
            except OSError:
                continue
    found = shutil.which("rpcs3")
    if found:
        out.append(Path(found))
    return out


def find_rpcs3(hint: str | os.PathLike | None = None) -> Path | None:
    for p in ([Path(hint)] if hint else []) + ([Path(load_settings()["rpcs3"])] if load_settings().get("rpcs3") else []) + candidates():
        if p.is_dir():
            p = p / _exe_name()
        if _valid(p):
            return p.resolve()
    return None


def decrypt_with_rpcs3(self_path: Path, rpcs3: Path, work: Path, progress=lambda m: None) -> Path:
    """Copia o SELF para a pasta de trabalho, pede ao RPCS3 para convertê-lo e devolve o ELF."""
    # caminhos absolutos: o RPCS3 roda com a pasta dele como pasta de trabalho
    self_path, rpcs3, work = Path(self_path).resolve(), Path(rpcs3).resolve(), Path(work).resolve()
    dst_dir = work / "rpcs3_conversao"
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    dst_dir.mkdir(parents=True)
    copy = dst_dir / self_path.name
    shutil.copy2(self_path, copy)
    out_elf = copy.with_suffix(".elf")
    progress(f"Gerando o EBOOT.ELF com o seu RPCS3 ({rpcs3})...")
    cmd = [str(rpcs3), "--no-gui", "--decrypt", str(copy)]
    try:
        proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=TIMEOUT, cwd=str(rpcs3.parent),
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        log = f"$ {' '.join(cmd)}\n(código {proc.returncode})\n{proc.stdout}\n{proc.stderr}"
    except subprocess.TimeoutExpired:
        log = f"$ {' '.join(cmd)}\n(tempo esgotado: {TIMEOUT} s)"
    except OSError as error:
        raise DecryptError(f"não foi possível executar o RPCS3 ({rpcs3}): {error}") from error
    (work / "rpcs3_conversao.log").write_text(log, encoding="utf-8")
    if not out_elf.is_file() or out_elf.stat().st_size < 64:
        hint = ""
        if "KLIC" in log:
            hint = " O executável pede uma licença digital (KLIC): é de um jogo da PSN, não do disco."
        raise DecryptError("o RPCS3 não gerou o EBOOT.ELF." + hint + " Veja rpcs3_conversao.log. Confira se o RPCS3 "
                           "abre normalmente e se o firmware do PS3 está instalado nele (File > Install Firmware).")
    head = out_elf.read_bytes()[:64]
    hdr = formats.elf_header(head)
    if not hdr or "error" in hdr or hdr.get("machine_id") != 21:
        raise DecryptError("o arquivo gerado pelo RPCS3 não é um ELF PPU válido; veja rpcs3_conversao.log")
    copy.unlink()  # a cópia do SELF não é mais necessária
    return out_elf


def known_version(self_sha: str, elf_sha: str | None) -> dict:
    k = KNOWN.get(self_sha)
    if not k:
        return {"known": False}
    return {"known": True, **{key: v for key, v in k.items() if key != "elf_sha256"},
            "elf_matches": elf_sha == k["elf_sha256"] if elf_sha else None}
