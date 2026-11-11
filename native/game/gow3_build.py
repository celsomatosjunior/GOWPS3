#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""GOW3 Native: traduz o EBOOT.ELF inteiro do God of War III, compila o executável nativo e o roda.

Roda no computador do usuário, sobre a cópia dele do jogo. Nada do jogo é enviado para lugar algum;
tudo o que é gerado fica em --trabalho (código traduzido, executável, logs). Passos (cada um grava
log em <trabalho>/logs e pode ser repetido sozinho com --passos):

  elf       acha o EBOOT.ELF: --elf, ou o que o GOW3_Native_Analyzer já gerou (cache), ou pede ao
            RPCS3 do usuário (rpcs3 --decrypt), como o analisador faz
  carregar  ps3recomp tools/ppu_loader.py: funções (.opd), importações do firmware, segmentos, TOC
  traduzir  ps3recomp tools/ppu_lifter.py --hle-stubs --chunks N: o código PPU inteiro em C++
  projeto   copia o projeto-modelo do ps3recomp (templates/project) e configura com CMake
            (Windows: clang-cl do Visual Studio + Ninja; SPUs embutidos traduzidos pelo modelo)
  compilar  compila o executável GOW3Native
  rodar     roda o executável por --segundos com a pasta do jogo como /dev_bdvd e resume o log

    python gow3_build.py --jogo "I:\\Games\\PS3\\...\\God.Of.War.3.PS3" --ps3recomp C:\\ps3recomp --trabalho I:\\GOW3_Native
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANALYZER = HERE.parent / "analyzer"
STEPS = ["elf", "carregar", "traduzir", "projeto", "compilar", "rodar"]


class StepError(RuntimeError):
    pass


def log_path(work: Path, step: str) -> Path:
    (work / "logs").mkdir(parents=True, exist_ok=True)
    return work / "logs" / f"{step}.log"


def run(cmd, work: Path, step: str, env=None, cwd=None, timeout=None) -> subprocess.CompletedProcess:
    """Roda um comando gravando a saída em logs/<passo>.log (acrescenta)."""
    lp = log_path(work, step)
    with open(lp, "a", encoding="utf-8", errors="replace") as f:
        f.write(f"\n$ {' '.join(str(c) for c in cmd)}\n")
        f.flush()
        proc = subprocess.run([str(c) for c in cmd], stdout=f, stderr=subprocess.STDOUT, env=env, cwd=cwd,
                              timeout=timeout)
        f.write(f"(código {proc.returncode})\n")
    return proc


def tail(path: Path, n: int = 30) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except OSError:
        return ""


