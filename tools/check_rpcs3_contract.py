#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Confere, no código-fonte do RPCS3, tudo o que o GOW3_PS3_PC.exe usa dele.

Uso: python tools/check_rpcs3_contract.py <clone do rpcs3> <saída de "core_tests --dump-yaml">
Falha (código 1) se o RPCS3 mudou algo de que o aplicativo depende.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    rpcs3, yaml_file = Path(sys.argv[1]), Path(sys.argv[2])
    config_h = (rpcs3 / "rpcs3/Emu/system_config.h").read_text(encoding="utf-8")
    types_cpp = (rpcs3 / "rpcs3/Emu/system_config_types.cpp").read_text(encoding="utf-8")
    cli = (rpcs3 / "rpcs3/rpcs3.cpp").read_text(encoding="utf-8")
    file_cpp = (rpcs3 / "Utilities/File.cpp").read_text(encoding="utf-8")
    sources = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in (rpcs3 / "rpcs3").rglob("*.cpp"))
    problems = []

    # 1. Cada chave e valor de texto do YAML gerado existe no RPCS3.
    for line in yaml_file.read_text(encoding="utf-8").splitlines():
        match = re.match(r'^\s*([^:#][^:]*):\s*(.*)$', line)
        if not match:
            continue
        key, value = match.group(1).strip(), match.group(2).strip()
        if f'"{key}"' not in config_h:
            problems.append(f"chave de configuração inexistente: {key}")
        if value.startswith('"') and value != '""' and key != "Adapter":
            if f"return {value};" not in types_cpp:
                problems.append(f"valor inexistente para {key}: {value}")

    # 2. Valores de todas as opções do aplicativo (não só os padrões).
    settings_cpp = (ROOT / "app/core/settings.cpp").read_text(encoding="utf-8")
    for key, body in re.findall(r'static const OptionTable table\{"([^"]+)", \{(.*?)\}\};', settings_cpp, re.S):
        for value in re.findall(r'\{"[^"]*", "[^"]*", "([^"]*)"\}', body):
            if not value.isdigit() and f'return "{value}";' not in types_cpp:
                problems.append(f"valor inexistente para {key}: {value}")
    scale = re.search(r"uint<(\d+), (\d+)> resolution_scale_percent", config_h)
    for percent in (100, 125, 150, 200, 300):
        if not scale or not int(scale.group(1)) <= percent <= int(scale.group(2)):
            problems.append(f"escala {percent}% fora da faixa do RPCS3")
    if "uint<0, 16> anisotropic_level_override" not in config_h:
        problems.append("faixa do filtro anisotrópico mudou")

    # 3. Opções de linha de comando.
    for option in ("no-gui", "fullscreen", "config", "installfw", "headless", "version"):
        if option == "version":
            if "addVersionOption" not in cli:
                problems.append("--version não existe mais")
        elif f'= "{option}";' not in cli:
            problems.append(f"opção --{option} não existe mais")

    # 4. Pasta de dados por variável de ambiente e pasta portable.
    if 'L"RPCS3_CONFIG_DIR"' not in file_cpp:
        problems.append("RPCS3_CONFIG_DIR não é mais lida")
    if '"/portable/"' not in file_cpp:
        problems.append("regra da pasta portable mudou")

    # 5. Textos de log que o diagnóstico procura.
    diagnostics = (ROOT / "app/core/diagnostics.cpp").read_text(encoding="utf-8")
    for needle in re.findall(r'^\t\{"([^"]+)",', diagnostics, re.M):
        if needle.strip() not in sources:
            problems.append(f"mensagem de log não existe mais: {needle}")

    if problems:
        print("Contrato com o RPCS3 QUEBRADO:\n  " + "\n  ".join(problems))
        return 1
    print("Contrato com o RPCS3 conferido: chaves, valores, opções de linha de comando, pasta de dados e mensagens de log.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
