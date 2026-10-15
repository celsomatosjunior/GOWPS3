# SPDX-License-Identifier: GPL-2.0-only
"""Análise estática de um executável PPU (EBOOT.ELF) para a recompilação.

Usa o ppu_loader e o disassembler do ps3recomp e calcula, por função: tamanho, chamadas diretas,
chamadas a bibliotecas do sistema (NID), chamadas indiretas, syscalls, uso de VMX/ponto flutuante,
acesso a memória e laços. Daí saem o grafo de chamadas, o fluxo a partir da entrada, as dependências
PRX, as referências a SPU e as funções candidatas ao primeiro teste de recompilação.

O relatório guarda só metadados (endereços, tamanhos, contagens, nomes de bibliotecas e NIDs);
nenhum byte ou instrução do jogo é copiado.
"""

from __future__ import annotations

import json
import re
import struct
import tempfile
from collections import Counter, defaultdict, deque
from pathlib import Path

from . import tools

VMX_EXTRA = {"lvx", "lvxl", "stvx", "stvxl", "lvebx", "lvehx", "lvewx", "stvebx", "stvehx", "stvewx", "lvsl", "lvsr",
             "lvlx", "lvrx", "stvlx", "stvrx", "lvlxl", "lvrxl", "stvlxl", "stvrxl", "mfvscr", "mtvscr", "dst", "dstt",
             "dss", "dssall"}
# Instruções que impedem a comparação justa com a referência: dependem do sistema (relógio, SPRs,
# MSR), são armadilhas (o lifter ignora `tw`; a CPU de referência gera exceção) ou acessam a memória
# do convidado pelo ponteiro plano `vm_base` do ps3recomp em vez de vm_read/vm_write.
UNSAFE_FOR_REFERENCE = {"mftb", "mftbu", "mfspr", "mtspr", "mfmsr", "mtmsr", "mtmsrd", "tw", "twi", "td", "tdi", "trap",
                        "rfid", "lwbrx", "stwbrx", "lhbrx", "sthbrx", "ldbrx", "stdbrx", "dcbz"}
SPU_HINTS = ("spu", "spurs", "sysspu")


class ElfImage:
    """Segmentos PT_LOAD de um ELF64 big-endian, para ler bytes por endereço do convidado."""

    def __init__(self, path: Path):
        self.data = Path(path).read_bytes()
        d = self.data
        phoff, = struct.unpack_from(">Q", d, 0x20)
        phentsize, phnum = struct.unpack_from(">HH", d, 0x36)
        self.entry, = struct.unpack_from(">Q", d, 0x18)
        self.loads = []
        for i in range(phnum):
            p_type, flags, off, vaddr, _pa, filesz, memsz, _al = struct.unpack_from(">IIQQQQQQ", d, phoff + i * phentsize)
            if p_type == 1:
                self.loads.append({"vaddr": vaddr, "offset": off, "filesz": filesz, "memsz": memsz, "flags": flags})

    def read(self, vaddr: int, size: int) -> bytes:
        for s in self.loads:
            if s["vaddr"] <= vaddr and vaddr + size <= s["vaddr"] + s["filesz"]:
                o = s["offset"] + vaddr - s["vaddr"]
                return self.data[o:o + size]
        return b""


def _target(operands: str):
    last = operands.split(",")[-1].strip()
    if last.startswith("0x"):
        try:
            return int(last, 16)
        except ValueError:
            return None
    return None


