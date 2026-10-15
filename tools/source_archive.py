#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Gera um .tar.gz com todos os arquivos versionados de um repositório git, incluindo submódulos
inicializados. Uso: python tools/source_archive.py <repositório> <saída.tar.gz> <prefixo>"""
import subprocess, sys, tarfile
from pathlib import Path

repo, out, prefix = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
listing = subprocess.run(["git", "-C", str(repo), "ls-files", "--recurse-submodules", "-z"],
                         check=True, capture_output=True).stdout.decode("utf-8", "surrogateescape")
count = 0
out.parent.mkdir(parents=True, exist_ok=True)
with tarfile.open(out, "w:gz", compresslevel=6) as archive:
    for name in filter(None, listing.split("\0")):
        path = repo / name
        if path.is_file():  # submódulos não inicializados aparecem como pasta vazia
            archive.add(path, f"{prefix}/{name}", recursive=False)
            count += 1
print(f"{out}: {count} arquivos, {out.stat().st_size / 2**20:.1f} MB")
