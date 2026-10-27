# SPDX-License-Identifier: GPL-2.0-only
"""Gera o EBOOT.ELF a partir do EBOOT.BIN usando o RPCS3 instalado no computador do usuário.

Este programa não decifra nada e não contém chaves: quem converte é o próprio RPCS3 do usuário
(`rpcs3 --no-gui --decrypt <arquivo>`, a mesma função de "Utilities > Decrypt PS3 Binaries"), sobre
a cópia do jogo do usuário. O EBOOT.BIN original não é alterado: o RPCS3 trabalha numa cópia dentro
da pasta de trabalho do analisador.
"""

from __future__ import annotations

import json
import os
import shutil
import string
import subprocess
import sys
import time
from pathlib import Path

from . import formats

# Versões conferidas (SHA-256). O EBOOT.ELF é o que o RPCS3 gera a partir do EBOOT.BIN.
KNOWN = {
    "49e894c2c9ca9d87824292a93eded16b733bdaf0eef4d28918483007f9bc35b0": {
        "title": "God of War III", "title_id": "BCES00510", "version": "01.00",
        "elf_sha256": "931ccd9bb11014efd2ef6b3dc51f421a029f9256da6b9de6b8cf2fdbb948b2ae",
    },
}

TIMEOUT = 300


class DecryptError(RuntimeError):
    pass


def settings_path() -> Path:
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()
    return base / "configuracoes.json"


