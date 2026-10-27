# SPDX-License-Identifier: GPL-2.0-only
"""Recompilação das funções candidatas e teste diferencial contra a CPU de referência.

1. O lifter do ps3recomp converte as funções escolhidas (código PowerPC do ELF) em C++.
2. O zig (clang empacotado) compila esse C++ com o runtime mínimo num executável Windows x64
   separado: GOW3_Native_RecompTest.exe.
3. Para cada função são gerados estados iniciais determinísticos (registradores + memória). O mesmo
   estado é dado ao executável recompilado e ao executor de referência (Unicorn, que roda o código
   de máquina original).
4. Os estados finais são comparados: 32 GPRs, 32 FPRs (bit a bit), CR, XER[SO/OV/CA], CTR, LR,
   quantidade, posição e resumo (FNV-1a) de todos os bytes escritos na memória. Falha de acesso nos
   dois lados conta como comportamento igual só quando o tipo de falha é o mesmo.

Tudo fica gravado em arquivos de texto para repetir a comparação: casos.txt, resultados_*.txt,
divergencias.txt, lifter.log e compilacao.log.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import state as S
from . import tools
from .analysis import ElfImage
from .reference import Reference

CASES_PER_FUNCTION = 64
RUN_TIMEOUT = 60  # segundos por lote; um caso que trava é marcado e o lote continua do seguinte
REGISTER_FIELDS = [f"r{i}" for i in range(32)] + [f"f{i}" for i in range(32)] + ["cr", "xer", "ctr", "lr", "mem"]


def zig_command() -> list[str]:
    bundled = tools.resource_dir() / "ziglang" / ("zig.exe" if os.name == "nt" else "zig")
    if bundled.is_file():
        return [str(bundled)]
    if getattr(sys, "frozen", False):
        raise FileNotFoundError("compilador zig não encontrado no pacote")
    return [sys.executable, "-m", "ziglang"]


def runtime_source() -> Path:
    return tools.resource_dir() / "runtime" / "recomp_test_runtime.cpp"


def host_target() -> str:
    if os.name == "nt":
        return "x86_64-windows-gnu"
    return {"x86_64": "x86_64-linux-gnu", "aarch64": "aarch64-linux-gnu"}.get(platform.machine(), "native")


MAX_LIFTED_BYTES = 64 * 1024 * 1024  # bem acima do esperado para dezenas de funções folha


def masked_elf(elf: Path, analysis: dict, candidates: list[dict], dst: Path) -> dict:
    """Cópia do ELF em que só o código das funções escolhidas permanece; o código das outras
    funções vira zero. Dados, tabelas de salto e constantes ficam intactos.

    Motivo: o lifter do ps3recomp estende os fragmentos que descobre (casos de switch, entradas no
    meio de funções) até a próxima função da lista. Com uma lista esparsa (40 de 11.060 funções) cada
    fragmento chega a megabytes e o resultado explode: 2,39 GB de C++ para 40 funções do God of War
    III. Sem o código das outras funções não há o que estender."""
    import struct
    data = bytearray(elf.read_bytes())
    phoff = struct.unpack_from(">Q", data, 0x20)[0]
    phentsize, phnum = struct.unpack_from(">HH", data, 0x36)
    segs = []
    for i in range(phnum):
        p_type, flags, off, vaddr, _pa, filesz, _m, _a = struct.unpack_from(">IIQQQQQQ", data, phoff + i * phentsize)
        if p_type == 1 and flags & 1:
            segs.append((vaddr, off, filesz))
    keep = [(int(c["start"], 16), int(c["end"], 16)) for c in candidates]
    zeroed = 0
    for f in analysis.get("functions", []):
        a, b = int(f["start"], 16), int(f["end"], 16)
        if any(a < ke and b > ks for ks, ke in keep):
            continue
        for vaddr, off, filesz in segs:
            lo, hi = max(a, vaddr), min(b, vaddr + filesz)
            if lo < hi:
                data[off + lo - vaddr:off + hi - vaddr] = bytes(hi - lo)
                zeroed += hi - lo
    dst.write_bytes(bytes(data))
    return {"zeroed_code_bytes": zeroed, "kept_functions": len(keep)}


def lift(elf: Path, candidates: list[dict], toc: int | None, out: Path, code_end: int | None,
         analysis: dict | None = None) -> str:
    out.mkdir(parents=True, exist_ok=True)
    flist = out / "funcoes_escolhidas.json"
    flist.write_text(json.dumps([{"start": c["start"], "end": c["end"]} for c in candidates], indent=1))
    lift_input = elf
    note = ""
    if analysis and analysis.get("functions"):
        lift_input = out / "entrada_lifter.elf"
        info = masked_elf(elf, analysis, candidates, lift_input)
        note = (f"entrada do lifter: código de {len(analysis['functions']) - info['kept_functions']} outras funções "
                f"zerado ({info['zeroed_code_bytes']} bytes); só as {info['kept_functions']} escolhidas ficam\n")
    argv = [lift_input, "--functions", flist, "--single-file", "--jobs", "1", "-o", out / "lifted"]
    if toc is not None:
        argv += ["--toc", hex(toc)]
    if code_end:
        argv += ["--code-end", hex(code_end)]
    log = note + tools.run_tool("ppu_lifter", argv)
    if lift_input != elf:
        lift_input.unlink()  # cópia derivada do jogo: não fica no disco
    (out / "lifter.log").write_text(log, encoding="utf-8")
    size = (out / "lifted" / "ppu_recomp.c").stat().st_size
    if size > MAX_LIFTED_BYTES:
        raise RuntimeError(f"o lifter gerou {size / 1e6:.0f} MB de C++ para {len(candidates)} funções; "
                           "isso indica fragmentos estendidos além das funções escolhidas (veja lifter.log)")
    return log


def lifter_todos(lifted_c: Path, funcs: list[str]) -> dict[str, int]:
    """Quantas instruções de cada função o lifter deixou como comentário TODO (não traduzidas)."""
    import re
    text = lifted_c.read_text(encoding="latin-1")
    out = {}
    for name in funcs:
        m = re.search(r"^void %s\(ppu_context\* ctx\)\s*\{" % name, text, re.M)
        if not m:
            continue
        end = text.find("\n}\n", m.end())
        body = text[m.end():end if end > 0 else len(text)]
        # ".word" é dado/preenchimento depois do blr (nunca executado); o resto é instrução não traduzida
        out[name] = sum(1 for t in re.findall(r"/\* TODO: (\S+)", body) if not t.startswith("."))
    return out


def compile_test_exe(out: Path, target: str, exe_name: str) -> Path:
    lifted = out / "lifted"
    exe = out / exe_name
    cmd = zig_command() + ["c++", "-target", target, "-std=c++20", "-O1", "-w", "-fno-strict-aliasing",
                           "-DPPU_NO_INLINE_LOADS", "-DPPU_NO_INLINE_STORES",
                           "-I", str(lifted), "-I", str(tools.ps3recomp_root() / "runtime" / "ppu"), "-x", "c++", str(lifted / "ppu_recomp.c"),
                           str(runtime_source()), "-o", str(exe)]
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    (out / "compilacao.log").write_text(" ".join(cmd) + "\n\n" + proc.stdout + proc.stderr +
                                        f"\n(código {proc.returncode}, {time.time() - t0:.1f} s)\n", encoding="utf-8")
    if proc.returncode != 0 or not exe.is_file():
        raise RuntimeError("a compilação do código recompilado falhou; veja compilacao.log:\n" + (proc.stderr or proc.stdout)[-3000:])
    return exe


def run_recompiled(exe: Path, elf: Path, cases_file: Path, results_file: Path, total: int, runner: list[str]) -> list[str]:
    """Roda o executável; se ele travar ou cair num caso, marca o caso e continua do seguinte."""
    if results_file.exists():
        results_file.unlink()
    first = 0
    lines: list[str] = []
    while first < total:
        cmd = runner + [str(exe), str(elf), str(cases_file), str(results_file), str(first)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=RUN_TIMEOUT,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            code = proc.returncode
        except subprocess.TimeoutExpired:
            code = "timeout"
        lines = results_file.read_text(encoding="utf-8", errors="replace").splitlines() if results_file.exists() else []
        if len(lines) >= total:
            break
        if code == 0 and len(lines) < total:
            raise RuntimeError(f"o executável terminou sem gravar todos os casos ({len(lines)}/{total})")
        # o caso de índice len(lines) travou (timeout) ou derrubou o processo
        with open(results_file, "a", encoding="utf-8") as f:
            f.write(f"func ? case ? {'timeout' if code == 'timeout' else 'crash'} {code}\n")
        lines = results_file.read_text(encoding="utf-8").splitlines()
        first = len(lines)
    return lines


def parse_result(line: str) -> dict:
    t = line.split()
    if "ok" not in t:
        for kind in ("fault", "timeout", "crash", "missing"):
            if kind in t:
                i = t.index(kind)
                return {"status": kind, "kind": t[i + 1] if kind == "fault" and i + 1 < len(t) else kind}
        return {"status": "invalid"}
    i = t.index("ok")
    v = t[i + 1:]
    gpr = v[v.index("gpr") + 1:v.index("gpr") + 33]
    fpr = v[v.index("fpr") + 1:v.index("fpr") + 33]
    out = {"status": "ok"}
    for k in range(32):
        out[f"r{k}"] = int(gpr[k], 16)
        out[f"f{k}"] = int(fpr[k], 16)
    for key in ("cr", "xer", "ctr", "lr"):
        out[key] = int(v[v.index(key) + 1], 16)
    m = v.index("mem")
    out["mem"] = (int(v[m + 1]), int(v[m + 2], 16), int(v[v.index("first") + 1], 16))
    return out


def compare(rec: dict, ref: dict, fctiw: bool = False) -> tuple[str, list[dict]]:
    """Compara dois estados finais. Com `fctiw`, uma diferença só nos 32 bits altos de um FPR não é
    divergência: o ISA (Book I, fctiw/fctiwz) deixa esses bits indefinidos."""
    if rec["status"] != "ok" or ref["status"] != "ok":
        if rec["status"] == "fault" and ref["status"] == "fault" and rec["kind"] == ref["kind"]:
            return "ambos-falharam", []
        if rec["status"] == "timeout" and ref["status"] == "fault" and ref["kind"] == "timeout":
            return "ambos-sem-fim", []
        if rec["status"] == "ok" and ref["status"] == "fault" and ref["kind"] == "timeout":
            # o recompilado terminou; a referência (muito mais lenta) não terminou nem com o limite longo:
            # nada foi comparado, então não é divergência
            return "limite-da-referência", []
        return "divergente", [{"campo": "execução", "recompilado": rec.get("kind", rec["status"]),
                               "referência": ref.get("kind", ref["status"])}]
    diffs = []
    undefined = []
    for field in REGISTER_FIELDS:
        a, b = rec[field], ref[field]
        if a != b and fctiw and field.startswith("f") and (a & 0xFFFFFFFF) == (b & 0xFFFFFFFF):
            undefined.append(field)
            continue
        if a != b:
            fmt = (lambda x: "%d bytes, resumo %x, primeiro %x" % x) if field == "mem" else (lambda x: f"0x{x:X}")
            diffs.append({"campo": field, "recompilado": fmt(a), "referência": fmt(b)})
    if diffs:
        return "divergente", diffs
    return ("idêntico-com-bits-indefinidos" if undefined else "idêntico"), [{"campo": f} for f in undefined]


def reference_line(addr: int, case: dict, outcome: dict) -> str:
    return f"func {addr:08X} " + S.format_result(case["id"], outcome)


def run(elf: Path, analysis: dict, work: Path, progress=lambda m: None, limit: int = 40,
        cases_per_function: int = CASES_PER_FUNCTION, target: str | None = None, runner: list[str] | None = None,
        exe_name: str = "GOW3_Native_RecompTest.exe", mutate=None, captured: list[dict] | None = None) -> dict:
    """Executa todo o teste e devolve a seção 'recompilation_test' do relatório."""
    out = work / "recomp_test"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    candidates = analysis["candidates"][:limit]
    if not candidates:
        return {"status": "sem candidatas", "functions": []}
    def as_int(v):
        return int(v, 16) if isinstance(v, str) else v

    tocs = sorted({as_int(c["toc"]) for c in candidates if c.get("toc") is not None})
    toc = tocs[0] if tocs else None
    image = ElfImage(elf)
    code_end = max((s["vaddr"] + s["filesz"] for s in image.loads if s["flags"] & 1), default=None)

    progress(f"Recompilando {len(candidates)} funções com o lifter do ps3recomp...")
    lift(elf, candidates, toc, out, code_end, analysis)
    if mutate is not None:  # só para o autoteste: introduz um erro proposital no código gerado
        mutate(out / "lifted" / "ppu_recomp.c")
    exe_target = target or host_target()
    todos = lifter_todos(out / "lifted" / "ppu_recomp.c", [c["func"] for c in candidates])
    progress(f"Compilando o código recompilado para {exe_target} (zig/clang)... na primeira vez leva alguns minutos")
    exe = compile_test_exe(out, exe_target, exe_name)

    progress("Gerando estados iniciais...")
    cases_lines, plan = [], []
    for idx, c in enumerate(candidates):
        addr = int(c["start"], 16)
        ctoc = as_int(c.get("toc")) if c.get("toc") is not None else (toc or 0)
        for case in S.make_cases(ctoc, cases_per_function, base_seed=addr):
            cases_lines.append(f"run {addr:08X} " + S.format_case(case))
            plan.append((c, addr, case))
        for n, cap in enumerate(x for x in (captured or []) if x.get("addr") == addr):
            case = S.real_case(n, cap)
            if case is not None:
                cases_lines.append(f"run {addr:08X} " + S.format_case(case))
                plan.append((c, addr, case))
    cases_file = out / "casos.txt"
    cases_file.write_text("\n".join(cases_lines) + "\n")

    progress(f"Executando {len(plan)} casos no executável recompilado...")
    rec_lines = run_recompiled(exe, elf, cases_file, out / "resultados_recompilado.txt", len(plan), runner or [])

    progress(f"Executando os mesmos {len(plan)} casos na CPU de referência (código PowerPC original)...")
    ref = Reference(image)
    ref_lines = []
    for n, (c, addr, case) in enumerate(plan):
        ref_lines.append(reference_line(addr, case, ref.run(addr, case, code_end=int(c["end"], 16))))
        if n % 100 == 99:
            progress(f"  referência: {n + 1}/{len(plan)}")
    # casos em que só a referência atingiu o limite de instruções: repetir com limite muito maior
    retry = [n for n, (rl, fl) in enumerate(zip(rec_lines, ref_lines))
             if parse_result(rl)["status"] == "ok" and parse_result(fl).get("kind") == "timeout"]
    if retry:
        progress(f"Repetindo {len(retry)} caso(s) na referência com limite de {S.INSTRUCTION_LIMIT_LONG // 1_000_000} milhões de instruções...")
        for n in retry:
            c, addr, case = plan[n]
            ref_lines[n] = reference_line(addr, case, ref.run(addr, case, code_end=int(c["end"], 16),
                                                              limit=S.INSTRUCTION_LIMIT_LONG))
    (out / "resultados_referencia.txt").write_text("\n".join(ref_lines) + "\n")

    progress("Comparando...")
    fctiw_funcs = {addr for (c, addr, _case) in plan
                   if any(w == 32 for (_a, _w, w, _z) in ref._fcti_sites(addr, int(c["end"], 16)))}
    per_func: dict[int, dict] = {}
    div_log = []
    for (c, addr, case), rl, fl in zip(plan, rec_lines, ref_lines):
        f = per_func.setdefault(addr, {"func": c["func"], "start": c["start"], "end": c["end"], "insns": c["insns"],
                                       "why": c["why"], "cases": 0, "identical": 0, "both_faulted": 0, "undefined_bits_only": 0, "reference_limit": 0,
                                       "real_cases": 0, "real_identical": 0, "real_both_faulted": 0, "real_divergent": 0,
                                       "divergent": 0, "divergences": []})
        f["cases"] += 1
        verdict, diffs = compare(parse_result(rl), parse_result(fl), addr in fctiw_funcs)
        if case.get("real"):
            f["real_cases"] += 1
            key = ("real_identical" if verdict.startswith("idêntico") else "real_divergent" if verdict == "divergente"
                   else "real_both_faulted")
            f[key] += 1
        if verdict.startswith("idêntico"):
            f["identical"] += 1
            if verdict != "idêntico":
                f["undefined_bits_only"] += 1
        elif verdict in ("ambos-falharam", "ambos-sem-fim"):
            f["both_faulted"] += 1
        elif verdict == "limite-da-referência":
            f["reference_limit"] += 1
        else:
            f["divergent"] += 1
            if len(f["divergences"]) < 5:
                f["divergences"].append({"case": case["id"], "seed": f"{case['seed']:x}", "diffs": diffs[:8]})
            div_log.append(f"{c['func']} caso {case['id']} (semente {case['seed']:x}):")
            div_log += [f"    {d['campo']}: recompilado={d['recompilado']} referência={d['referência']}" for d in diffs]
    (out / "divergencias.txt").write_text("\n".join(div_log) + ("\n" if div_log else "nenhuma divergência\n"), encoding="utf-8")

    functions = []
    for f in per_func.values():
        f["lifter_todos"] = todos.get(f["func"], 0)
        if f["lifter_todos"]:
            f["status"] = "tradução incompleta"  # o lifter não traduziu alguma instrução
        elif f["divergent"]:
            f["status"] = "divergente"
        elif f["identical"] == 0:
            f["status"] = "inconclusiva"  # todos os casos falharam igualmente nos dois lados
        else:
            f["status"] = "idêntica"
        functions.append(f)
    totals = {
        "functions": len(functions),
        "identical_functions": sum(1 for f in functions if f["status"] == "idêntica"),
        "divergent_functions": sum(1 for f in functions if f["status"] == "divergente"),
        "inconclusive_functions": sum(1 for f in functions if f["status"] == "inconclusiva"),
        "incomplete_translation_functions": sum(1 for f in functions if f["status"] == "tradução incompleta"),
        "cases": len(plan),
        "identical_cases": sum(f["identical"] for f in functions),
        "both_faulted_cases": sum(f["both_faulted"] for f in functions),
        "divergent_cases": sum(f["divergent"] for f in functions),
        "cases_differing_only_in_isa_undefined_bits": sum(f["undefined_bits_only"] for f in functions),
        "reference_limit_cases": sum(f["reference_limit"] for f in functions),
        "real_cases": sum(f["real_cases"] for f in functions),
        "real_identical_cases": sum(f["real_identical"] for f in functions),
        "real_divergent_cases": sum(f["real_divergent"] for f in functions),
        "functions_with_real_identical": sum(1 for f in functions if f["real_identical"]),
        "reference_retried_cases": len(retry),
    }
    return {
        "status": "executado",
        "method": ("Execução diferencial por estado: o mesmo estado inicial (registradores e memória) é dado ao "
                   "código recompilado (x86-64) e ao código PowerPC original rodando na CPU de referência "
                   "(Unicorn/QEMU). Comparam-se todos os registradores inteiros e de ponto flutuante, CR, XER, CTR, "
                   "LR e todos os bytes escritos na memória."),
        "reference": "Unicorn 2.1 (QEMU TCG), PowerPC 64 bits big-endian, validado contra o qemu-ppc64 no CI",
        "test_executable": exe.name,
        "target": exe_target,
        "cases_per_function": cases_per_function,
        "totals": totals,
        "functions": functions,
        "files": ["casos.txt", "resultados_recompilado.txt", "resultados_referencia.txt", "divergencias.txt",
                  "lifter.log", "compilacao.log", "funcoes_escolhidas.json"],
        "limitations": [
            "Testa funções isoladas (folhas): sem chamadas a outras funções, ao sistema (syscalls/NIDs) ou VMX.",
            "A referência executa até 5 milhões de instruções por caso. Se só ela atingir o limite (o recompilado "
            "terminou), o caso é repetido com 400 milhões; se ainda assim não terminar, conta como 'sem fim só na "
            "referência': nada foi comparado, não é divergência.",
            "Os estados iniciais são sintéticos (aleatórios com semente fixa); não reproduzem o estado do jogo em "
            "execução, então mostram equivalência do código traduzido, não que o jogo funcione.",
            "O FPSCR e os registradores vetoriais não são comparados (a referência não expõe VMX).",
            "Após fctiw/fctiwz os 32 bits altos do FPR são indefinidos pelo ISA; diferença só neles é contada à "
            "parte (undefined_bits_only), não como igualdade plena nem como divergência.",
            "Correção na referência: o Unicorn 2.1 (QEMU 5) devolve 0x80000000 em todo fcti* fora do intervalo; "
            "nesses casos a referência aplica a saturação do ISA (Book I 4.6.7).",
            "Memória de teste em 4 modos (4 casos cada): bytes aleatórios; só ponteiros válidos; e dois mistos, em "
            "que cada palavra de 32 bits é um ponteiro válido, um número pequeno (índice/contador) ou um float "
            "pequeno. Nos modos com ponteiros, a área .bss (globais que o jogo preenche ao rodar) recebe palavras do "
            "mesmo tipo em vez de zeros. É um estado sintético, idêntico nos dois lados: serve para comparar a "
            "tradução, não reproduz o jogo.",
            "'Tradução incompleta': o lifter deixou alguma instrução como comentário TODO (não traduzida).",
            "Uma função 'inconclusiva' falhou da mesma forma nos dois lados em todos os casos (ex.: precisa de "
            "ponteiros para estruturas reais do jogo).",
        ],
    }
