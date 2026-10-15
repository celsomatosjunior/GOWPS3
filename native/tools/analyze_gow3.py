#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Análise do executável do God of War III (PS3) para a recompilação estática.

    python native/tools/analyze_gow3.py <pasta do jogo | EBOOT.BIN | EBOOT.ELF>
            --ps3recomp <clone do ps3recomp> --out <pasta do relatório> [--lift-sample N]

O que faz, sem decifrar nada:
  * lê o PARAM.SFO (serial, título, versão);
  * lê os cabeçalhos que o formato SELF guarda em texto aberto no EBOOT.BIN e nos .sprx/.self
    (tipo, revisão de chave, versão, cabeçalho ELF, segmentos, quais estão cifrados);
  * fSELF de depuração (revisão 0x8000, sem cifra) é desembrulhado com o unfself.py do ps3recomp.

Com um EBOOT.ELF já decifrado e preparado pelo usuário, roda também o pipeline do ps3recomp:
  * ppu_loader.py   -> funções (OPD), TOC, segmentos, importações por biblioteca (NID)
  * NIDs nomeados e marcados como implementados ou não no runtime HLE do ps3recomp
  * extract_spu_images.py -> programas SPU embutidos
  * --lift-sample N -> recompila N funções PPU para C com o ppu_lifter (só tradução; nada é executado)

