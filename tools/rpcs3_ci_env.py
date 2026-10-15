#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Imprime (KEY=VALUE) as variáveis de ambiente de um job do CI do RPCS3.

Assim as versões de Qt, LLVM e Vulkan SDK usadas na compilação são sempre as que o próprio
RPCS3 usa no commit fixado em RPCS3_COMMIT.txt, sem cópia manual.
Uso: python tools/rpcs3_ci_env.py rpcs3/.github/workflows/rpcs3.yml Windows_Build
"""
import sys
import yaml

workflow = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
env = workflow["jobs"][sys.argv[2]].get("env", {})
required = ("QT_VER_MAIN", "QT_VER", "QT_VER_MSVC", "QT_DATE", "LLVM_VER", "VULKAN_VER", "VULKAN_SDK_SHA", "CCACHE_SHA")
missing = [key for key in required if key not in env]
if missing:
    sys.exit(f"o CI do RPCS3 não define mais: {', '.join(missing)}")
for key, value in env.items():
    if "${{" in str(value):
        continue  # expressões do GitHub (dependem do repositório do RPCS3)
    print(f"{key}={value}")
