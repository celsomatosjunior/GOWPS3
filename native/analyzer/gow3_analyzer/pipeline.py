# SPDX-License-Identifier: GPL-2.0-only
"""Fluxo completo: localizar o executável, identificar, analisar, recompilar/testar e gerar relatórios."""

from __future__ import annotations

import traceback
from pathlib import Path

from . import __version__, analysis, capture, decrypt, formats, recomp_test, report, tools

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


def default_captures_dir() -> Path:
    """Pasta fixa das capturas (ao lado do programa): análises seguintes do mesmo EBOOT.ELF as usam."""
    return decrypt.settings_path().parent / "capturas"


def decoder_warning(rpcs3_hint: str | None) -> str | None:
    """O RPCS3 só para nos breakpoints com o PPU Decoder em Interpreter. Confere a configuração do
    jogo (custom_configs) e a global; devolve um aviso se estiver em LLVM."""
    tool = decrypt.find_rpcs3(rpcs3_hint)
    if not tool:
        return None
    base = tool.parent
    files = [base / "config" / "custom_configs" / "config_BCES00510.yml", base / "custom_configs" / "config_BCES00510.yml",
             base / "config" / "config.yml", base / "config.yml"]
    for f in files:
        try:
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip().startswith("PPU Decoder:"):
                    value = line.split(":", 1)[1].strip()
                    if "llvm" in value.lower():
                        return (f"Atenção: o PPU Decoder do RPCS3 está em '{value}' ({f.name}). Os breakpoints só funcionam "
                                "com 'Interpreter (static)': no RPCS3, clique com o botão direito no jogo > Create Custom "
                                "Configuration > CPU > PPU Decoder > Interpreter (static), e reinicie o jogo.")
                    return None
        except OSError:
            continue
    return None


def run(path, out_dir, recompile: bool = True, limit: int = 40, cases: int = recomp_test.CASES_PER_FUNCTION,
        progress=print, target: str | None = None, runner: list[str] | None = None,
        rpcs3: str | None = None, use_rpcs3: bool = True, capture_minutes: float | None = None,
        capture_states: int = 4, gdb_port: int = 2345, captures_dir: Path | None = None) -> dict:
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
            rep["input"]["version_check"] = decrypt.known_elf(ident["sha256"])
        else:  # fSELF de depuração: o ELF é reconstruído sem chave nenhuma
            work.mkdir(parents=True, exist_ok=True)
            elf = work / (exe.stem + ".elf")
            progress("Reconstruindo o ELF do fSELF de depuração (unfself do ps3recomp, sem chaves)...")
            tools.run_tool("unfself", [exe, "-o", elf])
            rep["input"]["unwrapped_elf_sha256"] = formats.sha256_file(elf)

    elif ident.get("encrypted") and ident.get("format") == "SELF" and use_rpcs3:
        # SELF de varejo: o EBOOT.ELF é gerado pelo RPCS3 do próprio usuário (o analisador não decifra)
        tool = decrypt.find_rpcs3(rpcs3)
        conv = {"method": "rpcs3 --decrypt", "rpcs3": str(tool) if tool else None}
        rep["input"]["conversion"] = conv
        if tool is None:
            conv["status"] = "RPCS3 não encontrado"
            rep["input"]["status"] = ("SELF de varejo cifrado. Para gerar o EBOOT.ELF automaticamente, indique o rpcs3.exe "
                                      "instalado no seu computador (botão RPCS3 na janela, ou --rpcs3 na linha de comando). "
                                      "Este programa não decifra nada: quem converte é o seu RPCS3.")
            progress(rep["input"]["status"])
        else:
            work.mkdir(parents=True, exist_ok=True)
            try:
                elf = decrypt.decrypt_with_rpcs3(exe, tool, work, progress)
                decrypt.save_settings({"rpcs3": str(tool)})
                elf_sha = formats.sha256_file(elf)
                conv.update(status="ok", elf=str(elf), elf_sha256=elf_sha)
                conv["version_check"] = decrypt.known_version(ident["sha256"], elf_sha)
                vc = conv["version_check"]
                if vc.get("known"):
                    msg = (f"Versão reconhecida: {vc['title']} {vc['title_id']} {vc['version']}; EBOOT.ELF "
                           + ("idêntico ao já verificado." if vc.get("elf_matches") else "DIFERENTE do verificado (confira a cópia)."))
                else:
                    msg = "EBOOT.ELF gerado; esta versão do EBOOT.BIN não está na lista de versões conferidas."
                conv["message"] = msg
                rep["input"]["ready"] = True
                rep["input"]["status"] = "EBOOT.ELF gerado pelo seu RPCS3: pronto para análise. " + msg
                progress(rep["input"]["status"])
            except decrypt.DecryptError as error:
                conv.update(status="falhou", error=str(error))
                rep["input"]["status"] = "Não foi possível gerar o EBOOT.ELF: " + str(error)
                progress(rep["input"]["status"])

    if elf is not None:
        rep["analysis"] = analysis.analyse(elf, work, progress)
        progress(f"Análise: {rep['analysis']['function_count']} funções, {len(rep['analysis']['candidates'])} candidatas.")
        cdir = Path(captures_dir) if captures_dir else default_captures_dir()
        elf_sha = formats.sha256_file(elf)
        if capture_minutes:
            warn = decoder_warning(rpcs3)
            if warn:
                progress(warn)
            try:
                summary = capture.capture(elf, rep["analysis"]["candidates"][:limit], cdir, port=gdb_port,
                                          minutes=capture_minutes, per_function=capture_states, progress=progress)
                if warn:
                    summary["decoder_warning"] = warn
                progress(f"Captura: {summary['states']} estados reais de {summary['functions_captured']} funções.")
                progress("Pode fechar o jogo no RPCS3 (e voltar o PPU Decoder para 'Recompiler (LLVM)').")
                if summary["states"] == 0:
                    progress("Nenhuma função parou. Confira se o PPU Decoder do RPCS3 está em 'Interpreter' e se você "
                             "jogou durante a captura.")
            except capture.GdbError as error:
                rep["capture_error"] = str(error)
                progress(f"Captura não feita: {error}")
        captured = None
        loaded = capture.load(cdir / capture.CAPTURE_FILE, elf_sha)
        if loaded:
            rep["captures"], captured = loaded[0], loaded[1]
            progress(f"Usando {len(captured)} estados reais capturados em {rep['captures']['created']}.")
        if recompile:
            try:
                rep["recompilation_test"] = recomp_test.run(elf, rep["analysis"], out, progress, limit=limit,
                                                            cases_per_function=cases, target=target, runner=runner,
                                                            captured=captured)
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
