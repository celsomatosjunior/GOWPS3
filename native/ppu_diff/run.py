#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Teste diferencial da recompilação PPU.

  run.py generate --ps3recomp DIR --out BUNDLE
      (Linux, precisa de powerpc64-linux-gnu-gcc e qemu-ppc64)
      1. compila corpus.c para PowerPC/Cell  -> corpus.elf (código de máquina PowerPC real)
      2. executa corpus.elf no QEMU          -> ref_qemu.txt  (referência: o próprio PowerPC)
      3. compila o mesmo C para o host       -> ref_native.txt (referência secundária)
      4. recompila o PowerPC com o lifter do ps3recomp -> lifted/ppu_recomp.c
      5. gera driver.cpp e copia o runtime mínimo + CMakeLists para BUNDLE

  run.py compare --bundle BUNDLE --output saida_do_executavel.txt
      compara a saída do executável recompilado (Linux ou Windows) com ref_qemu.txt;
      código 0 = idêntico em todos os casos.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def sh(cmd, **kw):
    print("$ " + " ".join(cmd), flush=True)
    result = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if result.returncode != 0:
        raise SystemExit(f"falhou ({result.returncode}): {' '.join(cmd)}\n{result.stdout}\n{result.stderr}")
    return result.stdout


def generate(ps3recomp, out, ppu_cc, qemu, host_cc):
    os.makedirs(out, exist_ok=True)
    python = sys.executable
    sh([python, os.path.join(HERE, "gen.py"), "mains", "--out", out])
    corpus = os.path.join(HERE, "corpus.c")
    shutil.copy2(corpus, out)
    elf = os.path.join(out, "corpus.elf")
    # -mcpu=cell: o compilador gera código para o PPU do Cell (o processador do PS3).
    sh([ppu_cc, "-mcpu=cell", "-mcmodel=small", "-O2", "-static", "-fno-stack-protector", "-o", elf, corpus,
        os.path.join(out, "cases_main.c")])
    ref = sh([qemu, elf])
    open(os.path.join(out, "ref_qemu.txt"), "w").write(ref)
    native = os.path.join(out, "native_ref")
    sh([host_cc, "-O2", "-ffp-contract=off", "-o", native, corpus, os.path.join(out, "cases_main.c")])
    open(os.path.join(out, "ref_native.txt"), "w").write(sh([native]))
    os.remove(native)

    print(sh([python, os.path.join(HERE, "gen.py"), "symbols", "--elf", elf, "--out", out]), end="")
    meta = json.load(open(os.path.join(out, "meta.json")))
    lifted = os.path.join(out, "lifted")
    lift_log = sh([python, os.path.join(ps3recomp, "tools", "ppu_lifter.py"), elf,
                   "--functions", os.path.join(out, "functions.json"),
                   "--code-end", hex(meta["text_end"]),
                   # O ELF de teste usa descritores ELFv1 de 64 bits; o lifter lê o formato do PS3
                   # ({u32 código, u32 TOC}), então o TOC é informado explicitamente.
                   "--toc", hex(next(iter(meta["functions"].values()))["toc"]),
                   "--single-file", "-o", lifted])
    open(os.path.join(out, "lifter.log"), "w").write(lift_log)
    sh([python, os.path.join(HERE, "gen.py"), "driver", "--meta", os.path.join(out, "meta.json"), "--out", out])
    for name in ("guest_runtime.cpp", "guest_runtime.h", "CMakeLists.txt"):
        shutil.copy2(os.path.join(HERE, name), out)
    todo = open(os.path.join(lifted, "ppu_recomp.c")).read().count("/* TODO")
    lines = sum(1 for _ in open(os.path.join(lifted, "ppu_recomp.c")))
    stats = {"functions": len(meta["functions"]), "lifted_c_lines": lines, "todo_markers": todo,
             "cases": len(ref.splitlines())}
    json.dump(stats, open(os.path.join(out, "stats.json"), "w"), indent=1)
    print(f"pacote do teste em {out}: {stats}")


def compare(bundle, output_file):
    ref = open(os.path.join(bundle, "ref_qemu.txt")).read().splitlines()
    got = open(output_file).read().splitlines()
    native = open(os.path.join(bundle, "ref_native.txt")).read().splitlines()
    fails = 0
    for i, expected in enumerate(ref):
        actual = got[i] if i < len(got) else "(ausente)"
        if actual != expected:
            fails += 1
            print(f"DIFERENTE: QEMU {expected}  |  recompilado {actual}")
    if len(got) != len(ref):
        print(f"DIFERENTE: {len(got)} linhas recompiladas, {len(ref)} no QEMU")
        fails += 1
    native_diff = sum(1 for a, b in zip(ref, native) if a != b)
    print(f"Recompilado x PowerPC no QEMU: {len(ref) - fails}/{len(ref)} casos idênticos")
    print(f"(informativo) C nativo x PowerPC no QEMU: {len(ref) - native_diff}/{len(ref)} idênticos "
          "(diferenças em ponto flutuante são esperadas: o PowerPC usa multiplicação-soma fundida)")
    print("RESULTADO: " + ("APROVADO" if fails == 0 else "REPROVADO"))
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--ps3recomp", required=True)
    g.add_argument("--out", required=True)
    g.add_argument("--ppu-cc", default="powerpc64-linux-gnu-gcc")
    g.add_argument("--qemu", default="qemu-ppc64")
    g.add_argument("--host-cc", default="cc")
    c = sub.add_parser("compare")
    c.add_argument("--bundle", required=True)
    c.add_argument("--output", required=True)
    a = ap.parse_args()
    if a.cmd == "generate":
        generate(os.path.abspath(a.ps3recomp), os.path.abspath(a.out), a.ppu_cc, a.qemu, a.host_cc)
        return 0
    return compare(a.bundle, a.output)


if __name__ == "__main__":
    sys.exit(main())
