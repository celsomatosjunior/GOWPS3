# SPDX-License-Identifier: GPL-2.0-only
"""Ponto de entrada: `python -m gow3ps3` abre a janela; as opções abaixo servem a atalhos e testes."""

from __future__ import annotations

import argparse
import sys

from . import app, sysinfo

MARK = {"ok": "OK  ", "aviso": "AVISO", "erro": "ERRO"}


def _print(findings) -> None:
    for finding in findings:
        print(f"[{MARK[finding.level]}] {finding.message}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="gow3ps3", description=f"{app.APP_NAME} {app.VERSION}")
    parser.add_argument("--check", action="store_true", help="verifica RPCS3, firmware, jogo e computador")
    parser.add_argument("--print-command", action="store_true", help="mostra o comando que iniciaria o jogo")
    parser.add_argument("--play", action="store_true", help="inicia o jogo com as configurações salvas")
    parser.add_argument("--rpcs3", help="executável ou pasta do RPCS3 (salvo nas configurações)")
    parser.add_argument("--game", help="pasta do God of War III (salvo nas configurações)")
    args = parser.parse_args(argv)

    launcher = app.Launcher()
    settings = launcher.load_settings()
    if args.rpcs3:
        settings.rpcs3_path = args.rpcs3
    if args.game:
        settings.game_path = args.game
    if args.rpcs3 or args.game:
        launcher.save_settings(settings)

    if not (args.check or args.print_command or args.play):
        from .gui import main as gui_main
        return gui_main()

    findings, info = launcher.preflight(settings)
    if args.check:
        _print(findings)
        _print(sysinfo.evaluate(sysinfo.collect()))
    blocking = any(f.level == "erro" for f in findings)
    if args.print_command:
        if info is None or not info.ok or not settings.rpcs3_path:
            print("Sem jogo ou RPCS3 válidos: nada a iniciar.", file=sys.stderr)
            return 2
        print(" ".join(f'"{part}"' if " " in part else part for part in launcher.command(settings, info)))
    if args.play:
        if blocking:
            _print([f for f in findings if f.level == "erro"])
            return 2
        return launcher.play(settings).wait()
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
