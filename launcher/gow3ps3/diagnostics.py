# SPDX-License-Identifier: GPL-2.0-only
"""Lê o RPCS3.log e traduz os erros conhecidos em mensagens compreensíveis.

Prefixos de nível conferidos em rpcs3/util/logs.cpp ("·F " fatal, "·E " erro, "·W " aviso).
Os textos procurados abaixo foram copiados do código do RPCS3.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# (trecho exato do log, explicação para o usuário)
KNOWN_PATTERNS = (
    ("Firmware is missing",
     "O firmware do PS3 não está instalado neste perfil. Use 'Instalar firmware' com o arquivo "
     "PS3UPDAT.PUP baixado do site da PlayStation."),
    ("Firmware is too old",
     "O firmware instalado é mais antigo do que o jogo pede. Instale a versão mais recente."),
    ("No compatible GPU devices found",
     "Nenhuma placa de vídeo compatível com Vulkan foi encontrada. Atualize o driver."),
    ("VK_ERROR_OUT_OF_DEVICE_MEMORY",
     "Acabou a memória de vídeo (VRAM). Reduza a resolução interna."),
    ("VK_ERROR_DEVICE_LOST",
     "O driver de vídeo travou (device lost). Atualize o driver e tente sem sobreclock."),
    ("Failed to apply config: ",
     "O RPCS3 não aceitou o arquivo de configuração do launcher. Restaure as configurações padrão."),
    ("Invalid file or folder",
     "O RPCS3 não encontrou o executável do jogo na pasta escolhida."),
    ("Failed to decrypt content",
     "O RPCS3 não conseguiu ler o executável do jogo. A cópia pode estar incompleta ou ser de outra fonte."),
    ("Missing decryption key for the disc",
     "Esta cópia é uma imagem de disco que precisa da chave do próprio disco. Use a pasta do jogo "
     "copiada pelo seu PS3."),
)


@dataclass
class LogReport:
    found: bool
    fatal: list[str]
    errors: int
    warnings: int
    explanations: list[str]


def analyse_text(text: str) -> LogReport:
    fatal, errors, warnings = [], 0, 0
    for line in text.splitlines():
        if line.startswith("·F "):
            fatal.append(line[3:].strip())
        elif line.startswith("·E "):
            errors += 1
        elif line.startswith("·W "):
            warnings += 1
    explanations = [message for needle, message in KNOWN_PATTERNS if needle in text]
    return LogReport(True, fatal[-10:], errors, warnings, explanations)


def analyse(log_file) -> LogReport:
    try:
        text = Path(log_file).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return LogReport(False, [], 0, 0, [])
    return analyse_text(text)


def tail(log_file, lines: int = 200) -> str:
    try:
        content = Path(log_file).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(content[-lines:])
