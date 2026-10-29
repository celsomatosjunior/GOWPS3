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


def use_gow3_rsx(proj: Path, cm: Path):
    """No Windows, o main.cpp do modelo chama o motor de desenho por gow3_rsx.cpp, que escolhe em tempo de
    execução entre o backend D3D12 (padrão) e o live draw (RSX_LIVE_DRAW=1)."""
    main = proj / "main.cpp"
    text = main.read_text(encoding="utf-8")
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
           f"-DPS3RECOMP_DIR={Path(args.ps3recomp).resolve()}", f"-DRECOMP_DIR={state['recomp_dir']}"] + cc
    if args.spu_dir:
        cmd.append(f"-DSPU_DIR={Path(args.spu_dir).resolve()}")
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
    proc = run(cmd, work, "compilar", env=env)
    text = log_path(work, "compilar").read_text(errors="replace")
    errors = [ln for ln in text.splitlines() if re.search(r"error[: ]|FAILED:|fatal error|LNK\d{4}", ln)][:40]
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
    # O player de vídeo do GOW3 pausa o envio de AUs por mais de 1,5 s; o "idle drain" do cellVdec
    # esvaziava o decodificador com flush nessa pausa e todas as AUs P/B seguintes saíam vazias.
    env.setdefault("VDEC_IDLE_DRAIN_MS", "0")
    # Motor de desenho "live draw" (gow3_rsx.cpp): com ele aparecem o logo e a abertura; o backend
    # D3D12 padrão grava os desenhos para o flip e não mostra o que o jogo compõe pela memória.
    env.setdefault("RSX_LIVE_DRAW", "1")
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
    ap.add_argument("--ffmpeg", help="FFmpeg LGPL compartilhado (pasta com include/ e bin/, mesma série das DLLs): "
                                     "o cellVdec decodifica os vídeos do jogo")
    ap.add_argument("--spu-dir", help="SPU_DIR já montada (programas SPU e policy modules recompilados por fora)")
    args = ap.parse_args()
    if not args.elf and not args.jogo:
        ap.error("indique --jogo ou --elf")
    work = Path(args.trabalho).resolve()
    work.mkdir(parents=True, exist_ok=True)
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
