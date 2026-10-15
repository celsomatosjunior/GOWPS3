# SPDX-License-Identifier: GPL-2.0-only
"""Reconhecimento e verificação da pasta do God of War III (PS3) fornecida pelo usuário.

O launcher só LÊ os arquivos do jogo: nada é decifrado, alterado ou copiado.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import psf

# Seriais listados para God of War III na wiki do RPCS3
# (https://wiki.rpcs3.net/index.php?title=God_of_War_III, consultada em 15/10/2026).
KNOWN_SERIALS = (
    "BCES00510", "BCUS98111", "BCAS25003", "BCES00799", "BCKS15003",
    "BCES00516", "BCAS25007", "BCJS37001", "BCJS75001",
)

# Convenção de prefixos dos seriais de disco da Sony.
REGION_BY_PREFIX = {
    "BCUS": "América do Norte",
    "BCES": "Europa",
    "BCAS": "Ásia",
    "BCJS": "Japão",
    "BCKS": "Coreia",
}

SELF_MAGIC = b"SCE\x00"   # executável assinado/cifrado (formato original do disco)
ELF_MAGIC = b"\x7fELF"    # executável já decifrado pelo próprio usuário


@dataclass
class Finding:
    level: str      # "ok", "aviso" ou "erro"
    message: str


@dataclass
class GameInfo:
    root: Path                    # pasta escolhida pelo usuário
    game_dir: Path                # pasta que contém PARAM.SFO e USRDIR
    boot_path: Path               # caminho entregue ao RPCS3
    serial: str = ""
    title: str = ""
    app_version: str = ""
    required_firmware: str = ""
    category: str = ""
    region: str = ""
    eboot_kind: str = ""
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.level == "erro" for f in self.findings)


def _locate(root: Path) -> Path | None:
    """Aceita a raiz do disco (com PS3_GAME), a própria PS3_GAME ou uma pasta de jogo do HDD."""
    for candidate in (root / "PS3_GAME", root):
        if (candidate / "PARAM.SFO").is_file():
            return candidate
    return None


def _firmware_text(value) -> str:
    # PS3_SYSTEM_VER vem como "03.1500"; o RPCS3 mostra "3.15".
    text = str(value or "").strip()
    try:
        major, minor = text.split(".", 1)
        return f"{int(major)}.{minor.rstrip('0') or '0'}"
    except ValueError:
        return text


def inspect(root) -> GameInfo:
    root = Path(root)
    info = GameInfo(root=root, game_dir=root, boot_path=root)
    add = info.findings.append

    if not root.is_dir():
        add(Finding("erro", f"A pasta não existe: {root}"))
        return info

    game_dir = _locate(root)
    if game_dir is None:
        add(Finding("erro", "PARAM.SFO não encontrado. Escolha a pasta do jogo "
                            "(a que contém PS3_GAME, ou a própria PS3_GAME)."))
        return info
    info.game_dir = game_dir
    # Disco completo: o RPCS3 recebe a raiz; pasta isolada: recebe a própria pasta.
    info.boot_path = root if game_dir != root else game_dir

    try:
        sfo = psf.load(game_dir / "PARAM.SFO")
    except (OSError, psf.PsfError) as error:
        add(Finding("erro", f"PARAM.SFO ilegível: {error}"))
        return info

    info.serial = str(sfo.get("TITLE_ID", ""))
    info.title = str(sfo.get("TITLE", ""))
    info.app_version = str(sfo.get("APP_VER", sfo.get("VERSION", "")))
    info.category = str(sfo.get("CATEGORY", ""))
    info.required_firmware = _firmware_text(sfo.get("PS3_SYSTEM_VER", ""))
    info.region = REGION_BY_PREFIX.get(info.serial[:4], "desconhecida")

    if info.serial in KNOWN_SERIALS:
        add(Finding("ok", f"God of War III reconhecido: {info.serial} ({info.region})"))
    else:
        add(Finding("erro", f"O serial {info.serial or '(vazio)'} não é de God of War III. "
                            f"Seriais aceitos: {', '.join(KNOWN_SERIALS)}"))

    if info.category not in ("DG", "HG", "GD"):
        add(Finding("aviso", f"Categoria inesperada no PARAM.SFO: {info.category or '(vazia)'}"))

    eboot = game_dir / "USRDIR" / "EBOOT.BIN"
    if not eboot.is_file():
        add(Finding("erro", "USRDIR/EBOOT.BIN não encontrado: a cópia do jogo está incompleta."))
    else:
        with open(eboot, "rb") as stream:
            magic = stream.read(4)
        if magic == SELF_MAGIC:
            info.eboot_kind = "SELF (original do disco)"
        elif magic == ELF_MAGIC:
            info.eboot_kind = "ELF (já decifrado)"
        else:
            info.eboot_kind = "desconhecido"
            add(Finding("erro", "EBOOT.BIN não tem cabeçalho SELF nem ELF: arquivo corrompido."))
        if info.eboot_kind != "desconhecido":
            add(Finding("ok", f"EBOOT.BIN presente: {info.eboot_kind}"))

    empty = [p for p in _walk(game_dir / "USRDIR") if p.stat().st_size == 0]
    if empty:
        sample = ", ".join(str(p.relative_to(game_dir)) for p in empty[:3])
        add(Finding("aviso", f"{len(empty)} arquivo(s) vazio(s) em USRDIR (ex.: {sample}). "
                             "Isso costuma indicar uma cópia interrompida."))
    if game_dir != root and not (root / "PS3_DISC.SFB").is_file():
        add(Finding("aviso", "PS3_DISC.SFB ausente na raiz do disco."))
    return info


def _walk(directory: Path):
    if not directory.is_dir():
        return
    for base, _dirs, files in os.walk(directory):
        for name in files:
            yield Path(base) / name


def file_manifest(game_dir) -> dict[str, list]:
    """Tamanho e SHA-256 de cada arquivo, para detectar mudanças depois da primeira verificação."""
    game_dir = Path(game_dir)
    manifest = {}
    for path in sorted(_walk(game_dir)):
        digest = hashlib.sha256()
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
        manifest[path.relative_to(game_dir).as_posix()] = [path.stat().st_size, digest.hexdigest()]
    return manifest


def compare_manifest(saved: dict, current: dict) -> list[Finding]:
    findings = []
    missing = sorted(set(saved) - set(current))
    changed = sorted(k for k in set(saved) & set(current) if saved[k] != current[k])
    added = sorted(set(current) - set(saved))
    if missing:
        findings.append(Finding("erro", f"{len(missing)} arquivo(s) sumiram desde a última verificação "
                                        f"(ex.: {missing[0]})"))
    if changed:
        findings.append(Finding("erro", f"{len(changed)} arquivo(s) mudaram desde a última verificação "
                                        f"(ex.: {changed[0]})"))
    if added:
        findings.append(Finding("aviso", f"{len(added)} arquivo(s) novos (ex.: {added[0]})"))
    if not findings:
        findings.append(Finding("ok", f"Integridade conferida: {len(current)} arquivos iguais à referência"))
    return findings


def save_manifest(path, manifest) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(manifest, indent=1), encoding="utf-8")


def load_manifest(path) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
