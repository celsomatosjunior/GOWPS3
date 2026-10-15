# SPDX-License-Identifier: GPL-2.0-only
"""Linha de comando. Sem argumentos, o executável abre a janela (gui.py).

    GOW3_Native_Analyzer.exe analisar <EBOOT.BIN|EBOOT.ELF|pasta> [--saida PASTA] [--sem-recompilar]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from . import __version__, pipeline


def default_output(base: Path | None = None) -> Path:
    root = base or (Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd())
    return root / "relatorios" / dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="GOW3_Native_Analyzer", description=f"GOW3 Native Analyzer {__version__}")
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("analisar", help="analisa o executável e testa a recompilação das candidatas")
    a.add_argument("entrada")
    a.add_argument("--saida")
    a.add_argument("--sem-recompilar", action="store_true")
    a.add_argument("--funcoes", type=int, default=40, help="máximo de funções candidatas no teste")
    a.add_argument("--casos", type=int, default=16, help="casos por função")
    a.add_argument("--alvo", help="alvo do zig (padrão: o sistema atual)")
    a.add_argument("--executor", nargs="*", help="programa para rodar o executável de teste (ex.: wine)")
    args = ap.parse_args(argv)
    if args.cmd == "analisar":
        out = Path(args.saida) if args.saida else default_output()
        out.mkdir(parents=True, exist_ok=True)
        log = open(out / "analise.log", "a", encoding="utf-8", buffering=1)
        # (sem faulthandler: no Windows ele registra como "fatal" exceções que o Unicorn trata
        # internamente, o que confundiria quem lê o log)

        def progress(msg):
            print(msg)
            log.write(msg + "\n")

        try:
            rep = pipeline.run(args.entrada, out, recompile=not args.sem_recompilar, limit=args.funcoes,
                               cases=args.casos, target=args.alvo, runner=args.executor, progress=progress)
        except Exception:
            import traceback
            log.write(traceback.format_exc())
            raise
        rt = rep.get("recompilation_test") or {}
        print(json.dumps({"saida": str(out), "pronto": rep["input"].get("ready"),
                          "funcoes": (rep.get("analysis") or {}).get("function_count"),
                          "teste": rt.get("totals") or rt.get("status")}, ensure_ascii=False, indent=1))
        if rt.get("status") == "falhou":
            return 3
        return 0 if rep["input"].get("ready") else 4
    ap.print_help()
    return 2
