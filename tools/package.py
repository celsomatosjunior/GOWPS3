#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Monta o pacote portátil GOW3_PS3_PC_Windows_x64.zip.

Uso:
  python tools/package.py --app GOW3_PS3_PC.exe [--rpcs3-bin <pasta bin do RPCS3 compilado>]
                          --out <pasta de saída> [--licenses <pasta>] [--build-info <arquivo>]

Sem --rpcs3-bin, o pacote sai sem o RPCS3: o usuário instala o RPCS3 oficial pelo botão
"Instalar RPCS3..." (o aplicativo copia para runtime\rpcs3 e gera o manifesto).

Estrutura gerada:
  GOW3_PS3_PC/
    GOW3_PS3_PC.exe
    runtime/rpcs3/...            RPCS3 compilado (rpcs3.exe, Qt, DLLs do Visual C++)
    runtime/runtime_manifest.txt sha256, tamanho e caminho de cada arquivo do runtime
    licenses/                    licenças (GPL-2.0, Qt LGPL, terceiros do RPCS3)
    LEIA-ME.txt, FONTE.txt, BUILD_INFO.txt
"""

import argparse
import hashlib
import os
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = "GOW3_PS3_PC"
ZIP_NAME = "GOW3_PS3_PC_Windows_x64.zip"

# Nada disso pode ir no pacote: firmware, arquivos do jogo, licenças digitais, dados de usuário.
FORBIDDEN_NAMES = {"ps3updat.pup", "eboot.bin", "param.sfo", "ps3_disc.sfb"}
FORBIDDEN_SUFFIXES = {".pup", ".rap", ".edat", ".sdat", ".rif", ".pkg", ".iso"}
FORBIDDEN_DIRS = {"dev_flash", "dev_hdd0", "dev_hdd1", "dev_usb000", "portable", "savestates", "cache", "log"}
# Lixo de compilação que o próprio deploy do RPCS3 remove (.ci/deploy-windows.sh).
DROP_SUFFIXES = {".exp", ".lib", ".pdb", ".ilk", ".iobj", ".ipdb"}
DROP_NAMES = {"vc_redist.x64.exe"}
# O RPCS3 recusa o Visual C++ e o Vulkan fora da pasta do Windows (rpcs3/module_verifier.cpp):
# essas DLLs nunca vão ao lado do rpcs3.exe; o instalador oficial vai em runtime/redist.
WINDOWS_ONLY_PREFIXES = ("msvcp140", "vcruntime140", "concrt140", "vccorlib140", "vcomp140", "vulkan-1")


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_forbidden(path, base):
    rel = path.relative_to(base)
    lowered = [part.lower() for part in rel.parts]
    if any(part in FORBIDDEN_DIRS for part in lowered[:-1]):
        return f"pasta proibida em {rel}"
    if lowered[-1] in FORBIDDEN_NAMES or path.suffix.lower() in FORBIDDEN_SUFFIXES:
        return f"arquivo proibido {rel}"
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", required=True, type=Path)
    parser.add_argument("--rpcs3-bin", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--licenses", type=Path, help="pasta com licenças extras (copiada para licenses/)")
    parser.add_argument("--vcredist", type=Path, help="vc_redist.x64.exe oficial da Microsoft")
    parser.add_argument("--vcredist-version", help="versão mínima do Visual C++ exigida pelo RPCS3 compilado")
    parser.add_argument("--build-info", type=Path, help="texto com commits e versões da compilação")
    args = parser.parse_args()

    if args.rpcs3_bin and not (args.rpcs3_bin / "rpcs3.exe").is_file():
        sys.exit(f"rpcs3.exe não encontrado em {args.rpcs3_bin}")
    if not args.app.is_file():
        sys.exit(f"aplicativo não encontrado: {args.app}")

    stage = args.out / PACKAGE
    if stage.exists():
        shutil.rmtree(stage)
    runtime = stage / "runtime" / "rpcs3"
    runtime.mkdir(parents=True)
    shutil.copy2(args.app, stage / "GOW3_PS3_PC.exe")

    problems, entries = [], []
    sources = sorted(p for p in args.rpcs3_bin.rglob("*") if p.is_file()) if args.rpcs3_bin else []
    for source in sources:
        problem = check_forbidden(source, args.rpcs3_bin)
        if problem:
            problems.append(problem)
            continue
        if source.suffix.lower() in DROP_SUFFIXES or source.name.lower() in DROP_NAMES:
            continue
        if source.suffix.lower() == ".dll" and source.name.lower().startswith(WINDOWS_ONLY_PREFIXES):
            print(f"removido do pacote (precisa vir do Windows): {source.name}")
            continue
        target = runtime / source.relative_to(args.rpcs3_bin)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        rel = target.relative_to(stage / "runtime").as_posix()
        entries.append(f"{sha256(target)} {target.stat().st_size} {rel}")
    if args.vcredist:
        redist = stage / "runtime" / "redist"
        redist.mkdir(parents=True)
        shutil.copy2(args.vcredist, redist / "vc_redist.x64.exe")
        (redist / "version.txt").write_text((args.vcredist_version or "") + "\n", encoding="utf-8")
        for name in ("vc_redist.x64.exe", "version.txt"):
            target = redist / name
            entries.append(f"{sha256(target)} {target.stat().st_size} redist/{name}")
    if problems:
        sys.exit("Pacote recusado (conteúdo que não pode ser distribuído):\n  " + "\n  ".join(problems))

    if entries:
        (stage / "runtime" / "runtime_manifest.txt").write_text(
            "# sha256 tamanho caminho (gerado por tools/package.py)\n" + "\n".join(entries) + "\n", encoding="utf-8")
    else:
        (stage / "runtime" / "LEIA-ME.txt").write_text(
            "O RPCS3 é instalado aqui pelo GOW3_PS3_PC.exe (botão 'Instalar RPCS3...').\n"
            "Baixe o RPCS3 para Windows em https://rpcs3.net/download, extraia numa pasta qualquer e escolha essa pasta.\n",
            encoding="utf-8")

    licenses = stage / "licenses"
    licenses.mkdir()
    shutil.copy2(ROOT / "LICENSE", licenses / "GPL-2.0_GOW3_PS3_PC_e_RPCS3.txt")
    shutil.copy2(ROOT / "THIRD_PARTY.md", licenses / "THIRD_PARTY.md")
    if args.licenses and args.licenses.is_dir():
        shutil.copytree(args.licenses, licenses, dirs_exist_ok=True)
    shutil.copy2(ROOT / "packaging" / "LEIA-ME.txt", stage / "LEIA-ME.txt")
    shutil.copy2(ROOT / "packaging" / "FONTE.txt", stage / "FONTE.txt")
    if args.build_info and args.build_info.is_file():
        shutil.copy2(args.build_info, stage / "BUILD_INFO.txt")

    zip_path = args.out / ZIP_NAME
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(stage.rglob("*")):
            archive.write(path, path.relative_to(args.out).as_posix())
    total = sum(p.stat().st_size for p in stage.rglob("*") if p.is_file())
    print(f"{zip_path}: {zip_path.stat().st_size / 2**20:.1f} MB compactado, {total / 2**20:.1f} MB extraído, "
          f"{len(entries)} arquivos de runtime")


if __name__ == "__main__":
    main()