def analyse(elf_path: Path, work: Path, progress=lambda msg: None) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    progress("Lendo funções, TOC e importações (ps3recomp ppu_loader)...")
    tools.run_tool("ppu_loader", [elf_path, "-o", work])
    stem = Path(elf_path).stem
    loader = json.loads((work / f"{stem}.loader.json").read_text())
    functions = json.loads((work / f"{stem}.functions.json").read_text())
    imports = json.loads((work / f"{stem}.imports.json").read_text())

    nid_db = tools.load("nid_database")
    names = nid_db.NIDDatabase()
    names.load_builtins()
    implemented = nid_db.NIDDatabase()
    hle_json = tools.resource_dir() / "hle_implemented.json"  # gerado no empacotamento
    if hle_json.is_file():
        implemented.load_json(str(hle_json))
        names.load_json(str(hle_json))
    else:
        implemented.load_implemented(str(tools.ps3recomp_root()))
    stub_map = {}
    for imp in imports:
        nid = int(imp["nid"], 16)
        hit = names.lookup_nid(nid)
        stub_map[int(imp["stub"], 16)] = {"library": imp["library"], "nid": imp["nid"],
                                           "name": hit[1] if hit else None,
                                           "hle": implemented.lookup_nid(nid) is not None}

    disasm = tools.load("ppu_disasm")
    image = ElfImage(elf_path)
    progress(f"Analisando {len(functions)} funções PPU...")
    func_info = {}
    starts = {int(f["start"], 16) for f in functions}
    for idx, f in enumerate(functions):
        start, end = int(f["start"], 16), int(f["end"], 16)
        blob = image.read(start, end - start)
        insns = disasm.disassemble_bytes(blob, start, True) if blob else []
        mn = Counter()
        calls, import_calls, syscalls = set(), set(), []
        indirect_calls = bctr = backward = blr = 0
        vmx = fp = loads = stores = unsafe = r13 = 0
        prev = None
        for ins in insns:
            m = ins.mnemonic
            mn[m] += 1
            if m in ("bl", "bla"):
                t = _target(ins.operands)
                if t in stub_map:
                    import_calls.add(t)
                elif t is not None:
                    calls.add(t)
            elif m in ("bctrl",):
                indirect_calls += 1
            elif m == "bctr":
                bctr += 1
            elif m == "blr":
                blr += 1
            elif m == "sc":
                num = None
                if prev is not None and prev.mnemonic == "li" and prev.operands.replace(" ", "").startswith("r11,"):
                    try:
                        num = int(prev.operands.split(",")[1], 0)
                    except ValueError:
                        num = None
                syscalls.append(num)
            if m.startswith("b") and m not in ("bl", "bla", "blr", "bctr", "bctrl", "blrl"):
                t = _target(ins.operands)
                if t is not None and t < ins.addr:
                    backward += 1
            if m.startswith("v") or m in VMX_EXTRA:
                vmx += 1
            elif m.startswith("f") or m.startswith(("lf", "stf")) or m in ("mffs", "mtfsf", "mtfsfi", "mtfsb0", "mtfsb1"):
                fp += 1
            if m.startswith("st"):
                stores += 1
            elif m.startswith("l") and m not in ("li", "lis") and not m.startswith("lv"):
                loads += 1
            if m in UNSAFE_FOR_REFERENCE and not (m in ("mfspr", "mtspr") and ("lr" in ins.operands or "ctr" in ins.operands)):
                unsafe += 1
            if "r13" in ins.operands:
                r13 += 1
            prev = ins
        func_info[start] = {
            "start": start, "end": end, "size": end - start, "insns": len(insns), "toc": f.get("toc"),
            "calls": sorted(calls), "import_calls": sorted(import_calls), "indirect_calls": indirect_calls,
            "bctr": bctr, "syscalls": syscalls, "blr": blr, "loops": backward, "vmx": vmx, "fp": fp,
            "loads": loads, "stores": stores, "unsafe": unsafe, "tls_r13": r13,
            "unknown": sum(c for k, c in mn.items() if k.startswith(("???", ".word", "unknown"))),
        }
        if idx % 2000 == 0 and idx:
            progress(f"  {idx}/{len(functions)} funções")

    # grafo de chamadas
    callers = Counter()
    for info in func_info.values():
        for t in info["calls"]:
            callers[t] += 1
    entry_code = int(loader.get("entry_code", "0x0"), 16)
    flow = []
    seen, queue = {entry_code}, deque([(entry_code, 0)])
    while queue and len(flow) < 400:
        addr, depth = queue.popleft()
        info = func_info.get(addr)
        node = {"func": f"func_{addr:08X}", "depth": depth, "known": info is not None}
        if info:
            node["calls"] = len(info["calls"])
            node["imports"] = [stub_map[s]["name"] or stub_map[s]["nid"] for s in info["import_calls"]][:12]
            if depth < 3:
                for t in info["calls"]:
                    if t not in seen:
                        seen.add(t)
                        queue.append((t, depth + 1))
        flow.append(node)

    # bibliotecas, dependências PRX e SPU
    by_lib = defaultdict(list)
    for stub, meta in sorted(stub_map.items()):
        users = [a for a, i in func_info.items() if stub in i["import_calls"]]
        by_lib[meta["library"]].append({**meta, "stub": f"0x{stub:08X}", "callers": len(users)})
    spu_functions = sorted({f"func_{a:08X}" for a, i in func_info.items()
                            for s in i["import_calls"]
                            if any(h in (stub_map[s]["library"] + (stub_map[s]["name"] or "")).lower() for h in SPU_HINTS)})
    prx_strings = sorted({m.decode("latin1") for m in re.findall(rb"[\w/\.\-]{3,64}\.s?prx", image.data)})

    progress("Procurando programas SPU embutidos...")
    spu_dir = work / "spu_images"
    try:
        out = tools.run_tool("extract_spu_images", [elf_path, "--output", spu_dir])
        spu_images = [{"name": p.name, "size": p.stat().st_size} for p in sorted(spu_dir.glob("*")) if p.is_file()]
    except tools.ToolError as error:
        spu_images = [] if "No SPU images found" in str(error) else [{"error": str(error)[-300:]}]

    syscall_counter = Counter(n for i in func_info.values() for n in i["syscalls"])
    candidates = select_candidates(func_info)
    return {
        "loader": loader,
        "function_count": len(func_info),
        "instruction_count": sum(i["insns"] for i in func_info.values()),
        "functions": [{**i, "start": f"0x{i['start']:08X}", "end": f"0x{i['end']:08X}",
                       "calls": [f"0x{c:08X}" for c in i["calls"]],
                       "import_calls": [stub_map[s]["name"] or stub_map[s]["nid"] for s in i["import_calls"]],
                       "callers": callers.get(i["start"], 0)} for i in func_info.values()],
        "summary": {
            "leaf_functions": sum(1 for i in func_info.values() if not i["calls"] and not i["import_calls"] and not i["indirect_calls"]),
            "with_vmx": sum(1 for i in func_info.values() if i["vmx"]),
            "with_fp": sum(1 for i in func_info.values() if i["fp"]),
            "with_indirect_calls": sum(1 for i in func_info.values() if i["indirect_calls"]),
            "with_syscalls": sum(1 for i in func_info.values() if i["syscalls"]),
            "calls_to_unknown_targets": sum(1 for i in func_info.values() for c in i["calls"] if c not in starts),
        },
        "most_called": [{"func": f"func_{a:08X}", "callers": n} for a, n in callers.most_common(25)],
        "entry_flow": flow,
        "imports": dict(sorted(by_lib.items())),
        "import_count": len(stub_map),
        "syscalls": [{"number": n, "sites": c} for n, c in syscall_counter.most_common()],
        "prx_dependencies": {"libraries": sorted(by_lib), "prx_files_referenced": prx_strings},
        "spu": {"images": spu_images, "functions_calling_spu_apis": spu_functions[:200],
                "functions_calling_spu_apis_count": len(spu_functions)},
        "candidates": candidates,
    }


