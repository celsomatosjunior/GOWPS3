"""Sonda o God of War III no RPCS3 do usuário pelo servidor GDB: põe breakpoints, e a cada parada
mostra pc, lr, r3..r5 e bytes de memória. Só lê o jogo; ao fim continua e desconecta.
Uso: rpcs3_gdb_sonda.py --bp 0x1E51AC --bp 0x1E5440 --mem 0x588E50:0x20 --paradas 6 --espera 240"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "GOWPS3" / "native" / "analyzer"))
from gow3_analyzer.gdb_client import GdbClient  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--bp", action="append", default=[])
ap.add_argument("--mem", action="append", default=[])
ap.add_argument("--paradas", type=int, default=6)
ap.add_argument("--espera", type=float, default=240)
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
g.interrupt()
for b in a.bp:
    print("bp", b, g.set_breakpoint(int(b, 16)), flush=True)
for k in range(a.paradas):
    g.resume()
    r = g.wait_stop(a.espera)
    if not r:
        print("nenhuma parada"); break
    tid = g.current_thread()
    if tid: g.select_thread(tid)
    regs = g.read_all_registers() or {}
    pc, lr = regs.get("pc"), regs.get("lr")
    gp = regs.get("gpr", [0] * 32)
    print(f"parada {k + 1} (thread {tid}): pc={pc and hex(pc)} lr={lr and hex(lr)} r3={gp[3]:#x} r4={gp[4]:#x} r5={gp[5]:#x}", flush=True)
    for m in a.mem:
        ad, n = (int(x, 16) for x in m.split(":"))
        d = g.read_memory(ad, n)
        print(f"   [{ad:#x}] {d.hex(' ') if d else None}", flush=True)
    sp = gp[1]
    st = g.read_memory(sp & 0xFFFFFFFF, 0x100) if sp else None
    if st:
        import struct
        ws = [struct.unpack_from('>I', st, i)[0] for i in range(0, len(st), 4)]
        print("   pilha (possíveis retornos):", " ".join(hex(w) for w in ws if 0x10000 <= w < 0x500000)[:400], flush=True)
for b in a.bp:
    g.remove_breakpoint(int(b, 16))
g.resume(); g.close()