# ---------------------------------------------------------------------------------------------
# ambiente de compilação no Windows: vcvars64 do Visual Studio (clang-cl vem junto)
# ---------------------------------------------------------------------------------------------
def vs_environment() -> dict | None:
    if os.name != "nt":
        return None
    vswhere = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.is_file():
        return None
    out = subprocess.run([str(vswhere), "-latest", "-products", "*", "-requires",
                          "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
                         capture_output=True, text=True).stdout.strip()
    if not out:
        return None
    vcvars = Path(out) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
    if not vcvars.is_file():
        return None
    dump = subprocess.run(f'cmd /c ""{vcvars}" >nul && set"', capture_output=True, text=True, shell=True).stdout
    env = {}
    for line in dump.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            env[k.upper()] = v  # os.environ no Windows usa chaves em maiúsculas (PATH, não Path)
    return env or None


def check_tools(env: dict) -> list[str]:
    missing = []
    for tool in (["clang-cl"] if os.name == "nt" else ["clang", "clang++"]) + ["cmake", "ninja"]:
        if shutil.which(tool, path=env.get("PATH")) is None:
            missing.append(tool)
    return missing


# ---------------------------------------------------------------------------------------------
# passos
# ---------------------------------------------------------------------------------------------
# "Skip any videos with X button" (autor: illusion, patches da comunidade do RPCS3), para o EBOOT 1.00:
# no player de vídeo, `stw r6,0xF5C(r31)` vira `stw r0,0xF5C(r31)`, e o X passa a pular qualquer vídeo.
# A troca é feita numa cópia local do EBOOT.ELF (nunca vai ao repositório), antes da tradução.
PULAR_VIDEOS = (0x0026FD18, bytes.fromhex("90DF"), bytes.fromhex("901F"))


def aplica_pular_videos(elf: Path, work: Path) -> Path:
    import struct
    ea, antes, depois = PULAR_VIDEOS
    data = bytearray(elf.read_bytes())
    phoff, = struct.unpack_from(">Q", data, 0x20)
    es, n = struct.unpack_from(">HH", data, 0x36)
    for i in range(n):
        p_type, _, off, vaddr, _, filesz = struct.unpack_from(">IIQQQQ", data, phoff + i * es)
        if p_type == 1 and vaddr <= ea < vaddr + filesz:
            o = off + ea - vaddr
            if data[o:o + 2] == depois:
                return elf                      # já aplicado
            if data[o:o + 2] != antes:
                raise StepError(f"--pular-videos: 0x{ea:X} tem {data[o:o + 2].hex()}, esperado {antes.hex()} "
                                "(o patch é do EBOOT 1.00)")
            data[o:o + 2] = depois
            out = work / "EBOOT.pular_videos.ELF"
            out.write_bytes(data)
            return out
    raise StepError(f"--pular-videos: 0x{ea:X} fora dos segmentos do ELF")


def aplica_patches_rpcs3(args, elf: Path, work: Path, state: dict, progress) -> Path:
    """Patches de terceiros do patch.yml do RPCS3 do usuário (native/tools/rpcs3_patches.py), numa cópia local."""
    sys.path.insert(0, str(HERE.parent / "tools"))
    import rpcs3_patches
    yml = Path(args.patch_yml) if args.patch_yml else (Path(args.rpcs3).parent if args.rpcs3 else
                                                       Path("F:/Quadrado do Claude/rpcs3")) / "patches" / "patch.yml"
    if not yml.is_file():
        raise StepError(f"--patch-rpcs3: não achei o patch.yml do RPCS3 em {yml} (use --patch-yml)")
    ps = rpcs3_patches.patches_do_jogo(yml, "BCES00510", "01.00")
    data = elf.read_bytes()
    for nome in args.patch_rpcs3:
        if nome not in ps:
            raise StepError(f"--patch-rpcs3: {nome!r} não existe para BCES00510 01.00; há: " + ", ".join(ps))
        data, feitos = rpcs3_patches.aplica(data, ps[nome]["ops"])
        progress(f"Patch do RPCS3 '{nome}' ({ps[nome]['autor']}): " + "; ".join(feitos))
    out = work / "EBOOT.patches.ELF"
    out.write_bytes(data)
    state["patches_rpcs3"] = list(args.patch_rpcs3)
    return out


def step_elf(args, work: Path, state: dict, progress):
    if args.elf:
        elf = Path(args.elf).resolve()
    else:
        sys.path.insert(0, str(ANALYZER))
        from gow3_analyzer import decrypt, formats, pipeline  # noqa: E402
        exe, _notes = pipeline.locate(Path(args.jogo))
        ident = formats.identify(exe)
        if ident.get("format") == "ELF":
            elf = exe
        else:
            elf = decrypt.cached_elf(ident["sha256"])
            if elf is None:
                tool = decrypt.find_rpcs3(args.rpcs3)
                if tool is None:
                    raise StepError("EBOOT.ELF não encontrado: rode o GOW3_Native_Analyzer uma vez (ele gera e guarda o "
                                    "EBOOT.ELF) ou indique --rpcs3 / --elf")
                elf = decrypt.decrypt_with_rpcs3(exe, tool, work, progress)
                decrypt.store_elf(ident["sha256"], elf)
    if not elf.is_file():
        raise StepError(f"{elf} não existe")
    if args.pular_videos:
        elf = aplica_pular_videos(elf, work)
    if args.patch_rpcs3:
        elf = aplica_patches_rpcs3(args, elf, work, state, progress)
    else:
        state.pop("patches_rpcs3", None)    # um build anterior com patches não deixa a marca
    state["elf"] = str(elf)
    progress(f"EBOOT.ELF: {elf} ({elf.stat().st_size:,} bytes)".replace(",", "."))


def fim_do_codigo_por_secoes(elf: Path) -> int | None:
    """Fim da última seção executável (SHF_ALLOC|SHF_EXECINSTR) de um ELF64 big-endian, ou None
    quando o ELF não tem tabela de seções ou nenhuma seção executável."""
    import struct
    data = elf.read_bytes()
    if len(data) < 0x40 or data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 2:
        return None
    shoff = struct.unpack_from(">Q", data, 0x28)[0]
    shentsize, shnum = struct.unpack_from(">HH", data, 0x3A)
    if not shoff or not shnum or shentsize < 0x40 or shoff + shnum * shentsize > len(data):
        return None
    fim = None
    for i in range(shnum):
        sh_type, sh_flags, sh_addr, _, sh_size = struct.unpack_from(">IQQQQ", data, shoff + i * shentsize + 4)
        if sh_type != 8 and sh_flags & 0x6 == 0x6 and sh_size:   # 8 = SHT_NOBITS; 0x6 = ALLOC|EXECINSTR
            fim = max(fim or 0, sh_addr + sh_size)
    return fim


def step_carregar(args, work: Path, state: dict, progress):
    elf = Path(state["elf"])
    out = work / "analise"
    out.mkdir(parents=True, exist_ok=True)
    proc = run([sys.executable, Path(args.ps3recomp) / "tools" / "ppu_loader.py", elf, "-o", out], work, "carregar")
    if proc.returncode:
        raise StepError("ppu_loader falhou:\n" + tail(log_path(work, "carregar")))
    stem = elf.stem
    files = {k: out / f"{stem}.{k}.json" for k in ("functions", "imports", "image", "loader")}
    for k, p in files.items():
        if not p.is_file():
            raise StepError(f"ppu_loader não gerou {p.name}")
    funcs = json.loads(files["functions"].read_text())
    imports = json.loads(files["imports"].read_text())
    image = json.loads(files["image"].read_text())
    loader = json.loads(files["loader"].read_text())
    segs = image if isinstance(image, list) else image.get("segments", [])
    # As seções executáveis dizem onde o código acaba. O segmento executável vai além: no GOW3 ele
    # também carrega os dados só de leitura (0x3CA804..0x4F76E0), e o tradutor os lia como ~7.800
    # funções. Sem tabela de seções, fica o fim do segmento.
    code_end = fim_do_codigo_por_secoes(elf)
    for s in segs if code_end is None else []:
        flags = int(str(s.get("flags", 0)), 0) if not isinstance(s.get("flags"), int) else s["flags"]
        if flags & 1:
            v = int(str(s["vaddr"]), 0) if not isinstance(s["vaddr"], int) else s["vaddr"]
            fz = int(str(s["filesz"]), 0) if not isinstance(s["filesz"], int) else s["filesz"]
            code_end = max(code_end or 0, v + fz)
    state.update(functions_json=str(files["functions"]), imports_json=str(files["imports"]),
                 n_functions=len(funcs), n_imports=len(imports), code_end=code_end,
                 toc=loader.get("module_toc") or loader.get("entry_toc"))
    progress(f"{len(funcs)} funções, {len(imports)} importações do firmware, fim do código 0x{code_end or 0:X}")


def step_traduzir(args, work: Path, state: dict, progress):
    out = work / "recompiled"
    if out.exists():
        shutil.rmtree(out)
    cmd = [sys.executable, Path(args.ps3recomp) / "tools" / "ppu_lifter.py", state["elf"],
           "--functions", state["functions_json"], "--hle-stubs", state["imports_json"],
           "--chunks", str(args.arquivos), "-o", out]
    if state.get("code_end"):
        cmd += ["--code-end", hex(state["code_end"])]
    if args.toc:
        cmd += ["--toc", args.toc]
    progress(f"Traduzindo {state['n_functions']} funções em {args.arquivos} arquivos (pode levar muitos minutos)...")
    t0 = time.time()
    proc = run(cmd, work, "traduzir")
    if proc.returncode:
        raise StepError("ppu_lifter falhou:\n" + tail(log_path(work, "traduzir")))
    srcs = sorted(out.glob("*.cpp")) + sorted(out.glob("*.c"))
    size = sum(p.stat().st_size for p in srcs)
    lines = 0
    todos = 0
    for p in srcs:
        with open(p, "rb") as f:
            for ln in f:
                lines += 1
                if b"/* TODO" in ln and b".word" not in ln:  # .word = dados no meio do código, não instrução
                    todos += 1
    m = re.search(r"(\d+) functions lifted", log_path(work, "traduzir").read_text(errors="replace"))
    state.update(recomp_dir=str(out), lifted_functions=int(m.group(1)) if m else None, lifted_files=len(srcs),
                 lifted_bytes=size, lifted_lines=lines, lifter_todos=todos, lift_seconds=round(time.time() - t0))
    progress(f"Tradução: {state['lifted_functions']} funções, {len(srcs)} arquivos, {lines:,} linhas, "
             f"{size / 1e6:.0f} MB, {todos} instruções não traduzidas (TODO)".replace(",", "."))


def add_libsre_lle(args, proj: Path, cm: Path):
    """LLE seletivo da libsre (gow3_libsre_lle.cpp): a libsre recompilada, o prx_loader do ps3recomp e
    a ligação dos NIDs da LFQueue. A pasta --lle-libsre tem lifted/libsre_recomp.cpp e libsre_image.bin."""
    lle = Path(args.lle_libsre).resolve()
    lifted = lle / "lifted" / "libsre_recomp.cpp"
    for p in (lifted, lle / "libsre_image.bin"):
        if not p.is_file():
            raise StepError(f"--lle-libsre: falta {p}")
    stubs = proj / "stubs.cpp"
    text, n = re.subn(r'extern "C" void ps3_load_prx_modules\(void\)\s*\{\s*\}', "", stubs.read_text(encoding="utf-8"))
    if n != 1:
        raise StepError("stubs.cpp do modelo mudou: não achei o ps3_load_prx_modules vazio")
    stubs.write_text(text, encoding="utf-8")
    ps3r = Path(args.ps3recomp).resolve()
    srcs = [HERE / "gow3_libsre_lle.cpp", ps3r / "runtime" / "prx" / "prx_loader.c", lifted]
    cm.write_text(cm.read_text(encoding="utf-8") + "\n# GOW3: LLE seletivo da libsre (LFQueue)\n"
                  "target_sources(${PROJECT_NAME} PRIVATE\n" +
                  "".join(f'    "{p.as_posix()}"\n' for p in srcs) + ")\n"
                  f'target_include_directories(${{PROJECT_NAME}} PRIVATE "{(ps3r / "runtime" / "prx").as_posix()}")\n',
                  encoding="utf-8")


def ffmpeg_cmake_args(args) -> list:
    """-D do CMake para o cellVdec decodificar com o FFmpeg (carregado em tempo de execução, nunca ligado)."""
    if not args.ffmpeg:
        return []
    inc = Path(args.ffmpeg).resolve() / "include"
    if not (inc / "libavcodec" / "avcodec.h").is_file():
        raise StepError(f"--ffmpeg: não achei {inc / 'libavcodec' / 'avcodec.h'}")
    return ["-DPS3RECOMP_FFMPEG_RUNTIME=ON", f"-DPS3RECOMP_FFMPEG_INCLUDE_DIR={inc}"]


def aplica_ganchos(args, modulo: str, texto: str) -> str:
    """--spu-ganchos <pasta>: ganchos nativos no código SPU traduzido, descritos em <pasta>/ganchos.json como
    [{"modulo": <pasta do módulo>, "funcao": <função traduzida>, "cabecalho": <arquivo da pasta>, "chamada": <C>}].
    O #include entra depois dos includes da fonte e a chamada como primeira linha do corpo da função (antes dos
    rótulos: roda uma vez a cada entrada, e um laço que volta ao rótulo não a repete). Os cabeçalhos ficam só na
    pasta local (são reescritas de código do jogo); o repositório só tem este mecanismo."""
    if args.sem_ganchos:
        return texto
    pasta = Path(args.spu_ganchos).resolve() if args.spu_ganchos else Path(args.trabalho).resolve() / "edge_nativo"
    if not (pasta / "ganchos.json").is_file():
        if args.spu_ganchos:
            raise StepError(f"--spu-ganchos: {pasta} não tem ganchos.json")
        return texto
    import json
    for g in json.loads((pasta / "ganchos.json").read_text(encoding="utf-8")):
        if g["modulo"] != modulo:
            continue
        assin = f"void {g['funcao']}(spu_context* ctx) {{\n"
        if assin not in texto:
            raise StepError(f"--spu-ganchos: {g['funcao']} não está em {modulo}")
        texto = texto.replace(assin, assin + f"        {g['chamada']}\n", 1)
        inc = f'#include "{(pasta / g["cabecalho"]).as_posix()}"\n'
        if inc not in texto:
            ultimo = texto.rfind("#include ", 0, texto.find("\nvoid "))
            fim = texto.index("\n", ultimo) + 1
            texto = texto[:fim] + inc + texto[fim:]
    return texto


def add_spu_jobs(args, proj: Path, cm: Path):
    """Os módulos de job Wws traduzidos por tools/lift_jobmods.py --engine-elf (um spu_recomp.c por módulo e o
    jobmods_register.c, que os registra num construtor como regiões verificadas pelo EA de origem)."""
    jobs = Path(args.spu_jobs).resolve()
    rt = (Path(args.ps3recomp).resolve() / "runtime" / "spu").as_posix()
    fontes = sorted(jobs.glob("jobmod_*/spu_recomp.c")) + [jobs / "jobmods_register.c"]
    if len(fontes) < 2 or not fontes[-1].is_file():
        raise StepError(f"--spu-jobs: {jobs} não tem jobmod_*/spu_recomp.c e jobmods_register.c")
    for c in fontes[:-1]:   # o include relativo ao ps3recomp vira um include pelo caminho de busca
        t = c.read_text(encoding="utf-8")
        if '"../../runtime/spu/' in t:
            c.write_text(t.replace('"../../runtime/spu/', '"'), encoding="utf-8")
    if args.spu_reg_locais:
        # Registradores SPU em variáveis locais (ps3recomp tools/spu_reg_locals.py): cópias reescritas no projeto,
        # as fontes de --spu-jobs ficam como estão.
        sys.path.insert(0, str(Path(args.ps3recomp).resolve() / "tools"))
        from spu_reg_locals import localize_source
        from spu_float_inputs import mark_float_inputs
        from spu_inline_fallthrough import inline_fallthrough
        destino = proj / "spu_jobs_rl"
        novas = []
        for c in fontes[:-1]:
            d = destino / c.parent.name
            d.mkdir(parents=True, exist_ok=True)
            shutil.copy2(c.parent / "spu_recomp.h", d / "spu_recomp.h")
            texto = aplica_ganchos(args, c.parent.name, c.read_text(encoding="utf-8"))
            if not args.sem_fundir:   # o trecho seguinte (preâmbulo -> laço) na mesma função C
                texto = inline_fallthrough(texto, max_lines=args.fundir_linhas, max_depth=args.fundir_trechos)[0]
            texto = localize_source(texto, max_lines=args.fundir_linhas + 100)
            if args.spu_float == "aprox":   # operandos de float a limitar (SPU_AX_CLAMP, ver spu_simd)
                texto = mark_float_inputs(texto, chains=not args.sem_cadeias, flow=args.fluxo_float, ls_assumed=args.float_ls)[0]
            texto = spu_vivos(args, texto, jobs=True, nome=c.parent.name)
            alvo = d / "spu_recomp.c"
            if not alvo.is_file() or alvo.read_text(encoding="utf-8") != texto:
                alvo.write_text(texto, encoding="utf-8")
            novas.append(alvo)
        fontes = novas + fontes[-1:]
    lista = "\n".join(f'    "{c.as_posix()}"' for c in fontes)
    cm.write_text(cm.read_text(encoding="utf-8") + "\n# GOW3: módulos de job Wws traduzidos (nativos)\n"
                  f"set(GOW3_SPU_JOBS\n{lista}\n)\n"
                  "target_sources(${PROJECT_NAME} PRIVATE ${GOW3_SPU_JOBS})\n"
                  "list(APPEND SPU_SOURCES ${GOW3_SPU_JOBS})\n"
                  f'target_include_directories(${{PROJECT_NAME}} PRIVATE "{rt}")\n', encoding="utf-8")


def spu_dir_projeto(args, proj: Path) -> Path:
    """A SPU_DIR que o CMake compila. Com --spu-reg-locais, um espelho dela no projeto com cada spu_recomp.c reescrito
    para registradores locais (spu_reg_locals.py; o policy module Wws roda a cada job EDGE); a pasta de --spu-dir
    fica como está."""
    origem = Path(args.spu_dir).resolve()
    if not args.spu_reg_locais:
        return origem
    sys.path.insert(0, str(Path(args.ps3recomp).resolve() / "tools"))
    from spu_reg_locals import localize_source
    from spu_float_inputs import mark_float_inputs
    from spu_inline_fallthrough import inline_fallthrough
    destino = proj / "spu_dir_rl"
    if destino.exists():
        shutil.rmtree(destino)
    shutil.copytree(origem, destino)
    for c in destino.glob("*/spu_recomp.c"):
        texto = aplica_ganchos(args, c.parent.name, c.read_text(encoding="utf-8"))
        if not args.sem_fundir:
            texto = inline_fallthrough(texto, max_lines=args.fundir_linhas, max_depth=args.fundir_trechos)[0]
        texto = localize_source(texto, max_lines=args.fundir_linhas + 100)
        if args.spu_float == "aprox":
            texto = mark_float_inputs(texto, chains=not args.sem_cadeias, flow=args.fluxo_float, ls_assumed=args.float_ls)[0]
        texto = spu_vivos(args, texto, nome=c.parent.name)
        c.write_text(texto, encoding="utf-8")
    return destino


def spu_vivos(args, texto: str, jobs: bool = False, nome: str = "") -> str:
    """--spu-vivos: nas saídas das funções SPU com registradores locais, grava de volta só os registradores vivos
    (ps3recomp tools/spu_live_flush.py, vivacidade sobre o módulo inteiro). "seguro": num retorno tudo está vivo;
    "abi": num retorno só r0-r3 e r80-r127 (os preservados da ABI da SPU), o que vale se quem chama é código
    compilado. "abi-jobs": "abi" só nos módulos de job (--spu-jobs), "seguro" no resto (o PM Wws trava com "abi")."""
    if args.spu_vivos == "nao":
        return texto
    sys.path.insert(0, str(Path(args.ps3recomp).resolve() / "tools"))
    import spu_live_flush
    abi = args.spu_vivos == "abi" or (args.spu_vivos == "abi-jobs" and jobs)
    filtro = os.environ.get("GOW3_VIVOS_ABI_MODS", "")   # depuração: "abi" só nos módulos com um destes trechos
    if abi and filtro:
        abi = any(f and f in nome for f in filtro.split(","))
    ret = spu_live_flush.ABI_RET_LIVE if abi else spu_live_flush.ALL
    if args.spu_vivos == "abi-auto":   # só nos jobs; por função, "tudo" onde quem chama lê um volátil depois
        return spu_live_flush.process(texto, auto_abi=jobs)[0]
    return spu_live_flush.process(texto, ret)[0]


def ppu_restrict_dir(args, state) -> str:
    """--ppu-restrict: uma cópia do código PPU traduzido com o contexto de cada função como `ppu_context* __restrict
    ctx`. Sem isso o compilador relê ctx->gpr[n] depois de toda escrita na memória do jogo (um ponteiro de byte que
    ele não sabe separar do contexto); com o restrict os registradores do PPU ficam em registradores do host entre
    as chamadas, perto do que a tradução com variáveis locais do Ascension dá. Vale porque nada no runtime altera um
    contexto por outro ponteiro enquanto a função roda (nenhum ponteiro de contexto em variável de thread)."""
    src = Path(state["recomp_dir"])
    if not getattr(args, "ppu_restrict", False):
        return str(src)
    dst = src.parent / (src.name + "_restrict")
    dst.mkdir(exist_ok=True)
    n = 0
    for f in src.iterdir():
        if not f.is_file():
            continue
        g = dst / f.name
        if g.is_file() and g.stat().st_mtime >= f.stat().st_mtime:
            continue
        if f.suffix in (".cpp", ".c"):
            t = f.read_text(encoding="utf-8", errors="surrogateescape")
            g.write_text(t.replace("(ppu_context* ctx) {", "(ppu_context* __restrict ctx) {"),
                         encoding="utf-8", errors="surrogateescape")
        else:
            shutil.copy2(f, g)
        n += 1
    print(f"  --ppu-restrict: {dst} ({n} arquivos reescritos)")
    return str(dst)


def spu_simd(args, cm: Path):
    """O modelo dá -O2 e SPU_USE_DISPATCH_MT só às imagens da SPU_DIR, e nenhuma fonte SPU recebe SIMD além do
    SSE2: o spu_shufb do código traduzido fica no laço de 16 bytes e fa/fm/fma do SPU, uma faixa por vez (os
    mais vistos no perfil da fase). Com --spu-simd avx2 (padrão) todas as fontes SPU, os módulos de job também,
    ganham -O2 -mavx2 -mfma e usam o caminho de 4 faixas do spu_helpers.h (exato, com correção faixa a faixa);
    sse41 deixa só o pshufb, para CPUs sem AVX2. -ffp-contract=off fica explícito."""
    # -w: no clang-cl o -Wall do modelo vale -Weverything, e a análise dos avisos nas funções longas com gotos e
    # registradores locais levava minutos por módulo de job.
    # -pre-RA-sched=list-burr (o escalonador do SelectionDAG que reduz registradores): no código dos jobs o
    # derramamento na pilha é ~25% das amostras (16 registradores AVX para 128 da SPU); ~6% menos acessos à pilha
    # nas funções quentes e ~2% de us/job (05/11).
    opts = (args.spu_opt or "-O2;-mllvm;-pre-RA-sched=list-burr") + ";-ffp-contract=off;-w;" + ("-mavx2;-mfma" if args.spu_simd == "avx2" else "-msse4.1")
    # --spu-float aprox: fa/fm/fma do SPU como as operações do host (SPU_FLOAT_APPROX do spu_helpers.h, como o
    # "approximate xfloat" padrão do RPCS3); exato = a emulação bit a bit (truncamento, faixa estendida).
    # SPU_LS_NODIAG: sem o teste das sondas de LS (SPU_LS_WATCH, SPU_SMC_WATCH...) em cada lqd/stqd; --spu-ls-diag
    # volta a compilá-las.
    # SPU_AX_NOFLUSH: no aproximado, o resultado de fa/fm/fma sai como o host o deixou, sem zerar denormais e o -0
    # a cada operação (três instruções dependentes no caminho crítico das cadeias de fma); os denormais ficam com o
    # FTZ/DAZ das threads de SPU (SPU_FTZ=1 no passo rodar). ~52,9 -> ~50,4 us por job EDGE.
    # SPU_AX_CLAMP: sem teste e desvio por operação; o resultado é limitado a +-FLT_MAX e um operando só onde
    # tools/spu_float_inputs.py o marcou (não veio de outra operação de float). Precisa das fontes marcadas, que só
    # as cópias de --spu-reg-locais recebem. Laço mais quente das EDGE: 57 -> ~36 ns por iteração.
    # SPU_INLINE_WRCH: os canais de parâmetro do MFC (LSA, EAH, EAL, Size, TagID, WrTagMask) gravados em linha no
    # código traduzido, sem chamar o despachante de canais (spu_helpers.h).
    defs = ("SPU_USE_DISPATCH_MT;SPU_INLINE_WRCH=1" + (";SPU_FLOAT_APPROX;SPU_AX_NOFLUSH=1" if args.spu_float == "aprox" else "")
            + (";SPU_AX_CLAMP=1" if args.spu_float == "aprox" and args.spu_reg_locais else "")
            + ("" if args.spu_ls_diag else ";SPU_LS_NODIAG"))
    # --spu-pgo: otimização guiada por perfil só no código SPU. "gerar" instrumenta (rodar com GOW3_PGO=<início>,<fim>
    # e LLVM_PROFILE_FILE, depois llvm-profdata merge); um caminho .profdata compila usando esse perfil.
    pgo_link = ""
    if args.spu_pgo == "gerar":
        opts += ";-fprofile-instr-generate"
        cl = shutil.which("clang-cl", path=(vs_environment() or {}).get("PATH")) or shutil.which("clang-cl")
        rt = Path(cl or ".").resolve().parent.parent / "lib" / "clang"
        libs = sorted(rt.glob("*/lib/windows/clang_rt.profile-x86_64.lib")) if rt.is_dir() else []
        if not libs:
            raise StepError("clang_rt.profile-x86_64.lib não encontrada ao lado do clang-cl (--spu-pgo gerar)")
        pgo_link = f'target_link_libraries(${{PROJECT_NAME}} PRIVATE "{libs[-1].as_posix()}")\n'
    elif args.spu_pgo:
        opts += f";-fprofile-instr-use={Path(args.spu_pgo).as_posix()}"
    cm.write_text(cm.read_text(encoding="utf-8") + "\n# GOW3: SIMD do host no código SPU traduzido\n"
                  'if(SPU_SOURCES AND (NOT MSVC OR CMAKE_C_COMPILER_ID MATCHES "Clang"))\n'
                  "    set_source_files_properties(${SPU_SOURCES} PROPERTIES\n"
                  '        INCLUDE_DIRECTORIES "${PS3RECOMP_DIR}/runtime/spu"\n'
                  f'        COMPILE_DEFINITIONS "{defs}"\n'
                  f'        COMPILE_OPTIONS "{opts}")\n'
                  "endif()\n" + pgo_link, encoding="utf-8")
    # --ppu-pgo: o mesmo para o código PPU traduzido (RECOMP_SOURCES). No Ascension, PGO no PPU tirou ~10% do quadro;
    # aqui a SPU do EDGE dorme ~21% esperando o PPU entregar a próxima lista. "gerar" instrumenta, um .profdata
    # compila com o perfil (rodar com GOW3_PGO=<início>,<fim> e LLVM_PROFILE_FILE, como no --spu-pgo).
    if args.ppu_avx2:
        # AVX2 + FMA3 no código PPU traduzido: o ppu_vmx.h liga o VMX_FAST_FP (vaddfp/vsubfp/vmaddfp/vnmsubfp em
        # quatro faixas, os mesmos bits do por faixa: 4 milhões de casos conferidos). O exe já pede AVX2 pelas SPUs.
        cm.write_text(cm.read_text(encoding="utf-8") + "\n# GOW3: AVX2/FMA no código PPU traduzido\n"
                      'set_property(SOURCE ${RECOMP_SOURCES} APPEND PROPERTY COMPILE_OPTIONS "-mavx2" "-mfma")\n',
                      encoding="utf-8")
    if args.ppu_pgo:
        ppu = ("-fprofile-instr-generate" if args.ppu_pgo == "gerar"
               else f"-fprofile-instr-use={Path(args.ppu_pgo).as_posix()}")
        extra = ""
        if args.ppu_pgo == "gerar" and not pgo_link:
            cl = shutil.which("clang-cl", path=(vs_environment() or {}).get("PATH")) or shutil.which("clang-cl")
            rt = Path(cl or ".").resolve().parent.parent / "lib" / "clang"
            libs = sorted(rt.glob("*/lib/windows/clang_rt.profile-x86_64.lib")) if rt.is_dir() else []
            if not libs:
                raise StepError("clang_rt.profile-x86_64.lib não encontrada ao lado do clang-cl (--ppu-pgo gerar)")
            extra = f'target_link_libraries(${{PROJECT_NAME}} PRIVATE "{libs[-1].as_posix()}")\n'
        # sem aviso para funções que o perfil não cobre (a fase não roda tudo)
        cm.write_text(cm.read_text(encoding="utf-8") + "\n# GOW3: PGO do código PPU traduzido\n"
                      "set_property(SOURCE ${RECOMP_SOURCES} APPEND PROPERTY COMPILE_OPTIONS "
                      f'"{ppu}" "-Wno-profile-instr-unprofiled" "-Wno-profile-instr-out-of-date")\n'
                      + extra, encoding="utf-8")


def use_gow3_rsx(proj: Path, cm: Path):
    """No Windows, o main.cpp do modelo chama o motor de desenho por gow3_rsx.cpp, que escolhe em tempo de
    execução entre o backend D3D12 (padrão) e o live draw (RSX_LIVE_DRAW=1)."""
    main = proj / "main.cpp"
    text = main.read_text(encoding="utf-8")
    if "template_rsx_init" in text:
        return   # ps3kit (ramo gow3): o próprio modelo já escolhe o live draw com RSX_LIVE_DRAW
    old = ("#  define rsx_backend_init    rsx_d3d12_backend_init\n"
           "#  define rsx_backend_present rsx_d3d12_backend_present\n"
           "#  define rsx_backend_pump    rsx_d3d12_backend_pump_messages\n")
    if old not in text:
        raise StepError("main.cpp do modelo mudou: não achei os rsx_backend_* do D3D12")
    new = ('extern "C" int  gow3_rsx_init(uint32_t w, uint32_t h, const char* title);\n'
           'extern "C" void gow3_rsx_present(void);\n'
           'extern "C" int  gow3_rsx_pump(void);\n'
           "#  define rsx_backend_init    gow3_rsx_init\n"
           "#  define rsx_backend_present gow3_rsx_present\n"
           "#  define rsx_backend_pump    gow3_rsx_pump\n")
    main.write_text(text.replace(old, new), encoding="utf-8")
    cm.write_text(cm.read_text(encoding="utf-8") + "\n# GOW3: motor de desenho escolhido em tempo de execução\n"
                  f'target_sources(${{PROJECT_NAME}} PRIVATE "{(HERE / "gow3_rsx.cpp").as_posix()}")\n',
                  encoding="utf-8")


def step_projeto(args, work: Path, state: dict, progress):
    proj = work / "projeto"
    if proj.exists():
        shutil.rmtree(proj)
    shutil.copytree(Path(args.ps3recomp) / "templates" / "project", proj)
    cm = proj / "CMakeLists.txt"
    cm.write_text(cm.read_text(encoding="utf-8").replace("project(MyGameRecomp", "project(GOW3Native"), encoding="utf-8")
    if args.lle_libsre:
        add_libsre_lle(args, proj, cm)
    # Diagnóstico do GOW3 (GOW3_WATCHDOG) e o .map do link para resolver os RVAs que ele imprime.
    cm.write_text(cm.read_text(encoding="utf-8") + "\n# GOW3: watchdog e mapa do link\n"
                  f'target_sources(${{PROJECT_NAME}} PRIVATE "{(HERE / "gow3_diag.cpp").as_posix()}")\n'
                  "if(MSVC)\n    target_link_options(${PROJECT_NAME} PRIVATE /MAP)\nendif()\n", encoding="utf-8")
    use_gow3_rsx(proj, cm)
    # Arquivos locais opcionais do runtime que só se registram por construtor (código do ps3kit usado com permissão
    # do Arnaldo, fora do patch público): entram direto no exe, porque um objeto não referenciado da biblioteca
    # estática do runtime seria descartado na ligação. Quem não os tem compila igual.
    for extra in sorted((Path(args.ps3recomp) / "runtime" / "spu").glob("*_ps3kit.c")):
        cm.write_text(cm.read_text(encoding="utf-8") + f'target_sources(${{PROJECT_NAME}} PRIVATE "{extra.as_posix()}")\n',
                      encoding="utf-8")
    if args.spu_jobs:
        add_spu_jobs(args, proj, cm)
    spu_simd(args, cm)
    build = work / "build"
    env = dict(os.environ)
    vs = vs_environment()
    if os.name == "nt":
        if vs is None:
            raise StepError("Visual Studio 2022 (Build Tools) com C++ e clang-cl não encontrado. Instale: "
                            "winget install Microsoft.VisualStudio.2022.BuildTools --override \"--quiet --wait "
                            "--add Microsoft.VisualStudio.Workload.VCTools --add "
                            "Microsoft.VisualStudio.Component.VC.Llvm.Clang --includeRecommended\"")
        env.update(vs)
        cc = ["-DCMAKE_C_COMPILER=clang-cl", "-DCMAKE_CXX_COMPILER=clang-cl"]
    else:
        cc = ["-DCMAKE_C_COMPILER=clang", "-DCMAKE_CXX_COMPILER=clang++"]
    missing = check_tools(env)
    if missing:
        raise StepError("faltam ferramentas: " + ", ".join(missing) + " (winget install Kitware.CMake Ninja-build.Ninja)")
    cmd = ["cmake", "-S", proj, "-B", build, "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
           f"-DPS3RECOMP_DIR={Path(args.ps3recomp).resolve()}", f"-DRECOMP_DIR={ppu_restrict_dir(args, state)}"] + cc
    if args.spu_dir:
        cmd.append(f"-DSPU_DIR={spu_dir_projeto(args, proj)}")
    elif not args.sem_spu:
        cmd.append(f"-DPORT_SPU_INPUTS={state['elf']}")
    cmd += ffmpeg_cmake_args(args)
    if build.exists():
        shutil.rmtree(build)
    proc = run(cmd, work, "projeto", env=env)
    if proc.returncode:
        raise StepError("CMake falhou:\n" + tail(log_path(work, "projeto"), 40))
    spu = re.findall(r"Lifted SPU:.*", log_path(work, "projeto").read_text(errors="replace"))
    state.update(build_dir=str(build), spu=spu[-1] if spu else None)
    progress("Projeto configurado" + (f" ({spu[-1]})" if spu else ""))


def step_compilar(args, work: Path, state: dict, progress):
    env = dict(os.environ)
    vs = vs_environment()
    if vs:
        env.update(vs)
    progress("Compilando (a primeira vez leva de 20 a 60 minutos e usa bastante memória)...")
    t0 = time.time()
    cmd = ["cmake", "--build", state["build_dir"]]
    if args.jobs:
        cmd += ["-j", str(args.jobs)]
    lp = log_path(work, "compilar")
    inicio = lp.stat().st_size if lp.exists() else 0
    proc = run(cmd, work, "compilar", env=env)
    # O log acumula as compilações anteriores: só a saída desta conta.
    with open(lp, "rb") as f:
        f.seek(inicio)
        text = f.read().decode("utf-8", errors="replace")
    # Só as linhas de diagnóstico (arquivo(linha,col): error: ...), não os trechos de código que os warnings
    # citam ("  145 |   DWORD error = ..."), que escondiam o erro real.
    errors = [ln for ln in text.splitlines()
              if re.search(r"\berror( [A-Z]+\d+)?:|FAILED:|fatal error|LNK\d{4}", ln) and " | " not in ln[:12]][:40]
    state.update(build_seconds=round(time.time() - t0), build_errors=errors)
    if proc.returncode:
        raise StepError("compilação falhou:\n" + "\n".join(errors[:20]))
    exe = next((p for p in Path(state["build_dir"]).glob("GOW3Native*") if p.suffix in (".exe", "")), None)
    if exe is None:
        raise StepError("compilação terminou sem GOW3Native")
    state.update(exe=str(exe), exe_bytes=exe.stat().st_size)
    if args.lle_libsre:
        shutil.copy2(Path(args.lle_libsre) / "libsre_image.bin", exe.parent / "libsre_image.bin")
    if args.ffmpeg:   # as DLLs LGPL do FFmpeg ao lado do .exe (ficam no PC do usuário)
        for dll in (Path(args.ffmpeg) / "bin").glob("*.dll"):
            shutil.copy2(dll, exe.parent / dll.name)
    progress(f"Executável: {exe} ({exe.stat().st_size / 1e6:.0f} MB) em {state['build_seconds'] // 60} min")


MARKERS = {
    "nids_nao_implementados": re.compile(r"[Uu]nimplemented NID|missing NID|unknown NID"),
    "chamadas_indiretas_sem_destino": re.compile(r"unresolved indirect call"),
    "falhas_de_memoria": re.compile(r"(?i)access violation|segfault|guest fault|null read|bad address"),
    "erros": re.compile(r"(?i)\berror\b|fatal"),
}
# Com GCM_FLIPCOUNT=1 o cellGcmSys registra "[flip] N at T ms" a cada flip (todos até 400, depois 1 em 10).
FLIP_RE = re.compile(r"^\[flip\] (\d+) at (\d+) ms", re.M)


def step_rodar(args, work: Path, state: dict, progress):
    exe = state.get("exe")
    if not exe:
        raise StepError("compile antes (passo compilar)")
    env = dict(os.environ)
    env.setdefault("GCM_FLIPCOUNT", "1")
    # O RSX do GOW3 espera os SPUs como no hardware: SEMAPHORE_ACQUIRE bloqueia (as tarefas MLAA
    # liberam o semáforo do quadro) e um salto para si mesmo ("park") espera ser reescrito, sem o
    # atalho de seguir o put. Sem isso o RSX terminava dois quadros de uma vez, o RsxSync disparava
    # duas vezes seguidas, duas tarefas MLAA pulavam um quadro e a thread principal esperava para sempre.
    env.setdefault("GCM_SEMA_ACQUIRE", "1")
    env.setdefault("GCM_PARK_GRACE_MS", "3600000")
    env.setdefault("GCM_PARK_WAIT_MS", "3600000")   # o mesmo ajuste com o nome do ps3kit
    # O player de vídeo do GOW3 pausa o envio de AUs por mais de 1,5 s; o "idle drain" do cellVdec
    # esvaziava o decodificador com flush nessa pausa e todas as AUs P/B seguintes saíam vazias.
    env.setdefault("VDEC_IDLE_DRAIN_MS", "0")
    # Motor de desenho "live draw" (gow3_rsx.cpp): com ele aparecem o logo e a abertura; o backend
    # D3D12 padrão grava os desenhos para o flip e não mostra o que o jogo compõe pela memória.
    env.setdefault("RSX_LIVE_DRAW", "1")
    # A thread de apresentação olha a FIFO sem dormir (GCM_DRAIN_MS=0 do main.cpp do modelo: só cede a CPU): na fase o
    # andador vive estacionado nos buracos que os jobs EDGE preenchem sem avisar ninguém. 4 ms -> 1 ms: ~6,1 -> ~7,1
    # quadros/s; 1 ms -> 0: ~8,3 -> ~8,8. Custa um núcleo girando.
    env.setdefault("GCM_DRAIN_MS", "0")
    # Memória por thread do último motor MFC do ps3recomp (desligada por padrão lá): sem ela o mfc_for, que
    # procura o motor da SPU a cada acesso a canal, era 4 a 5% das threads SPU mais ocupadas na fase.
    env.setdefault("SPU_MFC_LOOKUP_CACHE", "1")
    # Um policy module que fez trabalho roda de novo na mesma SPU sem devolver a vez à thread do kernel
    # do SPURS (cellSpurs.c, spurs_pm_sticky_take): cada devolução custava ~20 us por job EDGE.
    # 1024 (era 64): cada devolução ao kernel podia levar a cadeia EDGE a outra thread/núcleo, com a LS e o código frios
    # no cache (64 -> 100000: ~50 -> ~48,3 us por job). Sem teto, porém, um workload que só podia rodar naquela SPU, ou
    # que o kernel só sonda de tempos em tempos (as listas Wws sem chute), ficava sem vez: o jogo travou 2 vezes em 15
    # na inicialização. 1024 repetições são ~50 ms.
    env.setdefault("SPURS_PM_STICKY", "1024")
    # SPURS_PM_AFFINITY=1 (cada thread de SPU num núcleo próprio) dava ~1% (us/job(60s) ~48,0 -> ~47,5), mas travava a
    # abertura às vezes (6 em 34 execuções com ela, 0 em 22 sem): fica desligada.
    # O policy module Wws reenvia o código do job a cada job (~100 mil GETs por segundo): compara só o trecho
    # reenviado e mantém o módulo verificado e o cache de despacho (spu_overlay_note_get). Verificações completas
    # de ~58 KB: ~7 mil -> ~700 por segundo.
    env.setdefault("SPU_OVL_INCREMENTAL", "1")
    # FTZ/DAZ nas threads de SPU (denormais como zero, como o SPU): o float aproximado sem zerar a cada operação
    # (SPU_AX_NOFLUSH) conta com isso.
    env.setdefault("SPU_FTZ", "1")
    if args.jogo:
        root = Path(args.jogo)
        if (root / "PS3_GAME").is_dir():
            env["PS3_VFS_ROOT"] = str(root)
    lp = log_path(work, "rodar")
    progress(f"Rodando o GOW3Native por até {args.segundos} s (log: {lp})...")
    t0 = time.time()
    with open(lp, "w", encoding="utf-8", errors="replace") as f:
        proc = subprocess.Popen([exe, state["elf"]], stdout=f, stderr=subprocess.STDOUT, env=env, cwd=work)
        try:
            code = proc.wait(timeout=args.segundos)
            ended = f"terminou sozinho (código {code})"
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(30)
            code = None
            ended = f"ainda rodando após {args.segundos} s (encerrado pelo script)"
    text = lp.read_text(encoding="utf-8", errors="replace")
    counts = {k: len(rx.findall(text)) for k, rx in MARKERS.items()}
    flips = FLIP_RE.findall(text)
    counts["flips"] = int(flips[-1][0]) if flips else 0
    if len(flips) > 1 and int(flips[-1][1]) > 0:
        counts["flips_por_s"] = round(int(flips[-1][0]) * 1000 / int(flips[-1][1]))
    nids = sorted(set(re.findall(r"NID (0x[0-9A-Fa-f]{8})[^\n]*?in module (\w+)", text)))[:60]
    state.update(run_seconds=round(time.time() - t0), run_end=ended, run_code=code, run_counts=counts,
                 run_missing_nids=[f"{m}:{n}" for n, m in nids], run_tail=text.splitlines()[-60:])
    progress(f"Execução: {ended}; " + ", ".join(f"{k}={v}" for k, v in counts.items()))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jogo", help="pasta do jogo (a que contém PS3_GAME)")
    ap.add_argument("--elf", help="EBOOT.ELF já gerado (senão usa o do analisador ou o RPCS3)")
    ap.add_argument("--rpcs3", help="rpcs3.exe (para gerar o EBOOT.ELF, se preciso)")
    ap.add_argument("--ps3recomp", required=True, help="checkout do ps3recomp (versão fixada + patches do projeto)")
    ap.add_argument("--trabalho", required=True, help="pasta de trabalho (tudo o que é gerado fica aqui)")
    ap.add_argument("--passos", default=",".join(STEPS), help="passos a rodar, em ordem (padrão: todos)")
    ap.add_argument("--arquivos", type=int, default=96, help="arquivos .cpp da tradução (mais = menos memória por arquivo)")
    ap.add_argument("--jobs", type=int, help="compilações em paralelo (padrão: o do Ninja)")
    ap.add_argument("--segundos", type=int, default=120, help="tempo de execução no passo rodar")
    ap.add_argument("--toc", help="TOC explícito (só para ELFs de teste com descritores ELFv1)")
    ap.add_argument("--sem-spu", action="store_true", help="não traduzir os programas SPU embutidos")
    ap.add_argument("--lle-libsre", help="pasta da libsre relocada e recompilada (lifted/, libsre_image.bin): "
                                         "a LFQueue passa a rodar o código real da Sony")
    ap.add_argument("--pular-videos", action="store_true",
                    help="aplica numa cópia local do EBOOT o patch 'Skip any videos with X' (EBOOT 1.00): "
                         "o X pula os vídeos, como no RPCS3")
    ap.add_argument("--patch-rpcs3", action="append", default=[], metavar="NOME",
                    help="aplica ao EBOOT (cópia local) um patch PPU do patch.yml do RPCS3, pelo nome do RPCS3 "
                         "(repetível). native/tools/rpcs3_patches.py --listar mostra os do GOW3 1.00")
    ap.add_argument("--patch-yml", help="patch.yml do RPCS3 (padrão: <pasta do rpcs3>/patches/patch.yml)")
    ap.add_argument("--spu-jobs", help="pasta dos módulos de job Wws traduzidos por "
                                       "tools/lift_jobmods.py --engine-elf (rodam nativos, não no interpretador)")
    ap.add_argument("--ffmpeg", help="FFmpeg LGPL compartilhado (pasta com include/ e bin/, mesma série das DLLs): "
                                     "o cellVdec decodifica os vídeos do jogo")
    ap.add_argument("--spu-reg-locais", action=argparse.BooleanOptionalAction, default=True,
                    help="registradores SPU dos módulos de job em variáveis locais de cada função (padrão: ligado)")
    ap.add_argument("--spu-ls-diag", action="store_true",
                    help="compila as sondas de LS do runtime SPU (SPU_LS_WATCH etc.) no código traduzido")
    ap.add_argument("--spu-opt", default="",
                    help="opções de otimização das fontes SPU no lugar de -O2;-mllvm;-pre-RA-sched=list-burr, separadas por ;")
    ap.add_argument("--spu-float", choices=["aprox", "exato"], default="aprox",
                    help="ponto flutuante do SPU: aprox = operações do host (como o RPCS3); exato = bit a bit")
    ap.add_argument("--sem-fundir", action="store_true",
                    help="não juntar a função SPU traduzida com o trecho seguinte (spu_inline_fallthrough.py)")
    ap.add_argument("--fundir-linhas", type=int, default=500, help="tamanho máximo de uma função fundida")
    ap.add_argument("--spu-ganchos", default="",
                    help="pasta com ganchos.json: chamadas nativas inseridas em funções SPU traduzidas (só local; "
                         "padrão: <trabalho>/edge_nativo, quando existe)")
    ap.add_argument("--sem-ganchos", action="store_true", help="não aplicar os ganchos nativos")
    ap.add_argument("--float-ls", action="store_true",
                    help="operando de float que vem direto de uma leitura da LS marcado SPU_AXL (em vez de SPU_AXI); "
                         "com -DSPU_AXL_NOCLAMP=1 nas fontes SPU ele fica sem o limite (estudo)")
    ap.add_argument("--sem-fluxo-float", dest="fluxo_float", action="store_false",
                    help="sem o mark_body_flow do spu_float_inputs (padrão: um operando de float fica sem SPU_AXI também "
                         "depois de rótulos e cópias, quando todo caminho o traz de outra operação de float; -2%% por job EDGE)")
    ap.add_argument("--sem-cadeias", action="store_true",
                    help="limitar a ±FLT_MAX também os resultados de float que só alimentam outra operação de float")
    ap.add_argument("--spu-vivos", choices=["nao", "seguro", "abi", "abi-jobs", "abi-auto"], default="seguro",
                    help="gravar de volta só os registradores SPU vivos nas saídas das funções (spu_live_flush.py)")
    ap.add_argument("--fundir-trechos", type=int, default=4, help="quantos trechos seguintes fundir no máximo")
    ap.add_argument("--spu-pgo", default="",
                    help="PGO do código SPU: 'gerar' instrumenta; um arquivo .profdata compila com o perfil")
    ap.add_argument("--ppu-restrict", action="store_true",
                    help="código PPU traduzido com o contexto __restrict. QUEBRA o jogo (05/11: fica preso antes da fase, a 72 flips/s): algum código depende do contexto visto por outro caminho. Só para investigar.")
    ap.add_argument("--ppu-avx2", action="store_true",
                    help="código PPU traduzido com -mavx2 -mfma (liga o caminho rápido de float do VMX)")
    ap.add_argument("--ppu-pgo", default="",
                    help="PGO do código PPU traduzido: 'gerar' instrumenta; um arquivo .profdata compila com o perfil")
    ap.add_argument("--spu-simd", choices=["avx2", "sse41"], default="avx2",
                    help="SIMD do host no código SPU traduzido: avx2 (padrão, com FMA3) ou sse41 (CPUs sem AVX2)")
    ap.add_argument("--spu-dir", help="SPU_DIR já montada (programas SPU e policy modules recompilados por fora)")
    args = ap.parse_args()
    if not args.elf and not args.jogo:
        ap.error("indique --jogo ou --elf")
    work = Path(args.trabalho).resolve()
    work.mkdir(parents=True, exist_ok=True)
    # Sem o gow3_libsre_lle.cpp o PARAM.SFO não é lido (título BLES00000) e o jogo para antes do logo:
    # a libsre já preparada na pasta de trabalho entra sozinha.
    padrao_lle = work / "firmware" / "libsre_lle"
    if not args.lle_libsre and (padrao_lle / "libsre_image.bin").is_file():
        args.lle_libsre = str(padrao_lle)
        print(f"--lle-libsre não indicado: usando {padrao_lle}")
    state_file = work / "estado.json"
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.is_file() else {}
    resumo = work / "resumo.txt"

    def progress(msg):
        line = time.strftime("%H:%M:%S ") + msg
        print(line, flush=True)
        with open(resumo, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    funcs = {"elf": step_elf, "carregar": step_carregar, "traduzir": step_traduzir, "projeto": step_projeto,
             "compilar": step_compilar, "rodar": step_rodar}
    steps = [s.strip() for s in args.passos.split(",") if s.strip()]
    for s in steps:
        if s not in funcs:
            ap.error(f"passo desconhecido: {s} (passos: {', '.join(STEPS)})")
    ok = True
    for s in steps:
        progress(f"== {s} ==")
        t0 = time.time()
        try:
            funcs[s](args, work, state, progress)
            state.setdefault("steps", {})[s] = {"ok": True, "seconds": round(time.time() - t0)}
        except (StepError, subprocess.SubprocessError, OSError) as error:
            state.setdefault("steps", {})[s] = {"ok": False, "seconds": round(time.time() - t0), "error": str(error)[:4000]}
            progress(f"FALHOU em {s}: {error}")
            ok = False
        state_file.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")
        if not ok:
            break
    progress("TUDO CERTO" if ok else "PAROU (veja logs\\ e estado.json)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