def select_candidates(func_info: dict, limit: int = 40) -> list[dict]:
    """Funções boas para o primeiro teste: folhas, sem syscalls, sem VMX, sem instruções dependentes
    do sistema; preferindo tamanho médio, com acesso a memória e aritmética."""
    out = []
    for a, i in func_info.items():
        reasons = []
        if i["calls"] or i["import_calls"] or i["indirect_calls"]:
            continue
        # ".word" (dados/preenchimento entre funções) não desqualifica: não é executado.
        if i["syscalls"] or i["vmx"] or i["unsafe"] or not i["blr"]:
            continue
        if not 4 <= i["insns"] <= 400:
            continue
        score = min(i["insns"], 120) + 3 * min(i["loads"] + i["stores"], 20) + 10 * min(i["loops"], 3) + 2 * min(i["fp"], 10)
        if i["insns"] < 8:
            score -= 40
        reasons.append(f"{i['insns']} instruções")
        if i["loads"] or i["stores"]:
            reasons.append(f"{i['loads']} leituras/{i['stores']} escritas de memória")
        if i["loops"]:
            reasons.append(f"{i['loops']} laço(s)")
        if i["fp"]:
            reasons.append("ponto flutuante")
        if i["bctr"]:
            reasons.append("tabela de salto")
        if i["tls_r13"]:
            reasons.append("usa r13 (TLS)")
        out.append({"func": f"func_{a:08X}", "start": f"0x{a:08X}", "end": f"0x{i['end']:08X}", "toc": i["toc"],
                    "insns": i["insns"], "score": score, "why": ", ".join(reasons)})
    out.sort(key=lambda c: (-c["score"], c["start"]))
    return out[:limit]