Este script NUNCA decifra SELF de varejo e não contém chaves. Nada do jogo é copiado para o
relatório além de números, endereços, nomes de bibliotecas e NIDs.
"""

import argparse
import datetime
import hashlib
import json
import os
import struct
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCE_MAGIC = b"SCE\x00"
PT_NAMES = {1: "LOAD", 4: "NOTE", 7: "TLS", 0x60000001: "PRX_PARAM (proc_param)", 0x60000002: "PROC_PRX_PARAM",
            0x700000A4: "SCE_PPURELA", 0x700000A8: "SCE_SEGSYM"}
SELF_TYPES = {1: "LV0", 2: "LV1", 3: "LV2", 4: "aplicativo", 5: "módulo isolado SPU", 6: "secure loader",
              8: "NPDRM (PSN)"}


# ---------------------------------------------------------------- PARAM.SFO
def read_sfo(path):
    d = Path(path).read_bytes()
    if d[:4] != b"\x00PSF":
        return {}
    key_table, data_table, count = struct.unpack_from("<III", d, 8)
    out = {}
    for i in range(count):
        key_off, fmt, size, _max, data_off = struct.unpack_from("<HHIII", d, 20 + i * 16)
        end = d.index(b"\0", key_table + key_off)
        key = d[key_table + key_off:end].decode("ascii", "replace")
        raw = d[data_table + data_off:data_table + data_off + size]
        out[key] = struct.unpack("<I", raw)[0] if fmt == 0x0404 else raw.split(b"\0")[0].decode("utf-8", "replace")
    return out


# ---------------------------------------------------------------- ELF / SELF headers
def elf_summary(d, base=0):
    """Cabeçalho ELF64 big-endian e segmentos (lidos de d[base:])."""
    if d[base:base + 4] != b"\x7fELF":
        return None
    e_type, e_machine = struct.unpack_from(">HH", d, base + 16)
    (e_entry, e_phoff, e_shoff) = struct.unpack_from(">QQQ", d, base + 24)
    e_phentsize, e_phnum, e_shentsize, e_shnum = struct.unpack_from(">HHHH", d, base + 54)
    return {"type": {2: "EXEC", 3: "DYN (PRX)"}.get(e_type, e_type),
            "machine": {21: "PPC64 (PPU)", 23: "SPU"}.get(e_machine, e_machine),
            "entry": e_entry, "phoff": e_phoff, "phnum": e_phnum, "phentsize": e_phentsize,
            "shoff": e_shoff, "shnum": e_shnum}


def program_headers(d, phoff, phnum, phentsize=0x38):
    out = []
    for i in range(phnum):
        p_type, p_flags, p_offset, p_vaddr, _paddr, p_filesz, p_memsz, _align = \
            struct.unpack_from(">IIQQQQQQ", d, phoff + i * phentsize)
        out.append({"type": PT_NAMES.get(p_type, hex(p_type)), "flags": "".join(
            c for c, bit in (("R", 4), ("W", 2), ("X", 1)) if p_flags & bit), "offset": p_offset,
            "vaddr": p_vaddr, "filesz": p_filesz, "memsz": p_memsz})
    return out


def self_header(path):
    """Campos públicos do cabeçalho SCE/SELF. Não decifra nada."""
    d = Path(path).read_bytes()
    info = {"file": str(path), "size": len(d), "sha256": hashlib.sha256(d).hexdigest()}
    if d[:4] != SCE_MAGIC:
        info["format"] = "ELF" if d[:4] == b"\x7fELF" else "desconhecido"
        return info, d
    _magic, version, key_rev, hdr_type, _meta_off, header_len, elf_size = struct.unpack_from(">IIHHIQQ", d, 0)
    info.update(format="SELF", sce_version=version, key_revision=key_rev, header_type=hdr_type,
                header_len=header_len, elf_size=elf_size,
                fself_debug=key_rev == 0x8000)
    if hdr_type != 1:
        return info, d
    (_ext, appinfo_off, elf_off, phdr_off, _shdr_off, seginfo_off, _ver_off, _ctrl_off) = \
        struct.unpack_from(">8Q", d, 0x20)
    auth_id, vendor_id, self_type, app_version = struct.unpack_from(">QIIQ", d, appinfo_off)
    info.update(auth_id=hex(auth_id), vendor_id=hex(vendor_id),
                self_type=SELF_TYPES.get(self_type, hex(self_type)),
                app_version="%d.%02d" % ((app_version >> 48) & 0xFFFF, (app_version >> 32) & 0xFFFF))
    elf = elf_summary(d, elf_off)
    if elf:
        info["elf"] = {k: v for k, v in elf.items() if k in ("type", "machine", "entry", "phnum", "shnum")}
        phdrs = program_headers(d, phdr_off, elf["phnum"])
        for i, ph in enumerate(phdrs):
            f_off, f_size, compressed, _u1, _u2, encrypted = struct.unpack_from(">QQIIII", d, seginfo_off + i * 0x20)
            ph.update(stored_size=f_size, compressed=compressed == 2, encrypted=encrypted == 1)
        info["segments"] = phdrs
    return info, d


# ---------------------------------------------------------------- pipeline do ps3recomp
def run(cmd, log):
    result = subprocess.run(cmd, capture_output=True, text=True)
    log.append({"cmd": " ".join(str(c) for c in cmd), "code": result.returncode,
                "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]})
    if result.returncode != 0:
        raise RuntimeError(f"falhou: {' '.join(str(c) for c in cmd)}\n{result.stderr[-2000:]}")
    return result.stdout


def analyse_elf(elf_path, ps3recomp, out, lift_sample, log):
    tools = Path(ps3recomp) / "tools"
    work = out / "ps3recomp"
    work.mkdir(parents=True, exist_ok=True)
    run([sys.executable, tools / "ppu_loader.py", elf_path, "-o", work], log)
    stem = Path(elf_path).stem
    loader = json.loads((work / f"{stem}.loader.json").read_text())
    functions = json.loads((work / f"{stem}.functions.json").read_text())
    imports = json.loads((work / f"{stem}.imports.json").read_text())
    image = json.loads((work / f"{stem}.image.json").read_text())

    sys.path.insert(0, str(tools))
    import nid_database  # noqa: E402  (ps3recomp, MIT)
    names = nid_database.NIDDatabase()
    names.load_builtins()
    implemented = nid_database.NIDDatabase()
    implemented.load_implemented(str(ps3recomp))
    by_lib = defaultdict(list)
    for imp in imports:
        nid = int(imp["nid"], 16)
        hit = names.lookup_nid(nid)
        by_lib[imp["library"]].append({"nid": imp["nid"], "name": hit[1] if hit else None,
                                       "hle": implemented.lookup_nid(nid) is not None})
    spu_dir = out / "spu_images"
    result = subprocess.run([sys.executable, tools / "extract_spu_images.py", elf_path, "--output", spu_dir],
                            capture_output=True, text=True)
    log.append({"cmd": "extract_spu_images.py", "code": result.returncode, "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-2000:]})
    if "No SPU images found" in result.stdout:
        spu = []
    elif result.returncode != 0:
        spu = [("erro", (result.stderr or result.stdout)[-300:])]
    else:
        spu = sorted((p.name, p.stat().st_size) for p in spu_dir.glob("*") if p.is_file())

    sample = None
    if lift_sample and not functions:
        sample = {"requested": lift_sample, "error": "nenhuma função encontrada pelo ppu_loader"}
    elif lift_sample:
        chosen = sorted(functions, key=lambda f: int(f["start"], 16))[:lift_sample]
        sample_json = work / "sample_functions.json"
        sample_json.write_text(json.dumps([{"start": f["start"], "end": f["end"]} for f in chosen]))
        lifted = out / "lift_sample"
        try:
            text = run([sys.executable, tools / "ppu_lifter.py", elf_path, "--functions", sample_json,
                        "--single-file", "-o", lifted], log)
            c = (lifted / "ppu_recomp.c").read_text(errors="replace")
            sample = {"requested": lift_sample, "lifted_lines": c.count("\n"), "todo_markers": c.count("/* TODO"),
                      "lifter_output": text.strip().splitlines()[-5:]}
        except RuntimeError as error:
            sample = {"requested": lift_sample, "error": str(error)[:500]}
    return {"loader": loader, "function_count": len(functions), "segments": image,
            "imports": {lib: entries for lib, entries in sorted(by_lib.items())},
            "import_count": len(imports), "spu_images": spu, "lift_sample": sample}


# ---------------------------------------------------------------- relatório
def hexs(v):
    return f"0x{v:08X}" if isinstance(v, int) else str(v)


def write_markdown(report, path):
    L = ["# Análise do executável — God of War III (PS3)", "",
         f"Gerado em {report['generated']} por `native/tools/analyze_gow3.py`.", ""]
    sfo = report.get("param_sfo") or {}
    if sfo:
        L += ["## PARAM.SFO", "", "| Campo | Valor |", "|---|---|"]
        for k in ("TITLE_ID", "TITLE", "APP_VER", "VERSION", "PS3_SYSTEM_VER", "CATEGORY"):
            if k in sfo:
                L.append(f"| {k} | {sfo[k]} |")
        L.append("")
    for item in report["executables"]:
        L += [f"## {Path(item['file']).name}", "", f"- Formato: {item.get('format')}, {item['size']:,} bytes",
              f"- SHA-256: `{item['sha256']}`"]
        if item.get("format") == "SELF":
            L += [f"- Tipo: {item.get('self_type')}, versão do aplicativo {item.get('app_version')}",
                  f"- Revisão de chave: 0x{item['key_revision']:04X} "
                  + ("(fSELF de depuração, sem cifra)" if item["fself_debug"] else "(varejo: segmentos cifrados)")]
            elf = item.get("elf")
            if elf:
                L.append(f"- ELF: {elf['type']}, {elf['machine']}, entrada (OPD) {hexs(elf['entry'])}, "
                         f"{elf['phnum']} segmentos, {elf['shnum']} seções")
            if item.get("segments"):
                L += ["", "| Segmento | Endereço | Tamanho na memória | Permissões | Cifrado | Comprimido |",
                      "|---|---|---|---|---|---|"]
                for s in item["segments"]:
                    L.append(f"| {s['type']} | {hexs(s['vaddr'])} | {s['memsz']:,} | {s['flags']} | "
                             f"{'sim' if s.get('encrypted') else 'não'} | {'sim' if s.get('compressed') else 'não'} |")
        L.append("")
    elf = report.get("elf_analysis")
    if elf is None:
        L += ["## Análise PPU/SPU", "", report.get("elf_missing_reason", ""), ""]
    else:
        ld = elf["loader"]
        L += ["## Análise PPU (ps3recomp `ppu_loader.py`)", "",
              f"- Funções PPU (descritores OPD): **{elf['function_count']:,}**",
              f"- Entrada: código {ld.get('entry_code')} (OPD {ld.get('entry_opd')}), TOC do módulo (r2): {ld.get('module_toc')}",
              f"- Importações do firmware: **{elf['import_count']}** em {len(elf['imports'])} bibliotecas", "",
              "| Biblioteca | Importações | Nomeadas | Implementadas no HLE do ps3recomp |", "|---|---|---|---|"]
        for lib, entries in elf["imports"].items():
            L.append(f"| {lib} | {len(entries)} | {sum(1 for e in entries if e['name'])} | "
                     f"{sum(1 for e in entries if e['hle'])} |")
        total = sum(len(v) for v in elf["imports"].values())
        hle = sum(1 for v in elf["imports"].values() for e in v if e["hle"])
        L += ["", f"Cobertura HLE das importações: {hle}/{total} ({(100 * hle / total) if total else 0:.0f}%).", "",
              "## Programas SPU embutidos", ""]
        L += [f"- {name}: {size:,} bytes" if isinstance(size, int) else f"- {name}: {size}" for name, size in elf["spu_images"]] or ["- nenhum encontrado"]
        if elf.get("lift_sample"):
            s = elf["lift_sample"]
            L += ["", "## Amostra recompilada (PPU → C)", ""]
            if s.get("error"):
                L.append(f"- Falhou: {s['error']}")
            else:
                L += [f"- {s['requested']} funções, {s['lifted_lines']:,} linhas de C, "
                      f"{s['todo_markers']} marcadores TODO (instruções/dados não traduzidos)",
                      "- Isto prova só a tradução; nada foi executado."]
    L += ["", "---", "Nenhum conteúdo do jogo foi copiado para este relatório; só metadados, endereços e NIDs."]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("--ps3recomp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--elf", help="EBOOT.ELF já decifrado (se não for o próprio input)")
    ap.add_argument("--lift-sample", type=int, default=0)
    a = ap.parse_args()
    src, out = Path(a.input), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    log = []
    report = {"generated": datetime.datetime.now().isoformat(timespec="seconds"), "executables": []}

    game_dir = src if src.is_dir() else None
    if game_dir and (game_dir / "PS3_GAME").is_dir():
        game_dir = game_dir / "PS3_GAME"
    eboot = (game_dir / "USRDIR" / "EBOOT.BIN") if game_dir else src
    if game_dir and (game_dir / "PARAM.SFO").is_file():
        report["param_sfo"] = read_sfo(game_dir / "PARAM.SFO")

    elf_path = Path(a.elf) if a.elf else None
    if eboot.is_file():
        info, _ = self_header(eboot)
        report["executables"].append(info)
        if info.get("format") == "ELF" and not elf_path:
            elf_path = eboot
        elif info.get("fself_debug") and not elf_path:
            elf_path = out / "EBOOT.elf"
            run([sys.executable, Path(a.ps3recomp) / "tools" / "unfself.py", eboot, "-o", elf_path], log)
    if game_dir:
        for extra in sorted((game_dir / "USRDIR").rglob("*")):
            if extra.suffix.lower() in (".sprx", ".self") and extra != eboot:
                report["executables"].append(self_header(extra)[0])

    if elf_path and elf_path.is_file():
        report["elf_analysis"] = analyse_elf(elf_path, a.ps3recomp, out, a.lift_sample, log)
    else:
        report["elf_missing_reason"] = (
            "O EBOOT.BIN é um SELF de varejo com segmentos cifrados. A análise de funções PPU, "
            "importações e programas SPU precisa do executável já decifrado (EBOOT.ELF), preparado "
            "pelo usuário a partir da própria cópia. Este projeto não decifra SELF de varejo.")
    (out / "report.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    (out / "commands.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
    write_markdown(report, out / "report.md")
    print((out / "report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
