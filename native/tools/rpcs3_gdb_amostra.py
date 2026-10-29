"""Amostra memória do God of War III no RPCS3 do usuário pelo servidor GDB, sem breakpoints: a cada
--intervalo segundos interrompe, lê cada faixa --mem, imprime só as que mudaram e continua. Só lê o jogo.
Uso: rpcs3_gdb_amostra.py --mem 0x649EC0:0xC --mem 0x64AA78:0xC --segundos 120"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analyzer"))
from gow3_analyzer.gdb_client import GdbClient  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--mem", action="append", default=[])
ap.add_argument("--segundos", type=float, default=120)
ap.add_argument("--intervalo", type=float, default=0.5)
ap.add_argument("--espera", type=float, default=240, help="tempo máximo até o servidor GDB responder")
a = ap.parse_args()
t0 = time.time(); g = None
while time.time() - t0 < a.espera:
    try:
        g = GdbClient(timeout=5.0); break
    except OSError:
        time.sleep(0.2)
if not g:
    sys.exit("servidor GDB não respondeu")
print(f"conectado em {time.time() - t0:.1f}s", flush=True)
faixas = [tuple(int(x, 16) for x in m.split(":")) for m in a.mem]
ultimo = {}
t1 = time.time()
try:
    while time.time() - t1 < a.segundos:
        g.interrupt()
        g.wait_stop(5)
        linha = []
        for ad, n in faixas:
            d = g.read_memory(ad, n)
            h = d.hex(" ") if d else None
            if ultimo.get(ad) != h:
                linha.append(f"[{ad:#x}] {h}")
                ultimo[ad] = h
        if linha:
            print(f"t={time.time() - t1:6.1f}s " + "  ".join(linha), flush=True)
        g.resume()
        time.sleep(a.intervalo)
finally:
    try:
        g.resume()
    except Exception:
        pass
    g.close()
