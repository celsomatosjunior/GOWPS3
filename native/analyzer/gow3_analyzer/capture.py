# SPDX-License-Identifier: GPL-2.0-only
"""Captura de estados reais: o jogo roda no RPCS3 do usuário e, pelo servidor GDB do RPCS3, cada
função testada é parada na entrada; registradores e a memória que ela usa são copiados.

Como se descobre a memória que a função usa: com o jogo parado no breakpoint, a função é executada
na CPU de referência (Unicorn) só com as páginas de código do ELF mapeadas; cada página de 4 KB que
ela tocar é buscada no RPCS3 pelo GDB, com o conteúdo de antes da execução. O caso capturado leva os
registradores e essas páginas, e depois é dado igual ao código recompilado e ao PowerPC original.

O que o servidor do RPCS3 não informa (XER, FPSCR, registradores vetoriais) entra zerado igual nos
dois lados: o caso continua sendo uma comparação válida da tradução, com um estado quase real.

O arquivo de capturas (capturas_gow3.json.gz) contém memória do jogo em execução: fica só no
computador do usuário e não deve ser publicado.
"""

from __future__ import annotations

import datetime as dt
import gzip
import json
import time
from pathlib import Path

from unicorn import UC_ARCH_PPC, UC_HOOK_INTR, UC_HOOK_MEM_UNMAPPED, UC_MODE_BIG_ENDIAN, UC_MODE_PPC64, Uc, UcError
from unicorn.unicorn_const import UC_TLB_VIRTUAL
from unicorn import ppc_const as P

from . import formats, state as S
from .analysis import ElfImage
from .guestmem import GuestMemory
from .gdb_client import REG_CR, REG_CTR, REG_LR, REG_PC, GdbClient, GdbError

PAGE = 0x1000
CAPTURE_FILE = "capturas_gow3.json.gz"
MSR_FP = 1 << 13


class LiveRunner:
    """Roda uma função a partir de um estado capturado, buscando páginas sob demanda."""

    def __init__(self, image: ElfImage, fetch):
        self.image, self.fetch = image, fetch
        self.code_pages: set[int] = set()
        for seg in image.loads:
            if seg["flags"] & 1:  # executável
                lo, hi = seg["vaddr"] & ~0xFFF, (seg["vaddr"] + seg["memsz"] + 0xFFF) & ~0xFFF
                self.code_pages.update(range(lo, hi, PAGE))

    def run(self, regs: dict) -> tuple[str, dict[int, bytes]]:
        mu = Uc(UC_ARCH_PPC, UC_MODE_PPC64 | UC_MODE_BIG_ENDIAN)
        mu.ctl_set_tlb_mode(UC_TLB_VIRTUAL)
        gm = GuestMemory(mu)  # endereços efetivos de 32 bits, como no RPCS3 (ver guestmem.py)
        for seg in self.image.loads:
            if seg["flags"] & 1:
                lo, hi = seg["vaddr"] & ~0xFFF, (seg["vaddr"] + seg["memsz"] + 0xFFF) & ~0xFFF
                gm.map(lo, hi - lo)
                mu.mem_write(seg["vaddr"], self.image.data[seg["offset"]:seg["offset"] + seg["filesz"]])
        gm.map(S.RETURN_SENTINEL, PAGE)
        mu.mem_write(S.RETURN_SENTINEL, bytes.fromhex("60000000" "7c6102a6" "7c6103a6" "60000000"))
        pages: dict[int, bytes] = {}
        failed: set[int] = set()
        self.failed_addrs: list[int] = []

        def on_unmapped(uc, access, addr, size, value, data):
            low = addr & 0xFFFFFFFF
            page = low & ~0xFFF
            if gm.find(page) is None:  # página de 32 bits ainda não trazida do jogo
                if page in failed or page == S.RETURN_SENTINEL or len(pages) > 512:
                    self.failed_addrs.append(addr)
                    return False
                content = self.fetch(page)
                if content is None:
                    failed.add(page)
                    self.failed_addrs.append(addr)
                    return False
                content = content[:PAGE].ljust(PAGE, b"\0")
                gm.map(page, PAGE)
                uc.mem_write(page, content)
                pages[page] = content
            if addr > 0xFFFFFFFF:  # ponteiro estendido com sinal: espelho da página de 32 bits
                return gm.alias(addr)
            return True

        exceptions = []
        mu.hook_add(UC_HOOK_MEM_UNMAPPED, on_unmapped)
        mu.hook_add(UC_HOOK_INTR, lambda uc, intno, d: (exceptions.append(intno), uc.emu_stop()))
        mu.reg_write(P.UC_PPC_REG_MSR, mu.reg_read(P.UC_PPC_REG_MSR) | MSR_FP)
        for i in range(32):
            mu.reg_write(getattr(P, f"UC_PPC_REG_{i}"), regs["gpr"][i])
            mu.reg_write(getattr(P, f"UC_PPC_REG_FPR{i}"), regs["fpr"][i])
        mu.reg_write(P.UC_PPC_REG_CR, regs["cr"])
        mu.reg_write(P.UC_PPC_REG_CTR, regs["ctr"])
        mu.reg_write(P.UC_PPC_REG_LR, S.RETURN_SENTINEL)
        try:
            mu.emu_start(regs["pc"], S.RETURN_SENTINEL, count=S.INSTRUCTION_LIMIT)
        except UcError as error:
            where = f" em 0x{self.failed_addrs[-1]:X}" if self.failed_addrs else ""
            return f"falha ({error}){where}", pages
        if exceptions:
            return f"exceção {exceptions[0]}", pages
        if mu.reg_read(P.UC_PPC_REG_PC) != S.RETURN_SENTINEL:
            return "sem fim", pages
        return "ok", pages


