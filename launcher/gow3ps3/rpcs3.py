# SPDX-License-Identifier: GPL-2.0-only
"""Integração com um executável do RPCS3 já instalado pelo usuário, sem modificá-lo.

Cada comportamento usado aqui foi conferido no código do RPCS3 (commit 4d5def5, 15/10/2026):
  * opções --no-gui, --fullscreen, --config, --installfw: rpcs3/rpcs3.cpp
  * --config aplica o arquivo por cima dos padrões (cfg_mode::config_override): rpcs3/Emu/System.cpp
  * Windows: RPCS3_CONFIG_DIR troca a pasta de dados; o RPCS3 corta tudo depois da última barra,
    então o valor PRECISA terminar com separador: Utilities/File.cpp, fs::get_config_dir
  * Linux: XDG_CONFIG_HOME / XDG_CACHE_HOME + "/rpcs3/": Utilities/File.cpp
  * uma pasta "portable" ao lado do executável tem prioridade sobre tudo isso
  * firmware: dev_flash/sys/external/liblv2.sprx e dev_flash/vsh/etc/version.txt
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


def is_windows(platform: str | None = None) -> bool:
    return (platform or sys.platform).startswith("win")


@dataclass(frozen=True)
class ProfilePaths:
    """Onde o RPCS3 vai gravar cada coisa quando iniciado com o ambiente deste perfil."""
    profile: Path
    emu_dir: Path        # $(EmulatorDir): dev_hdd0, dev_flash...
    config_dir: Path     # config.yml, custom_configs, input_configs
    cache_dir: Path      # cache de PPU/SPU/shaders
    log_file: Path

    @property
    def dev_flash(self) -> Path:
        return self.emu_dir / "dev_flash"

    @property
    def savedata(self) -> Path:
        return self.emu_dir / "dev_hdd0" / "home" / "00000001" / "savedata"

    @property
    def game_updates(self) -> Path:
        return self.emu_dir / "dev_hdd0" / "game"

    @property
    def override_config(self) -> Path:
        return self.profile / "gow3ps3_rpcs3.yml"


def profile_paths(profile, platform: str | None = None) -> ProfilePaths:
    profile = Path(profile)
    if is_windows(platform):
        return ProfilePaths(profile, profile, profile / "config", profile / "cache",
                            profile / "log" / "RPCS3.log")
    config = profile / "xdg" / "config" / "rpcs3"
    cache = profile / "xdg" / "cache" / "rpcs3"
    return ProfilePaths(profile, config, config, cache / "cache", cache / "RPCS3.log")


def environment(profile, base_env=None, platform: str | None = None) -> dict[str, str]:
    env = dict(os.environ if base_env is None else base_env)
    profile = Path(profile)
    if is_windows(platform):
        value = str(profile)
        if not value.endswith(("\\", "/")):
            value += "\\"
        env["RPCS3_CONFIG_DIR"] = value
    else:
        env["XDG_CONFIG_HOME"] = str(profile / "xdg" / "config")
        env["XDG_CACHE_HOME"] = str(profile / "xdg" / "cache")
    return env


def find_executable(path) -> Path | None:
    """Aceita o próprio executável ou a pasta onde ele está."""
    path = Path(path)
    if path.is_file():
        return path
    for name in ("rpcs3.exe", "rpcs3", "rpcs3.AppImage"):
        if (path / name).is_file():
            return path / name
    return None


def portable_dir(executable) -> Path | None:
    candidate = Path(executable).parent / "portable"
    return candidate if candidate.is_dir() else None


def firmware_version(paths: ProfilePaths) -> str:
    """Mesma regra de utils::get_firmware_version: 'release:04.9200:' vira '4.92'."""
    try:
        text = (paths.dev_flash / "vsh" / "etc" / "version.txt").read_text("ascii", "replace")
    except OSError:
        return ""
    parts = text.split(":")
    if len(parts) < 3:
        return ""
    version = parts[1]
    trim_start = len(version) - len(version.lstrip("0"))
    if trim_start == len(version):
        return ""
    if version[trim_start] == ".":
        if trim_start == 0:
            return ""
        trim_start -= 1
    dot = version.find(".", trim_start)
    if dot < 0:
        return ""
    # Reproduz a conta do RPCS3 (o segundo argumento de substr é uma contagem).
    last_not_zero = next((i for i in range(min(dot + 1, len(version) - 1), -1, -1) if version[i] != "0"), -1)
    count = max(last_not_zero, min(dot + 2, len(version)))
    return version[trim_start:trim_start + count]


def firmware_installed(paths: ProfilePaths) -> bool:
    return (paths.dev_flash / "sys" / "external" / "liblv2.sprx").is_file()


def version_tuple(text: str) -> tuple[int, ...]:
    out = []
    for piece in text.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out)


def boot_command(executable, game_path, config_file, fullscreen: bool = True) -> list[str]:
    command = [str(executable), "--no-gui"]
    if fullscreen:
        command.append("--fullscreen")   # o RPCS3 só aceita junto com --no-gui
    command += ["--config", str(config_file), str(game_path)]
    return command


def install_firmware_command(executable, pup_file) -> list[str]:
    return [str(executable), "--installfw", str(pup_file)]


def start(command, profile, platform: str | None = None) -> subprocess.Popen:
    paths = profile_paths(profile, platform)
    paths.profile.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(command, env=environment(profile, platform=platform),
                            cwd=str(Path(command[0]).parent))