def load_settings() -> dict:
    try:
        return json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(data: dict) -> None:
    try:
        cur = load_settings()
        cur.update(data)
        settings_path().write_text(json.dumps(cur, indent=1, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _exe_name() -> str:
    return "rpcs3.exe" if os.name == "nt" else "rpcs3"


def _valid(p: Path | None) -> bool:
    return bool(p) and p.is_file() and p.name.lower() in ("rpcs3.exe", "rpcs3", "rpcs3.appimage")


def candidates() -> list[Path]:
    """Lugares comuns de instalação do RPCS3 e o RPCS3 do pacote GOW3_PS3_PC."""
    out: list[Path] = []
    exe = _exe_name()
    env = os.environ.get("GOW3_RPCS3")
    if env:
        out.append(Path(env))
    here = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()
    # pacote GOW3_PS3_PC (o primeiro programa do projeto) ao lado do analisador
    for root in (here, here.parent, here.parent.parent):
        try:
            for d in root.iterdir():
                if d.is_dir() and d.name.upper().startswith("GOW3_PS3_PC"):
                    out += [d / "runtime" / "rpcs3" / exe, d / "GOW3_PS3_PC" / "runtime" / "rpcs3" / exe]
        except OSError:
            pass
    home = Path.home()
    for base in (home, home / "Desktop", home / "Downloads", home / "Documents",
                 Path(os.environ.get("LOCALAPPDATA", home)), Path(os.environ.get("ProgramFiles", "C:/Program Files"))):
        out += [base / "RPCS3" / exe, base / "rpcs3" / exe]
    if os.name == "nt":  # pastas na raiz de cada disco com "rpcs3" no nome (até dois níveis)
        for letter in string.ascii_uppercase:
            root = Path(f"{letter}:/")
            try:
                if not root.exists():
                    continue
                for d in root.iterdir():
                    if not d.is_dir():
                        continue
                    if "rpcs3" in d.name.lower():
                        out.append(d / exe)
                    elif d.name.lower() in ("games", "jogos", "emuladores", "emulators", "emulador"):
                        for sub in d.iterdir():
                            if sub.is_dir() and "rpcs3" in sub.name.lower():
                                out.append(sub / exe)
            except OSError:
                continue
    found = shutil.which("rpcs3")
    if found:
        out.append(Path(found))
    return out


def find_rpcs3(hint: str | os.PathLike | None = None) -> Path | None:
    for p in ([Path(hint)] if hint else []) + ([Path(load_settings()["rpcs3"])] if load_settings().get("rpcs3") else []) + candidates():
        if p.is_dir():
            p = p / _exe_name()
        if _valid(p):
            return p.resolve()
    return None


def clean_child_env() -> dict:
    """Ambiente para abrir um programa externo (o RPCS3) sem herdar nada do pacote do analisador.

    O executável empacotado (PyInstaller) põe a pasta _internal no PATH e no caminho de DLLs; um filho
    que herde isso carrega o VCRUNTIME140.dll do analisador em vez do instalado no Windows, e o RPCS3
    para com "vcruntime140.dll was incorrectly installed"."""
    env = dict(os.environ)
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        b = os.path.normcase(os.path.abspath(bundle))
        parts = [p for p in env.get("PATH", "").split(os.pathsep)
                 if p and not os.path.normcase(os.path.abspath(p)).startswith(b)]
        env["PATH"] = os.pathsep.join(parts)
    for key in list(env):
        if key.startswith(("_MEI", "_PYI", "PYI_")) or key in ("PYTHONHOME", "PYTHONPATH", "TCL_LIBRARY", "TK_LIBRARY",
                                                            "SSL_CERT_FILE", "SSL_CERT_DIR"):
            env.pop(key, None)
    return env


class _NoBundleDllDirectory:
    """No Windows, desfaz por um momento o SetDllDirectory(_internal) do carregador do PyInstaller, que
    os processos filhos herdam (documentado pelo PyInstaller), e o restaura depois."""

    def __enter__(self):
        self.k32 = None
        if os.name == "nt" and getattr(sys, "frozen", False):
            import ctypes
            self.k32 = ctypes.windll.kernel32
            self.k32.SetDllDirectoryW(None)
        return self

    def __exit__(self, *exc):
        if self.k32 is not None:
            self.k32.SetDllDirectoryW(getattr(sys, "_MEIPASS", None))
        return False


FAIL_MARKS = ("Failed to load SELF", "Failed to decrypt", "Failed to create", "Failed to load")


def _run_rpcs3(cmd, rpcs3: Path, work: Path, out_elf: Path, log_path: Path, t_start: float):
    """Roda o RPCS3 e o encerra quando a conversão termina, falha ou ele fica pedindo a KLIC.

    Com --decrypt o RPCS3 se liga ao console (AttachConsole/AllocConsole) e reabre o teclado (CONIN$):
    quando a conversão falha ele pede a KLIC e espera digitação, ignorando a entrada que lhe damos.
    Por isso o processo é acompanhado pelo arquivo gerado e pelo RPCS3.log, não pela saída."""
    out_file = work / "rpcs3_saida.txt"
    with open(out_file, "wb") as fo, _NoBundleDllDirectory():
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=fo, stderr=subprocess.STDOUT,
                                cwd=str(rpcs3.parent), env=clean_child_env(),
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    ended = "terminou sozinho"
    fail_seen = None
    elf_seen = None
    while proc.poll() is None:
        time.sleep(0.5)
        now = time.time()
        if out_elf.is_file():
            elf_seen = elf_seen or now
            if now - elf_seen > 30:  # o ELF já foi gravado; o RPCS3 só não fechou
                ended = "encerrado depois de gravar o ELF"
                break
        if fail_seen is None:
            try:
                if log_path.stat().st_mtime >= t_start - 2:
                    txt = log_path.read_text(encoding="utf-8", errors="replace")
                    if any(m in txt for m in FAIL_MARKS):
                        fail_seen = now
            except OSError:
                pass
        elif now - fail_seen > 5:  # falhou e está esperando a KLIC no console
            ended = "encerrado: a conversão falhou e o RPCS3 ficou esperando uma KLIC"
            break
        # parado: nem ELF nem log novo há 25 s (a conversão de um EBOOT leva poucos segundos)
        try:
            last = max(log_path.stat().st_mtime, t_start)
        except OSError:
            last = t_start
        if elf_seen is None and now - t_start > 30 and now - last > 25:
            ended = "encerrado: o RPCS3 ficou parado sem gerar o ELF (provavelmente esperando uma KLIC ou uma janela)"
            break
        if now - t_start > TIMEOUT:
            ended = f"encerrado por tempo ({TIMEOUT} s)"
            break
    if proc.poll() is None:
        proc.kill()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            pass
    try:
        text = out_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    log = f"$ {' '.join(cmd)}\n({ended}; código {proc.returncode}; {time.time() - t_start:.0f} s)\n{text}"
    return log, ended


def decrypt_with_rpcs3(self_path: Path, rpcs3: Path, work: Path, progress=lambda m: None) -> Path:
    """Copia o SELF para a pasta de trabalho, pede ao RPCS3 para convertê-lo e devolve o ELF."""
    # caminhos absolutos: o RPCS3 roda com a pasta dele como pasta de trabalho
    self_path, rpcs3, work = Path(self_path).resolve(), Path(rpcs3).resolve(), Path(work).resolve()
    dst_dir = work / "rpcs3_conversao"
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    dst_dir.mkdir(parents=True)
    copy = dst_dir / self_path.name
    shutil.copy2(self_path, copy)
    out_elf = copy.with_suffix(".elf")
    progress(f"Gerando o EBOOT.ELF com o seu RPCS3 ({rpcs3})...")
    cmd = [str(rpcs3), "--no-gui", "--decrypt", str(copy)]
    log_path = rpcs3.parent / "log" / "RPCS3.log"
    t_start = time.time()
    try:
        log, ended = _run_rpcs3(cmd, rpcs3, work, out_elf, log_path, t_start)
    except OSError as error:
        raise DecryptError(f"não foi possível executar o RPCS3 ({rpcs3}): {error}") from error
    rlog = rpcs3_log(rpcs3, since=t_start)
    log += "\n--- trechos do log do próprio RPCS3 (" + str(rpcs3.parent / "log" / "RPCS3.log") + ") ---\n"
    log += "\n".join(rlog["lines"]) if rlog["lines"] else "(log do RPCS3 não encontrado ou sem linhas relevantes)"
    (work / "rpcs3_conversao.log").write_text(log, encoding="utf-8")
    if not out_elf.is_file() or out_elf.stat().st_size < 64:
        hint = ""
        if not rlog["fresh"]:
            hint += (" O RPCS3 não chegou a escrever o log dele nesta tentativa: ele fechou logo ao abrir ou mostrou "
                     "uma janela de erro. Abra o RPCS3 normalmente uma vez para ver se ele inicia.")
        if rlog["version"]:
            hint += f" Versão do RPCS3: {rlog['version']}."
        if rlog["lines"] and not rlog["started"]:
            hint += (" O log do RPCS3 não mostra a conversão começando; se o seu RPCS3 for antigo, atualize-o "
                     "(a opção de linha de comando --decrypt só existe nas versões recentes).")
        if rlog["reason"]:
            hint += f" O RPCS3 informou: {rlog['reason']}"
        if "Enter KLIC" in log.split("\n", 2)[-1]:  # o próprio RPCS3 pediu a KLIC na saída
            hint += " O executável pede uma licença digital (KLIC): é de um jogo da PSN, não do disco."
        raise DecryptError("o RPCS3 não gerou o EBOOT.ELF." + hint + " Veja rpcs3_conversao.log. Confira se o RPCS3 "
                           "abre normalmente e se o firmware do PS3 está instalado nele (File > Install Firmware).")
    head = out_elf.read_bytes()[:64]
    hdr = formats.elf_header(head)
    if not hdr or "error" in hdr or hdr.get("machine_id") != 21:
        raise DecryptError(f"o arquivo gerado pelo RPCS3 não é um ELF PPU válido ({out_elf.stat().st_size} bytes, "
                           f"início {head[:4].hex()}); veja rpcs3_conversao.log")
    copy.unlink()  # a cópia do SELF não é mais necessária
    return out_elf


LOG_KEYS = ("DEC:", "SELF:", "Decrypt", "decrypt", "KLIC", "unself", "Failed", "failed")


def rpcs3_log(rpcs3: Path, since: float | None = None) -> dict:
    """Linhas relevantes do RPCS3.log (o RPCS3 reescreve o log a cada execução, então é a da conversão).
    A saída de texto do `--decrypt` vai para o console do Windows e não chega ao analisador."""
    out = {"lines": [], "version": None, "started": False, "reason": None, "fresh": False}
    p = rpcs3.parent / "log" / "RPCS3.log"
    try:
        if since is not None and p.stat().st_mtime < since - 2:
            return out  # log antigo: o RPCS3 não escreveu nada nesta tentativa
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    out["fresh"] = True
    for line in text.splitlines():
        if out["version"] is None and "RPCS3 v" in line:
            i = line.index("RPCS3 v")
            out["version"] = line[i:i + 60].split(" | ")[0].strip()
        if any(k in line for k in LOG_KEYS) or line.startswith(("·E", "·F", "E ", "F ")):
            out["lines"].append(line[:300])
        if "Decrypting binaries" in line:
            out["started"] = True
        if out["reason"] is None and ("Failed to" in line or "failed to" in line):
            for tag in ("SELF:", "DEC:"):
                if tag in line:
                    out["reason"] = line[line.index(tag):].strip()[:200]
                    break
    out["lines"] = out["lines"][-80:]
    return out


def known_version(self_sha: str, elf_sha: str | None) -> dict:
    k = KNOWN.get(self_sha)
    if not k:
        return {"known": False}
    return {"known": True, **{key: v for key, v in k.items() if key != "elf_sha256"},
            "elf_matches": elf_sha == k["elf_sha256"] if elf_sha else None}


def known_elf(elf_sha: str) -> dict:
    """Confere um EBOOT.ELF escolhido diretamente com os ELFs já verificados."""
    for k in KNOWN.values():
        if k["elf_sha256"] == elf_sha:
            return {"known": True, "elf_matches": True, **{key: v for key, v in k.items() if key != "elf_sha256"}}
    return {"known": False}
