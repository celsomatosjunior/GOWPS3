# SPDX-License-Identifier: GPL-2.0-only
"""Ponto de entrada do executável: sem argumentos abre a janela; com argumentos, linha de comando."""

import multiprocessing
import os
import sys
import threading

# O executável gerado pelo PyInstaller tem pilha de 1 MB na thread principal (o python.exe tem
# 2 MB), pouco para a inicialização da CPU de referência (Unicorn/QEMU): no Windows isso derrubava
# o processo. Todo o trabalho roda em threads com pilha de 64 MB.
STACK = 64 * 1024 * 1024


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
    threading.stack_size(STACK)
    if len(sys.argv) > 1:
        _console_streams()
        from gow3_analyzer.cli import main as cli_main
        result = {}
        worker = threading.Thread(target=lambda: result.setdefault("code", cli_main()), name="cli")
        worker.start()
        worker.join()
        sys.exit(result.get("code", 1))
    from gow3_analyzer.gui import main as gui_main
    gui_main()
