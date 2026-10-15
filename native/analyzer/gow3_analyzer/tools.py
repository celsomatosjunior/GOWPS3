# SPDX-License-Identifier: GPL-2.0-only
"""Acesso às ferramentas do ps3recomp (MIT) dentro do próprio processo.

No executável empacotado (PyInstaller) não há um python.exe para rodar scripts, então as
ferramentas são importadas como módulos e chamadas com sys.argv ajustado.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import os
import sys
from pathlib import Path


def resource_dir() -> Path:
    """Pasta dos recursos empacotados (ps3recomp, runtime C++, zig)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def ps3recomp_tools() -> Path:
    env = os.environ.get("GOW3_PS3RECOMP")
    candidates = [Path(env) / "tools"] if env else []
    candidates += [resource_dir() / "ps3recomp" / "tools", resource_dir().parent.parent.parent / "ps3recomp" / "tools"]
    for c in candidates:
        if (c / "ppu_lifter.py").is_file():
            return c
    raise FileNotFoundError("ferramentas do ps3recomp não encontradas (defina GOW3_PS3RECOMP)")


def ps3recomp_root() -> Path:
    return ps3recomp_tools().parent


def load(module: str):
    tools = str(ps3recomp_tools())
    if tools not in sys.path:
        sys.path.insert(0, tools)
    return importlib.import_module(module)


class ToolError(RuntimeError):
    pass


def run_tool(module: str, argv: list[str]) -> str:
    """Executa main() de uma ferramenta do ps3recomp e devolve o que ela imprimiu."""
    mod = load(module)
    out = io.StringIO()
    old = sys.argv
    sys.argv = [module + ".py"] + [str(a) for a in argv]
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            result = mod.main()
    except SystemExit as e:
        result = e.code
    finally:
        sys.argv = old
    if result not in (None, 0):
        raise ToolError(f"{module} terminou com código {result}:\n{out.getvalue()[-2000:]}")
    return out.getvalue()
