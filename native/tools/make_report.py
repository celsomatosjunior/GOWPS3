#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Monta o NATIVE_REPORT.md a partir dos artefatos do workflow native.yml."""

import argparse
import json
import os
from pathlib import Path


def read(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def last_line_with(text, needle):
    lines = [l for l in text.splitlines() if needle in l]
    return lines[-1].strip() if lines else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifacts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--run-url", default="")
    a = ap.parse_args()
    art = Path(a.artifacts)
    r_tools, r_gen, r_win = (os.environ.get(k, "?") for k in ("R_PS3RECOMP", "R_GENERATE", "R_WINDOWS"))

    win_logs = art / "ps3recomp_windows_logs"
    bundle = art / "ppu_diff_bundle"
    winexe = art / "ppu_recomp_windows_x64"
    stats = {}
    try:
        stats = json.loads(read(bundle / "stats.json"))
    except ValueError:
        pass
    cmp_linux = read(bundle / "compare_linux.txt")
    cmp_win = read(winexe / "compare_windows.txt")
    win_ok = "RESULTADO: APROVADO" in cmp_win
    linux_ok = "RESULTADO: APROVADO" in cmp_linux
    suites = read(win_logs / "lifter_suites_windows.txt")
    conformance = last_line_with(suites, "ppu-conformance")

    def mark(ok):
        return "✅" if ok else "❌"

    L = ["# GOW3 PS3 NATIVE — relatório da recompilação estática", "",
         f"Execução: {a.run_url}", "",
         "## Escada de progresso", "",
         "| Etapa | Situação |", "|---|---|",
         f"| 1. Ferramentas compiladas (ps3recomp no Windows, clang-cl) | {mark(r_tools == 'success')} {r_tools} |",
         "| 2. Executável do God of War III analisado | ⬜ aguardando o EBOOT do jogo (ferramenta `native/tools/analyze_gow3.py` pronta) |",
         f"| 3. Código PPU recompilado | 🟨 corpus de teste: {mark(win_ok)} Windows x64, {mark(linux_ok)} Linux; God of War III: ⬜ |",
         "| 4. Código SPU recompilado | ⬜ |",
         "| 5. Runtime inicializado | ⬜ |",
         "| 6. Primeiro quadro renderizado | ⬜ |",
         "| 7. Menu principal | ⬜ |",
         "| 8. Gameplay | ⬜ |",
         "| 9. Salvamento e carregamento | ⬜ |",
         "| 10. Jogo completo | ⬜ |", "",
         "## Teste diferencial PPU (código PowerPC real, não do jogo)", "",
         "O corpus (`native/ppu_diff/corpus.c`, código do projeto) foi compilado para PowerPC com "
         "`gcc -mcpu=cell`, executado no QEMU como referência, recompilado para C pelo `ppu_lifter` do "
         "ps3recomp e compilado para x86-64.", "",
         f"- Funções recompiladas: {stats.get('functions', '?')}; linhas de C geradas: {stats.get('lifted_c_lines', '?')}; "
         f"casos: {stats.get('cases', '?')}",
         f"- Windows x64 (clang-cl): {last_line_with(cmp_win, 'Recompilado x PowerPC') or 'sem resultado'}",
         f"- Linux x64 (clang): {last_line_with(cmp_linux, 'Recompilado x PowerPC') or 'sem resultado'}",
         f"- Executável Windows: {read(winexe / 'exe_windows.txt').strip().splitlines()[0] if read(winexe / 'exe_windows.txt') else 'não gerado'}",
         "", "## ps3recomp no Windows", "",
         f"- Compilador: {read(win_logs / 'toolchain.txt').strip().splitlines()[0] if read(win_logs / 'toolchain.txt') else '?'}",
         f"- ctest: {last_line_with(read(win_logs / 'ctest_windows.txt'), 'tests passed') or 'sem resultado'}",
         f"- Conformidade de instruções (compiladas e executadas no Windows): {conformance or 'sem resultado'}",
         f"- Andaime de boot PPU: {(read(win_logs / 'scaffold_windows.txt').strip().splitlines() or ['?'])[-1]}",
         "", "## O que isto NÃO prova", "",
         "- Nada aqui executou código do God of War III.",
         "- Recompilar e executar um corpus pequeno não garante que o jogo inteiro funcione: faltam a análise "
         "do executável real, SPU, runtime do sistema e gráficos (etapas 2 a 10).",
         ]
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
