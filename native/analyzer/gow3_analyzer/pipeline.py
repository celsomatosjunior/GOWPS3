# SPDX-License-Identifier: GPL-2.0-only
"""Fluxo completo: localizar o executável, identificar, analisar, recompilar/testar e gerar relatórios."""

from __future__ import annotations

import traceback
from pathlib import Path

from . import __version__, analysis, formats, recomp_test, report, tools

ELF_NAMES = ("EBOOT.ELF", "EBOOT.elf", "eboot.elf", "EBOOT.BIN.elf", "EBOOT.BIN.ELF")


def locate(path: Path) -> tuple[Path, list[str]]:
    """Aceita o EBOOT.BIN, um ELF, a pasta USRDIR, a pasta PS3_GAME ou a pasta do jogo.
    Se ao lado do EBOOT.BIN houver um EBOOT.ELF preparado pelo usuário, ele é usado."""
    notes = []
    path = Path(path)
    if path.is_dir():
        for base in (path, path / "USRDIR", path / "PS3_GAME" / "USRDIR"):
            for name in ELF_NAMES + ("EBOOT.BIN",):
                if (base / name).is_file():
                    notes.append(f"Pasta escolhida; usando {base / name}")
                    return base / name, notes
        raise FileNotFoundError(f"nenhum EBOOT.BIN ou EBOOT.ELF encontrado em {path}")
    if path.name.upper() == "EBOOT.BIN":
        for name in ELF_NAMES:
            if (path.parent / name).is_file():
                notes.append(f"Encontrado {name} ao lado do EBOOT.BIN; ele será analisado.")
                return path.parent / name, notes
    return path, notes


def find_sfo(exe: Path) -> dict:
    for cand in (exe.parent.parent / "PARAM.SFO", exe.parent / "PARAM.SFO", exe.parent.parent.parent / "PS3_GAME" / "PARAM.SFO"):
        if cand.is_file():
            try:
                sfo = formats.read_sfo(cand)
                return {k: v for k, v in sfo.items() if k in ("TITLE", "TITLE_ID", "APP_VER", "VERSION", "CATEGORY", "PS3_SYSTEM_VER")}
            except Exception:
                return {}
    return {}


def run(path, out_dir, recompile: bool = True, limit: int = 40, cases: int = recomp_test.CASES_PER_FUNCTION,
        progress=print, target: str | None = None, runner: list[str] | None = None) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    work = out / "trabalho"
    exe, notes = locate(Path(path))
    for n in notes:
        progress(n)
    progress(f"Identificando {exe.name} (SHA-256 de {exe.stat().st_size:,} bytes)...".replace(",", "."))
    ident = formats.identify(exe)
    rep = {"tool": "GOW3_Native_Analyzer", "version": __version__, "generated_at": report.now(),
           "input": ident, "notes": notes, "param_sfo": find_sfo(exe), "analysis": None, "recompilation_test": None}
    progress(ident["status"])

    elf = None
    if ident.get("ready"):
        if ident["format"] == "ELF":
            elf = exe
        else:  # fSELF de depuração: o ELF é reconstruído sem chave nenhuma
            work.mkdir(parents=True, exist_ok=True)
            elf = work / (exe.stem + ".elf")
            progress("Reconstruindo o ELF do fSELF de depuração (unfself do ps3recomp, sem chaves)...")
            tools.run_tool("unfself", [exe, "-o", elf])
            rep["input"]["unwrapped_elf_sha256"] = formats.sha256_file(elf)

    if elf is not None:
        rep["analysis"] = analysis.analyse(elf, work, progress)
        progress(f"Análise: {rep['analysis']['function_count']} funções, {len(rep['analysis']['candidates'])} candidatas.")
        if recompile:
            try:
                rep["recompilation_test"] = recomp_test.run(elf, rep["analysis"], out, progress, limit=limit,
                                                            cases_per_function=cases, target=target, runner=runner)
            except Exception as error:  # o relatório sai mesmo assim, com o erro registrado
                rep["recompilation_test"] = {"status": "falhou", "error": str(error),
                                             "trace": traceback.format_exc()[-4000:]}
                progress(f"Teste de recompilação falhou: {error}")
    rep["ladder"] = report.ladder(rep)
    progress("Gravando relatórios...")
    rep["files"] = {"json": str(report.write_json(rep, out)), "html": str(report.write_html(rep, out))}
    csv_path = report.write_functions_csv(rep, out)
    if csv_path:
        rep["files"]["csv"] = str(csv_path)
        report.write_json(rep, out)
    return rep
