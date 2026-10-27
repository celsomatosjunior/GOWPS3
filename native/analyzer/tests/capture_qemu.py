#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Captura de estados reais sem o jogo: o corpus do projeto roda no QEMU (qemu-ppc64 -g), que fala o
mesmo protocolo GDB do RPCS3, e o capturador do analisador para em cada função candidata do ELF de
teste (mesmo código, mesmos endereços), copia registradores e as páginas de memória usadas.
O arquivo gerado é reproduzido depois (run_synthetic.py --capturas) no código recompilado e no
PowerPC original, inclusive pelo .exe empacotado no Windows.

    python capture_qemu.py corpus.elf ps3_test.elf saida/ [--qemu qemu-ppc64] [--porta 23450]
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from gow3_analyzer import capture, pipeline  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus_elf")
    ap.add_argument("test_elf")
    ap.add_argument("out")
    ap.add_argument("--qemu", default="qemu-ppc64")
    ap.add_argument("--porta", type=int, default=23450)
    args = ap.parse_args()
    out = Path(args.out)
    rep = pipeline.run(args.test_elf, out / "analise", recompile=False, progress=lambda m: None,
                       captures_dir=out / "nenhuma")
    funcs = rep["analysis"]["candidates"][:40]
    code_same = all(
        pipeline.analysis.ElfImage(args.corpus_elf).read(int(f["start"], 16), 16)
        == pipeline.analysis.ElfImage(args.test_elf).read(int(f["start"], 16), 16) for f in funcs)
    print(f"{len(funcs)} candidatas; código igual no corpus e no ELF de teste: {code_same}")
    # -R: espaço de endereços abaixo de 4 GB, como no PS3 (a pilha do QEMU fica acima de 4 GB sem isso)
    q = subprocess.Popen([args.qemu, "-R", "0xF0000000", "-g", str(args.porta), args.corpus_elf], stdout=subprocess.DEVNULL)
    try:
        time.sleep(1.5)
        summary = capture.capture(Path(args.test_elf), funcs, out, port=args.porta, minutes=2, per_function=4,
                                  source="qemu (corpus do projeto)")
    finally:
        try:
            q.wait(30)
        except subprocess.TimeoutExpired:
            q.kill()
    print(summary)
    ok = (code_same and summary["functions_captured"] == len(funcs) and summary["states"] >= len(funcs)
          and summary["ok_states"] == summary["states"] and not summary["error"])
    print("CAPTURA QEMU: " + ("tudo certo" if ok else "falhou"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
