#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Teste da geração automática do EBOOT.ELF com um RPCS3 de verdade (sem arquivos do jogo).

1. SELF de depuração (make_debug_self.py) do ELF de teste -> `rpcs3 --no-gui --decrypt` -> o ELF
   gerado tem de ser idêntico, byte a byte, ao ELF de teste.
2. SELF de varejo sintético (make_fake_self.py, não é jogo nenhum) -> o RPCS3 não consegue
   converter; o analisador tem de dizer isso claramente e não analisar nada.
3. (opcional) o mesmo do item 2 pelo .exe empacotado, com --rpcs3.

    python test_rpcs3.py rpcs3.exe ps3_test.elf debug.BIN fake_retail.BIN saida/ [--exe GOW3_Native_Analyzer.exe]
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from gow3_analyzer import decrypt, pipeline  # noqa: E402


def check(cond, msg, failures):
    print(("OK    " if cond else "FALHA ") + msg)
    if not cond:
        failures.append(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rpcs3")
    ap.add_argument("elf")
    ap.add_argument("debug_self")
    ap.add_argument("fake_self")
    ap.add_argument("out")
    ap.add_argument("--exe")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    summary: dict = {}

    found = decrypt.find_rpcs3(args.rpcs3)
    check(found is not None, f"RPCS3 localizado: {found}", failures)

    w = out / "rpcs3_debug"
    w.mkdir(parents=True, exist_ok=True)
    try:
        elf = decrypt.decrypt_with_rpcs3(Path(args.debug_self), Path(args.rpcs3), w, print)
        got, want = elf.read_bytes(), Path(args.elf).read_bytes()
        same = got == want
        err = None
        if not same:
            first = next((i for i in range(min(len(got), len(want))) if got[i] != want[i]), min(len(got), len(want)))
            err = f"ELF gerado com {len(got)} bytes (esperado {len(want)}), primeira diferença em 0x{first:X}"
    except decrypt.DecryptError as error:
        same, err = False, str(error)
    summary["debug_self"] = {"identical": same, "error": err}
    log = w / "rpcs3_conversao.log"
    if log.is_file():
        print(log.read_text(encoding="utf-8", errors="replace")[-1500:])
    check(same, "RPCS3 de verdade: SELF de depuração convertido em ELF idêntico ao original"
          + (f" ({err})" if err else ""), failures)

    rep = pipeline.run(args.fake_self, out / "varejo", progress=print, rpcs3=args.rpcs3)
    conv = rep["input"].get("conversion") or {}
    summary["retail_fake"] = conv
    check(conv.get("status") == "falhou" and rep["analysis"] is None,
          f"SELF de varejo sintético: conversão recusada e explicada ({conv.get('status')})", failures)

    if args.exe:
        proc = subprocess.run([args.exe, "analisar", args.fake_self, "--saida", str(out / "exe_varejo"),
                               "--rpcs3", args.rpcs3], capture_output=True, text=True, timeout=900)
        j = json.loads((out / "exe_varejo" / "relatorio_gow3.json").read_text(encoding="utf-8"))
        c = j["input"].get("conversion") or {}
        summary["exe_retail_fake"] = {"returncode": proc.returncode, "conversion": c}
        check(proc.returncode == 4 and c.get("status") == "falhou",
              f".exe com --rpcs3 e SELF de varejo sintético: código {proc.returncode}, conversão {c.get('status')}",
              failures)

    (out / "teste_rpcs3.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print("\nTESTE RPCS3: " + ("tudo certo" if not failures else f"{len(failures)} falha(s)"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