def read_state(client: GdbClient) -> dict | None:
    g = client.read_all_registers()
    if g and g["pc"] is not None and None not in g["gpr"]:
        gpr, fpr, pc, cr, lr, ctr = g["gpr"], g["fpr"], g["pc"], g["cr"], g["lr"], g["ctr"]
    else:  # servidor sem 'g' completo: registrador por registrador
        gpr = [client.read_register(i) for i in range(32)]
        fpr = [client.read_register(32 + i) for i in range(32)]
        pc, cr, lr, ctr = (client.read_register(r) for r in (REG_PC, REG_CR, REG_LR, REG_CTR))
        if None in gpr or pc is None:
            return None
    return {"pc": pc, "gpr": [v & S.MASK for v in gpr], "fpr": [(v or 0) & S.MASK for v in fpr],
            "cr": (cr or 0) & 0xFFFFFFFF, "lr_real": lr or 0, "ctr": (ctr or 0) & S.MASK}


def stopped_thread(client: GdbClient, wanted: set[int]) -> tuple[str, int] | None:
    for tid in client.threads():
        if client.select_thread(tid):
            pc = client.read_register(REG_PC)
            if pc in wanted:
                return tid, pc
    return None


def capture(elf: Path, functions: list[dict], out_dir: Path, host: str = "127.0.0.1", port: int = 2345,
            minutes: float = 5.0, per_function: int = 4, progress=print, source: str = "rpcs3") -> dict:
    """Captura até `per_function` estados reais de cada função. `functions`: [{"func", "start"}...]
    (as candidatas da análise). Grava `capturas_gow3.json.gz` em `out_dir` e devolve o resumo."""
    image = ElfImage(elf)
    addrs = {int(f["start"], 16) if isinstance(f["start"], str) else f["start"]: f["func"] for f in functions}
    progress(f"Conectando ao servidor GDB em {host}:{port} (o jogo pausa enquanto o analisador trabalha)...")
    try:
        client = GdbClient(host, port)
    except OSError as error:
        raise GdbError(f"não foi possível conectar em {host}:{port}: {error}. O jogo está rodando no RPCS3?") from error
    cases: list[dict] = []
    hits = {a: 0 for a in addrs}
    refused = []
    t0 = time.time()
    error = None
    try:
      try:
        client.stop_reason()
        for a in list(addrs):
            if not client.set_breakpoint(a):
                refused.append(a)
                hits.pop(a)
        pending = set(hits)
        progress(f"{len(pending)} breakpoints colocados. Jogue normalmente; a captura dura até {minutes:g} min "
                 f"ou até juntar {per_function} estados de cada função.")
        runner = LiveRunner(image, lambda page: client.read_memory(page, PAGE))
        deadline = t0 + minutes * 60
        while pending and time.time() < deadline:
            client.resume()
            reply = client.wait_stop(deadline - time.time())
            if reply is None:  # tempo acabou: interrompe para poder tirar os breakpoints
                client.interrupt()
                break
            if reply.startswith(("W", "X")):  # o programa terminou (QEMU)
                break
            found = stopped_thread(client, pending)
            if not found:
                continue
            _tid, pc = found
            regs = read_state(client)
            if regs is None:
                continue
            outcome, pages = runner.run(regs)
            hits[pc] += 1
            cases.append({"func": addrs[pc], "addr": pc, "outcome_live": outcome, **{k: regs[k] for k in ("gpr", "fpr", "cr", "ctr", "lr_real")},
                          "pages": {f"{p:x}": data.hex() for p, data in sorted(pages.items())}})
            progress(f"  {addrs[pc]}: estado {hits[pc]}/{per_function} ({len(pages)} páginas, {outcome})")
            if hits[pc] >= per_function:
                client.remove_breakpoint(pc)
                pending.discard(pc)
        for a in pending:
            client.remove_breakpoint(a)
      except (OSError, GdbError) as exc:  # TimeoutError é OSError
        error = (f"o RPCS3 parou de responder durante a captura ({type(exc).__name__}: {exc}). "
                 "Os estados capturados até aqui foram guardados.")
        progress(error)
    finally:
        try:
            client.resume()  # o jogo continua rodando depois da captura
        except (OSError, GdbError):
            pass
        client.close()
    summary = {"source": source, "created": dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
               "elf_sha256": formats.sha256_file(elf), "seconds": round(time.time() - t0),
               "functions": len(addrs), "functions_captured": sum(1 for v in hits.values() if v),
               "states": len(cases), "breakpoints_refused": [f"{a:x}" for a in refused],
               "ok_states": sum(1 for c in cases if c["outcome_live"] == "ok"), "error": error}
    out_dir.mkdir(parents=True, exist_ok=True)
    with gzip.open(out_dir / CAPTURE_FILE, "wt", encoding="utf-8") as f:
        json.dump({"summary": summary, "cases": cases}, f)
    return summary


def load(path: Path, elf_sha256: str) -> tuple[dict, list[dict]] | None:
    """Lê um arquivo de capturas; só vale se foi feito com o mesmo EBOOT.ELF."""
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    if d.get("summary", {}).get("elf_sha256") != elf_sha256:
        return None
    return d["summary"], d["cases"]
