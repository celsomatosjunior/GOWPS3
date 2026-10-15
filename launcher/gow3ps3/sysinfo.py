# SPDX-License-Identifier: GPL-2.0-only
"""Detecção do computador (CPU, memória, sistema, GPU Vulkan) e avaliação de requisitos.

Os limites usados em evaluate() são critérios do launcher para avisar o usuário,
não requisitos oficiais do RPCS3.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .game import Finding


@dataclass
class SystemInfo:
    os_name: str = ""
    os_version: str = ""
    is_64bit: bool = True
    cpu_name: str = ""
    threads: int = 0
    avx2: bool | None = None
    avx512: bool | None = None
    ram_gb: float = 0.0
    gpus: list[str] = field(default_factory=list)
    vulkan_checked: bool = False


def _windows_info(info: SystemInfo) -> None:
    import ctypes
    import winreg

    kernel32 = ctypes.windll.kernel32
    # PF_AVX2_INSTRUCTIONS_AVAILABLE = 40, PF_AVX512F_INSTRUCTIONS_AVAILABLE = 41
    info.avx2 = bool(kernel32.IsProcessorFeaturePresent(40))
    info.avx512 = bool(kernel32.IsProcessorFeaturePresent(41))

    class MemoryStatus(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(MemoryStatus)
    if kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        info.ram_gb = status.ullTotalPhys / 2**30
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        info.cpu_name = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
    except OSError:
        pass
    # Build 22000 em diante é Windows 11.
    build = sys.getwindowsversion().build
    info.os_version = f"{'11' if build >= 22000 else '10' if build >= 10240 else '?'} (build {build})"


def _linux_info(info: SystemInfo) -> None:
    try:
        cpuinfo = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace")
        name = re.search(r"^model name\s*:\s*(.+)$", cpuinfo, re.M)
        info.cpu_name = name.group(1).strip() if name else ""
        flags = re.search(r"^flags\s*:\s*(.+)$", cpuinfo, re.M)
        flag_set = set(flags.group(1).split()) if flags else set()
        info.avx2 = "avx2" in flag_set
        info.avx512 = "avx512f" in flag_set
    except OSError:
        pass
    try:
        meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
        total = re.search(r"^MemTotal:\s*(\d+) kB", meminfo, re.M)
        info.ram_gb = int(total.group(1)) / 2**20 if total else 0.0
    except OSError:
        pass
    info.os_version = platform.release()


def vulkan_devices(run=subprocess.run) -> list[str] | None:
    """Placas que o driver Vulkan expõe, via `vulkaninfo --summary`. None se a ferramenta não existir."""
    tool = shutil.which("vulkaninfo")
    if not tool:
        return None
    try:
        result = run([tool, "--summary"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_vulkaninfo(result.stdout)


def parse_vulkaninfo(text: str) -> list[str]:
    names = re.findall(r"^\s*deviceName\s*=\s*(.+?)\s*$", text, re.M)
    return list(dict.fromkeys(names))


def collect() -> SystemInfo:
    info = SystemInfo(os_name=platform.system(), is_64bit=sys.maxsize > 2**32,
                      threads=os.cpu_count() or 0)
    try:
        if sys.platform.startswith("win"):
            _windows_info(info)
        elif sys.platform.startswith("linux"):
            _linux_info(info)
    except Exception as error:  # a detecção nunca deve impedir o launcher de abrir
        info.cpu_name = info.cpu_name or f"(falha na detecção: {error})"
    devices = vulkan_devices()
    if devices is not None:
        info.gpus, info.vulkan_checked = devices, True
    return info


def evaluate(info: SystemInfo) -> list[Finding]:
    out = []
    add = out.append
    if not info.is_64bit:
        add(Finding("erro", "O RPCS3 exige sistema de 64 bits."))
    if info.os_name == "Windows" and info.os_version.startswith("?"):
        add(Finding("erro", "O RPCS3 exige Windows 10 ou mais novo."))
    if info.threads and info.threads < 4:
        add(Finding("aviso", f"Só {info.threads} threads de CPU: God of War III usa muito os SPUs e deve ficar lento."))
    elif info.threads:
        add(Finding("ok", f"CPU com {info.threads} threads"))
    if info.avx2 is False:
        add(Finding("aviso", "CPU sem AVX2: o recompilador fica mais lento."))
    if info.avx512:
        add(Finding("ok", "CPU com AVX-512: o RPCS3 usa essas instruções nos SPUs."))
    if info.ram_gb and info.ram_gb < 8:
        add(Finding("aviso", f"{info.ram_gb:.1f} GB de RAM: abaixo de 8 GB o jogo pode travar."))
    elif info.ram_gb:
        add(Finding("ok", f"{info.ram_gb:.1f} GB de RAM"))
    if info.vulkan_checked and not info.gpus:
        add(Finding("erro", "Nenhuma placa com Vulkan encontrada. Atualize o driver de vídeo."))
    elif info.gpus:
        add(Finding("ok", "Vulkan: " + ", ".join(info.gpus)))
    else:
        add(Finding("aviso", "Não foi possível verificar o Vulkan aqui (vulkaninfo ausente); "
                             "o RPCS3 vai listar as placas ao iniciar."))
    return out
