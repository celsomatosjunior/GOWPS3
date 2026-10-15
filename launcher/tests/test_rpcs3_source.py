# SPDX-License-Identifier: GPL-2.0-only
"""Confere, no código-fonte do RPCS3, cada nome e texto que o launcher usa.

Rode com RPCS3_SRC apontando para um clone do RPCS3; sem isso o teste é pulado.
Serve para pegar mudanças do RPCS3 que quebrariam o launcher sem aviso.
"""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

from gow3ps3 import diagnostics, settings

SRC = os.environ.get("RPCS3_SRC")


@unittest.skipUnless(SRC, "defina RPCS3_SRC com o caminho de um clone do RPCS3")
class Rpcs3SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(SRC)
        cls.config_h = (root / "rpcs3/Emu/system_config.h").read_text(encoding="utf-8")
        cls.types_cpp = (root / "rpcs3/Emu/system_config_types.cpp").read_text(encoding="utf-8")
        cls.cli = (root / "rpcs3/rpcs3.cpp").read_text(encoding="utf-8")
        cls.everything = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                                   for p in (root / "rpcs3").rglob("*.cpp"))

    def _keys(self, tree):
        for key, value in tree.items():
            if isinstance(value, dict):
                yield key, None
                yield from self._keys(value)
            else:
                yield key, value

    def test_every_config_key_exists(self):
        for key, value in self._keys(settings.rpcs3_config(settings.Settings())):
            self.assertIn(f'"{key}"', self.config_h, f"chave {key!r} não existe no RPCS3")

    def test_every_enum_text_exists(self):
        tables = (settings.SCALING, settings.VSYNC, settings.FRAME_LIMIT, settings.SHADER_MODE, settings.SPU_BLOCK)
        for table in tables:
            for text in table.values():
                self.assertIn(f'return "{text}"', self.types_cpp, f"valor {text!r} não existe no RPCS3")
        for text in ("Recompiler (LLVM)", "Vulkan", "1280x720"):
            self.assertIn(f'return "{text}"', self.types_cpp)

    def test_value_ranges(self):
        scale = re.search(r'uint<(\d+), (\d+)> resolution_scale_percent', self.config_h)
        low, high = map(int, scale.groups())
        for percent in settings.INTERNAL_RESOLUTIONS.values():
            self.assertTrue(low <= percent <= high)
        self.assertIn('uint<0, 16> anisotropic_level_override', self.config_h)
        self.assertIn('_int<0, 6> preferred_spu_threads', self.config_h)

    def test_cli_options_exist(self):
        for option in ("no-gui", "fullscreen", "config", "installfw"):
            self.assertIn(f'= "{option}";', self.cli)

    def test_log_strings_exist(self):
        for needle, _ in diagnostics.KNOWN_PATTERNS:
            self.assertIn(needle.strip(), self.everything, f"texto {needle!r} não aparece no RPCS3")


if __name__ == "__main__":
    unittest.main()
