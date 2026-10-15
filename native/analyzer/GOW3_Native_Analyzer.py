# SPDX-License-Identifier: GPL-2.0-only
"""Ponto de entrada do executável: sem argumentos abre a janela; com argumentos, linha de comando."""

import multiprocessing
import os
import sys


def _console_streams():
    """O executável é de janela (sem console). Na linha de comando, usa o console de quem o chamou."""
    if sys.stdout is not None:
        return
    stream = None
    if os.name == "nt":
        try:
            import ctypes
            if ctypes.windll.kernel32.AttachConsole(-1):
                stream = open("CONOUT$", "w", encoding="utf-8", errors="replace")
        except Exception:
            stream = None
    if stream is None:
        stream = open(os.devnull, "w", encoding="utf-8")
    sys.stdout = sys.stderr = stream


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if len(sys.argv) > 1:
        _console_streams()
        from gow3_analyzer.cli import main as cli_main
        sys.exit(cli_main())
    from gow3_analyzer.gui import main as gui_main
    gui_main()
