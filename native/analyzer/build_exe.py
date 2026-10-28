#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Empacota o GOW3_Native_Analyzer para Windows x64 (PyInstaller, pasta única) e gera o ZIP.

    python build_exe.py --ps3recomp <ps3recomp com o patch do projeto> --out dist

Inclui: ferramentas Python do ps3recomp (MIT), tabela de NIDs implementados, runtime do teste,
Unicorn (GPL-2.0) e o compilador zig (MIT) reduzido ao necessário para x86_64-windows-gnu.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
NAME = "GOW3_Native_Analyzer"


def stdlib_imports(folder: Path) -> list[str]:
    mods = set()
    for py in folder.glob("*.py"):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            else:
                continue
            for n in names:
                if n.split(".")[0] in sys.stdlib_module_names:
                    mods.add(n)
    return sorted(mods)


def prune_zig(dst: Path):
    lib = dst / "lib"
    for d in (lib / "libc").iterdir():
        if d.name not in ("mingw", "include"):
            shutil.rmtree(d, ignore_errors=True)
    for d in (lib / "libc" / "include").iterdir():
        if d.name != "any-windows-any":
            shutil.rmtree(d, ignore_errors=True)
    for name in ("libtsan", "docs", "build-web", "init", "lldb"):
        shutil.rmtree(lib / name, ignore_errors=True)
    shutil.rmtree(dst / "__pycache__", ignore_errors=True)


def disable_cfg(exe: Path) -> bool:
    """Desliga o Control Flow Guard no cabeçalho PE do executável.

    O carregador do PyInstaller vem com CFG ligado; com ele, o Windows encerra o processo
    (0xC0000409) quando o Unicorn salta para o código que ele próprio gera em tempo de execução
    (TCG do QEMU), que não está na lista de destinos válidos. O python.exe não usa CFG, por isso o
    mesmo código funciona fora do pacote."""
    import struct
    data = bytearray(exe.read_bytes())
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    assert data[pe:pe + 4] == b"PE\0\0"
    off = pe + 24 + 0x46  # OptionalHeader.DllCharacteristics (PE32+)
    dc = struct.unpack_from("<H", data, off)[0]
    if not dc & 0x4000:
        return False
    struct.pack_into("<H", data, off, dc & ~0x4000)
    exe.write_bytes(bytes(data))
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ps3recomp", required=True)
    ap.add_argument("--out", default="dist")
    args = ap.parse_args()
    ps3 = Path(args.ps3recomp).resolve()
    out = Path(args.out).resolve()
    build = HERE / "build_pkg"
    shutil.rmtree(build, ignore_errors=True)
    res = build / "res"
    tools_dst = res / "ps3recomp" / "tools"
    tools_dst.mkdir(parents=True)
    for f in (ps3 / "tools").iterdir():
        if f.is_file() and f.suffix in (".py", ".json", ".txt", ".toml"):
            shutil.copy2(f, tools_dst / f.name)
    shutil.copy2(ps3 / "LICENSE", res / "ps3recomp" / "LICENSE")
    # cabeçalho que o código gerado pelo lifter inclui (semântica exata de VMX)
    (res / "ps3recomp" / "runtime" / "ppu").mkdir(parents=True)
    shutil.copy2(ps3 / "runtime" / "ppu" / "ppu_vmx.h", res / "ps3recomp" / "runtime" / "ppu" / "ppu_vmx.h")

    # NIDs que o runtime do ps3recomp implementa (calculado aqui, onde as fontes C existem)
    sys.path.insert(0, str(ps3 / "tools"))
    import nid_database  # noqa: E402
    db = nid_database.NIDDatabase()
    db.load_implemented(str(ps3))
    table: dict[str, dict[str, str]] = {}
    for nid, mod, name in db.all_entries():
        table.setdefault(mod, {})[name] = f"0x{nid:08X}"
    (res / "hle_implemented.json").write_text(json.dumps(table, indent=0))
    print(f"NIDs implementados no ps3recomp: {sum(len(v) for v in table.values())}")

    shutil.copytree(HERE / "runtime", res / "runtime")
    import ziglang
    zsrc = Path(ziglang.__file__).parent
    shutil.copytree(zsrc, res / "ziglang")
    prune_zig(res / "ziglang")

    sep = os.pathsep
    hidden = stdlib_imports(tools_dst) + ["tkinter", "tkinter.ttk", "tkinter.filedialog", "tkinter.scrolledtext",
                                          "tkinter.messagebox", "multiprocessing", "concurrent.futures"]
    cmd = [str(HERE / f"{NAME}.py"), "--name", NAME, "--onedir", "--windowed", "--noconfirm", "--clean",
           "--distpath", str(out), "--workpath", str(build / "work"), "--specpath", str(build),
           "--paths", str(HERE), "--collect-all", "unicorn",
           "--add-data", f"{res / 'ps3recomp'}{sep}ps3recomp",
           "--add-data", f"{res / 'runtime'}{sep}runtime",
           "--add-data", f"{res / 'hle_implemented.json'}{sep}.",
           "--add-data", f"{res / 'ziglang'}{sep}ziglang"]
    for h in hidden:
        cmd += ["--hidden-import", h]
    import PyInstaller.__main__
    PyInstaller.__main__.run(cmd)

    app = out / NAME
    exe = app / f"{NAME}.exe"
    if exe.is_file():
        print("Control Flow Guard desligado no .exe:", disable_cfg(exe))
    shutil.copy2(HERE / "LEIA-ME.txt", app / "LEIA-ME.txt")
    lic = app / "LICENCAS"
    lic.mkdir(exist_ok=True)
    shutil.copy2(ps3 / "LICENSE", lic / "ps3recomp-MIT.txt")
    shutil.copy2(HERE / "THIRD_PARTY.txt", lic / "TERCEIROS.txt")
    if (REPO / "LICENSE").is_file():
        shutil.copy2(REPO / "LICENSE", lic / "GOW3_Native-GPL-2.0.txt")
    # código-fonte do próprio analisador (GPL-2.0) junto do programa
    with zipfile.ZipFile(app / "fonte_do_analisador.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(HERE.rglob("*")):
            rel = f.relative_to(HERE)
            if f.is_file() and not any(p in ("build_pkg", "dist", "__pycache__") for p in rel.parts):
                z.write(f, f"analyzer/{rel.as_posix()}")
        z.write(REPO / "native" / "ps3recomp-elfv1.patch", "ps3recomp-elfv1.patch")
        z.write(REPO / "native" / "PS3RECOMP_COMMIT.txt", "PS3RECOMP_COMMIT.txt")

    zip_path = out / f"{NAME}_Windows_x64.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in sorted(app.rglob("*")):
            if f.is_file():
                z.write(f, f"{NAME}/{f.relative_to(app).as_posix()}")
    print(f"ZIP: {zip_path} ({zip_path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
