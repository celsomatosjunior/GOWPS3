# SPDX-License-Identifier: GPL-2.0-only
"""Configurações do launcher e geração do arquivo de configuração lido pelo RPCS3 (--config).

Os nomes das chaves e os textos dos valores são exatamente os que o RPCS3 grava no config.yml
(rpcs3/Emu/system_config.h e system_config_types.cpp). Qualquer chave ausente fica com o
padrão do RPCS3, porque ele carrega os padrões antes de aplicar o arquivo.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

# God of War III roda em 1280x720 no PS3; a escala do RPCS3 é relativa a isso.
INTERNAL_RESOLUTIONS = {"720p": 100, "900p": 125, "1080p": 150, "1440p": 200, "4K": 300}
SCALING = {"bilinear": "Bilinear", "fsr": "FidelityFX Super Resolution", "nearest": "Nearest"}
VSYNC = {"off": "Disabled", "adaptive": "Adaptive", "full": "Full"}
FRAME_LIMIT = {"auto": "Auto", "30": "30", "60": "60", "120": "120", "display": "Display", "off": "Off"}
SHADER_MODE = {
    "async_interpreter": "Async Recompiler with Shader Interpreter",
    "async": "Async Recompiler (multi-threaded)",
    "legacy": "Legacy Recompiler (single-threaded)",
}
SPU_BLOCK = {"safe": "Safe", "mega": "Mega", "giga": "Giga"}
ANISOTROPIC = (0, 2, 4, 8, 16)   # 0 = o jogo decide


@dataclass
class Settings:
    rpcs3_path: str = ""
    game_path: str = ""
    internal_resolution: str = "720p"
    output_scaling: str = "bilinear"
    rcas_sharpening: int = 50
    anisotropic: int = 0
    vsync: str = "off"
    frame_limit: str = "auto"
    shader_mode: str = "async_interpreter"
    fullscreen: bool = True
    performance_overlay: bool = False
    shader_compilation_hint: bool = True
    # Valores recomendados pela wiki do RPCS3 para God of War III.
    write_color_buffers: bool = True
    spu_block_size: str = "safe"
    preferred_spu_threads: int = 0
    vulkan_adapter: str = ""

    def validate(self) -> list[str]:
        errors = []
        checks = (
            ("internal_resolution", INTERNAL_RESOLUTIONS), ("output_scaling", SCALING),
            ("vsync", VSYNC), ("frame_limit", FRAME_LIMIT), ("shader_mode", SHADER_MODE),
            ("spu_block_size", SPU_BLOCK),
        )
        for name, allowed in checks:
            if getattr(self, name) not in allowed:
                errors.append(f"{name}: valor inválido {getattr(self, name)!r}")
        if self.anisotropic not in ANISOTROPIC:
            errors.append(f"anisotropic: valor inválido {self.anisotropic!r}")
        if not 0 <= self.rcas_sharpening <= 100:
            errors.append("rcas_sharpening: precisa estar entre 0 e 100")
        if not 0 <= self.preferred_spu_threads <= 6:
            errors.append("preferred_spu_threads: precisa estar entre 0 e 6")
        return errors


def load(path) -> Settings:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    known = {f.name for f in fields(Settings)}
    settings = Settings(**{k: v for k, v in data.items() if k in known})
    return settings if not settings.validate() else Settings(rpcs3_path=settings.rpcs3_path,
                                                             game_path=settings.game_path)


def save(settings: Settings, path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(asdict(settings), indent=2, ensure_ascii=False), encoding="utf-8")


def rpcs3_config(settings: Settings) -> dict:
    errors = settings.validate()
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "Core": {
            "PPU Decoder": "Recompiler (LLVM)",
            "SPU Decoder": "Recompiler (LLVM)",
            "SPU Block Size": SPU_BLOCK[settings.spu_block_size],
            "Preferred SPU Threads": settings.preferred_spu_threads,
        },
        "Video": {
            "Renderer": "Vulkan",
            "Resolution": "1280x720",
            "Resolution Scale": INTERNAL_RESOLUTIONS[settings.internal_resolution],
            "Output Scaling Mode": SCALING[settings.output_scaling],
            "FidelityFX CAS Sharpening Intensity": settings.rcas_sharpening,
            "Anisotropic Filter Override": settings.anisotropic,
            "VSync Mode": VSYNC[settings.vsync],
            "Frame limit": FRAME_LIMIT[settings.frame_limit],
            "Shader Mode": SHADER_MODE[settings.shader_mode],
            "Write Color Buffers": settings.write_color_buffers,
            "Vulkan": {"Adapter": settings.vulkan_adapter},
            "Performance Overlay": {"Enabled": settings.performance_overlay},
        },
        "Miscellaneous": {
            "Exit RPCS3 when process finishes": True,
            "Start games in fullscreen mode": settings.fullscreen,
            "Show shader compilation hint": settings.shader_compilation_hint,
        },
    }


def _scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def to_yaml(tree: dict, indent: int = 0) -> str:
    lines = []
    for key, value in tree.items():
        if isinstance(value, dict):
            lines.append(" " * indent + f"{key}:")
            lines.append(to_yaml(value, indent + 2))
        else:
            lines.append(" " * indent + f"{key}: {_scalar(value)}")
    return "\n".join(lines)


def write_rpcs3_config(settings: Settings, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Gerado pelo GOW3 PS3 PC. Alterações aqui são sobrescritas a cada início.\n"
                    + to_yaml(rpcs3_config(settings)) + "\n", encoding="utf-8")
    return path
