#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Autoteste do analisador sem nenhum arquivo do jogo (roda no CI público).

1. ELF sintético no formato de EBOOT do PS3 (corpus do projeto): análise + recompilação + teste
   diferencial. Esperado: todas as funções candidatas idênticas à referência.
2. Teste de mutação: um erro proposital é colocado no código recompilado de uma função. Esperado:
   o teste acusa divergência nessa função e só nela. (Mostra que a comparação detecta erros.)
3. SELF de varejo sintético: esperado "cifrado", sem análise e sem tentativa de decifrar.

    python run_synthetic.py ps3_test.elf fake_retail.BIN saida/ [--exe GOW3_Native_Analyzer.exe]
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from gow3_analyzer import pipeline, recomp_test  # noqa: E402

MUTANT = "func_10001938"  # mul64 do corpus: termina com add r3,r9,r10


def mutate(path: Path):
    src = path.read_text(encoding="latin-1")  # o lifter grava na codificação local (cp1252 no Windows)
    m = re.search(r"void %s\(ppu_context\* ctx\)\s*\{" % MUTANT, src)
    assert m, "função do teste de mutação não encontrada no código gerado"
    body_start = m.end()
    i = src.index("ctx->gpr[3] = ", body_start)
    src = src[:i] + "ctx->gpr[3] = 1 ^ " + src[i + len("ctx->gpr[3] = "):]
    path.write_text(src, encoding="latin-1")


def check(cond, msg, failures):
    print(("OK    " if cond else "FALHA ") + msg)
    if not cond:
        failures.append(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("elf")
    ap.add_argument("fake_self")
    ap.add_argument("out")
    ap.add_argument("--exe", help="testar também o executável empacotado")
    ap.add_argument("--grande", help="ELF com ~900 funções (make_ps3_test_elf.py --todas): recompilar 40 delas")
    ap.add_argument("--exe-extra", default="", help="argumentos extras para o executável (ex.: '--alvo x86_64-windows-gnu --executor wine')")
    args = ap.parse_args()
    out = Path(args.out)
    failures = []
    summary = {}

    rep = pipeline.run(args.elf, out / "fonte", progress=lambda m: print("  " + m))
    t = rep["recompilation_test"]["totals"]
    summary["source"] = t
    check(rep["analysis"]["function_count"] >= 18, f"análise: {rep['analysis']['function_count']} funções", failures)
    check(t["functions"] >= 10 and t["identical_functions"] == t["functions"],
          f"recompilação: {t['identical_functions']}/{t['functions']} funções idênticas, "
          f"{t['identical_cases']}/{t['cases']} casos", failures)

    rt = recomp_test.run(Path(args.elf), rep["analysis"], out / "mutacao", lambda m: None, mutate=mutate)
    bad = sorted(f["func"] for f in rt["functions"] if f["status"] == "divergente")
    summary["mutation"] = {"divergent": bad, "totals": rt["totals"]}
    check(bad == [MUTANT], f"mutação: divergência detectada em {bad} (esperado [{MUTANT}])", failures)

    if args.grande:
        # Poucas funções escolhidas num executável grande, como no jogo (40 de 11.060). Antes da
        # correção do lifter isso gerava centenas de MB (2,39 GB no God of War III).
        repg = pipeline.run(args.grande, out / "grande", progress=lambda m: None)
        rtg = repg.get("recompilation_test") or {}
        tg = rtg.get("totals") or {}
        lifted = out / "grande" / "recomp_test" / "lifted" / "ppu_recomp.c"
        size = lifted.stat().st_size if lifted.is_file() else -1
        summary["large"] = {"functions": repg["analysis"]["function_count"], "lifted_bytes": size, "totals": tg,
                            "status": rtg.get("status"), "error": rtg.get("error")}
        check(rtg.get("status") == "executado" and 0 < size < 32 * 1024 * 1024,
              f"executável grande ({repg['analysis']['function_count']} funções): {tg.get('functions')} recompiladas, "
              f"código gerado {size / 1e6:.1f} MB", failures)
        check(tg.get("identical_functions", 0) >= 15 and tg.get("incomplete_translation_functions", 1) == 0,
              f"executável grande: {tg.get('identical_functions')} idênticas, {tg.get('divergent_functions')} divergentes, "
              f"{tg.get('inconclusive_functions')} inconclusivas", failures)

    rep2 = pipeline.run(args.fake_self, out / "self_varejo", progress=lambda m: None)
    summary["retail_self"] = {"encrypted": rep2["input"].get("encrypted"), "ready": rep2["input"].get("ready"),
                              "status": rep2["input"].get("status")}
    check(rep2["input"].get("encrypted") is True and rep2["input"].get("ready") is False and rep2["analysis"] is None
          and (rep2["input"].get("elf") or {}).get("machine_id") == 21,
          "SELF de varejo: reconhecido como cifrado e não analisado", failures)

    if args.exe:
        exe_out = out / "exe"
        proc = subprocess.run([args.exe, "analisar", args.elf, "--saida", str(exe_out)] + args.exe_extra.split(), capture_output=True, text=True,
                              timeout=1800)
        print(f"código de saída do .exe: {proc.returncode}")
        print(proc.stdout[-2000:], proc.stderr[-2000:])
        if (exe_out / "analise.log").is_file():
            print("--- analise.log\n" + (exe_out / "analise.log").read_text(encoding="utf-8", errors="replace")[-4000:])
        rj = exe_out / "relatorio_gow3.json"
        j = json.loads(rj.read_text(encoding="utf-8")) if rj.is_file() else {}
        te = (j.get("recompilation_test") or {}).get("totals") or {}
        summary["exe"] = te or j.get("recompilation_test")
        check(proc.returncode == 0 and te.get("functions", 0) >= 10 and te.get("identical_functions") == te.get("functions"),
              f"executável empacotado: código {proc.returncode}, {te.get('identical_functions')}/{te.get('functions')} "
              f"funções idênticas", failures)
        check((exe_out / "relatorio_gow3.html").is_file(), "executável empacotado: relatório HTML gerado", failures)
        if args.grande:
            proc = subprocess.run([args.exe, "analisar", args.grande, "--saida", str(out / "exe_grande")] +
                                  args.exe_extra.split(), capture_output=True, text=True, timeout=3600)
            rj = out / "exe_grande" / "relatorio_gow3.json"
            jg = json.loads(rj.read_text(encoding="utf-8")) if rj.is_file() else {}
            tg = (jg.get("recompilation_test") or {}).get("totals") or {}
            summary["exe_large"] = tg or jg.get("recompilation_test")
            check(proc.returncode == 0 and tg.get("identical_functions", 0) >= 15,
                  f"executável empacotado, ELF grande: código {proc.returncode}, {tg.get('identical_functions')}/"
                  f"{tg.get('functions')} idênticas", failures)
        proc = subprocess.run([args.exe, "analisar", args.fake_self, "--saida", str(out / "exe_self")],
                              capture_output=True, text=True, timeout=600)
        j = json.loads((out / "exe_self" / "relatorio_gow3.json").read_text(encoding="utf-8"))
        check(proc.returncode == 4 and j["input"]["encrypted"] and not j["input"]["ready"],
              f"executável empacotado com SELF de varejo: código {proc.returncode} (esperado 4), sem análise", failures)

    summary["failures"] = failures
    (out / "autoteste.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print("\nAUTOTESTE: " + ("tudo certo" if not failures else f"{len(failures)} falha(s)"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
