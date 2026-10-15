# SPDX-License-Identifier: GPL-2.0-only
"""Lógica do launcher, separada da interface para poder ser testada."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import game, psf, rpcs3, settings as settings_mod
from .game import Finding

APP_NAME = "GOW3 PS3 PC"
VERSION = "0.1.0"


def default_base_dir() -> Path:
    override = os.environ.get("GOW3PS3_HOME")
    if override:
        return Path(override)
    if sys.platform.startswith("win"):
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "GOW3PS3PC"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "gow3ps3pc"


@dataclass
class Launcher:
    base_dir: Path = field(default_factory=default_base_dir)
    platform: str = sys.platform

    @property
    def settings_file(self) -> Path:
        return self.base_dir / "launcher.json"

    @property
    def profile_dir(self) -> Path:
        return self.base_dir / "rpcs3_profile"

    @property
    def manifest_file(self) -> Path:
        return self.base_dir / "game_manifest.json"

    @property
    def paths(self) -> rpcs3.ProfilePaths:
        return rpcs3.profile_paths(self.profile_dir, self.platform)

    def load_settings(self) -> settings_mod.Settings:
        return settings_mod.load(self.settings_file)

    def save_settings(self, value: settings_mod.Settings) -> None:
        settings_mod.save(value, self.settings_file)

    def installed_update(self, serial: str) -> str:
        sfo = self.paths.game_updates / serial / "PARAM.SFO"
        try:
            data = psf.load(sfo)
        except (OSError, psf.PsfError):
            return ""
        return str(data.get("APP_VER", ""))

    def preflight(self, value: settings_mod.Settings) -> tuple[list[Finding], game.GameInfo | None]:
        findings: list[Finding] = []
        add = findings.append

        executable = rpcs3.find_executable(value.rpcs3_path) if value.rpcs3_path else None
        if executable is None:
            add(Finding("erro", "Escolha a pasta do RPCS3 (o executável rpcs3.exe)."))
        else:
            add(Finding("ok", f"RPCS3: {executable}"))
            portable = rpcs3.portable_dir(executable)
            if portable:
                add(Finding("erro", f"Este RPCS3 tem a pasta {portable}. Ela faz o RPCS3 ignorar o perfil "
                                    "separado do launcher: use outra cópia do RPCS3 ou renomeie a pasta."))

        info = None
        if not value.game_path:
            add(Finding("erro", "Escolha a pasta do God of War III."))
        else:
            info = game.inspect(value.game_path)
            findings += info.findings

        if rpcs3.firmware_installed(self.paths):
            installed = rpcs3.firmware_version(self.paths)
            add(Finding("ok", f"Firmware instalado no perfil: {installed or 'versão desconhecida'}"))
            if info and info.required_firmware and installed and \
                    rpcs3.version_tuple(installed) < rpcs3.version_tuple(info.required_firmware):
                add(Finding("erro", f"O jogo pede firmware {info.required_firmware}; o perfil tem {installed}."))
        else:
            add(Finding("erro", "Firmware do PS3 não instalado neste perfil. Baixe o PS3UPDAT.PUP no site "
                                "oficial da PlayStation e use 'Instalar firmware'."))

        if info and info.serial:
            update = self.installed_update(info.serial)
            if update:
                add(Finding("ok", f"Atualização do jogo instalada: versão {update}"))
            else:
                add(Finding("aviso", "Nenhuma atualização do jogo instalada no perfil."))

        add(Finding("ok", f"Salvamentos deste perfil: {self.paths.savedata}"))
        return findings, info

    def check_integrity(self, info: game.GameInfo, reset: bool = False) -> list[Finding]:
        current = game.file_manifest(info.game_dir)
        saved = None if reset else game.load_manifest(self.manifest_file)
        if saved is None:
            game.save_manifest(self.manifest_file, current)
            return [Finding("ok", f"Referência criada com {len(current)} arquivos. As próximas verificações "
                                  "comparam com ela.")]
        return game.compare_manifest(saved, current)

    def command(self, value: settings_mod.Settings, info: game.GameInfo) -> list[str]:
        executable = rpcs3.find_executable(value.rpcs3_path)
        config = settings_mod.write_rpcs3_config(value, self.paths.override_config)
        return rpcs3.boot_command(executable, info.boot_path, config, value.fullscreen)

    def play(self, value: settings_mod.Settings):
        findings, info = self.preflight(value)
        blocking = [f for f in findings if f.level == "erro"]
        if blocking:
            raise RuntimeError("\n".join(f.message for f in blocking))
        return rpcs3.start(self.command(value, info), self.profile_dir, self.platform)

    def install_firmware(self, value: settings_mod.Settings, pup_file):
        executable = rpcs3.find_executable(value.rpcs3_path)
        if executable is None:
            raise RuntimeError("Escolha a pasta do RPCS3 primeiro.")
        if Path(pup_file).name.upper() != "PS3UPDAT.PUP":
            raise RuntimeError("Escolha o arquivo PS3UPDAT.PUP.")
        return rpcs3.start(rpcs3.install_firmware_command(executable, pup_file), self.profile_dir, self.platform)
