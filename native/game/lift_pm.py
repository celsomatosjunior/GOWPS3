"""Recompila um policy module SPURS (binário SPU cru, carregado em LS 0xA00) tirado do EBOOT.ELF.

O runtime acha o PM pela impressão FNV-1a-64 dos `size` bytes no endereço que o jogo passa a
AddWorkload, então a impressão é calculada sobre esses bytes exatos e conferida com a esperada.

    python lift_pm.py EBOOT.ELF --ps3recomp ps3recomp --ea 0x49FF80 --size 12032 --fp 0x7AE3FE49074DF128 --name pm_wwsjob --out DIR
"""
import argparse
import json
import struct
import subprocess
import sys
from pathlib import Path

PM_BASE = 0xA00


def read_ea(elf: bytes, ea: int, size: int) -> bytes:
    phoff, = struct.unpack_from(">Q", elf, 0x20)
    phentsize, phnum = struct.unpack_from(">HH", elf, 0x36)
    for i in range(phnum):
        o = phoff + i * phentsize
        p_type, _flags, off, vaddr, _paddr, filesz = struct.unpack_from(">IIQQQQ", elf, o)
        if p_type == 1 and vaddr <= ea and ea + size <= vaddr + filesz:
            return elf[off + ea - vaddr: off + ea - vaddr + size]
    raise SystemExit(f"0x{ea:X}+{size} não está em nenhum PT_LOAD com dados no arquivo")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("elf")
    ap.add_argument("--ps3recomp", required=True, help="checkout do ps3recomp")
    ap.add_argument("--ea", type=lambda s: int(s, 0), required=True)
    ap.add_argument("--size", type=lambda s: int(s, 0), required=True)
    ap.add_argument("--fp", type=lambda s: int(s, 0), help="impressão esperada (a do log do runtime)")
    ap.add_argument("--name", required=True)
    ap.add_argument("--out", required=True, help="SPU_DIR; o PM vai para <out>/<name>")
    ap.add_argument("--code-end", help="fim do código (resto é dado)")
    ap.add_argument("--extra-funcs")
    ap.add_argument("--force-indirect")
    args = ap.parse_args()
    PS3RECOMP = Path(args.ps3recomp).resolve()
    sys.path.insert(0, str(PS3RECOMP / "tools"))
    from spu_elf import fnv1a64
    from wrap_spu_elf import wrap

    blob = read_ea(Path(args.elf).read_bytes(), args.ea, args.size)
    fp = fnv1a64(blob)
    print(f"{args.name}: {len(blob)} bytes de 0x{args.ea:X}, fp=0x{fp:016X}")
    if args.fp is not None and fp != args.fp:
        raise SystemExit(f"impressão diferente da esperada 0x{args.fp:016X}: o PM não é esse trecho do EBOOT")
    out = Path(args.out) / args.name
    out.mkdir(parents=True, exist_ok=True)
    (out / "pm.bin").write_bytes(blob)
    (out / "image.elf").write_bytes(wrap(blob, base=PM_BASE, entry=PM_BASE))
    cmd = [sys.executable, str(PS3RECOMP / "tools" / "spu_lifter.py"), "--auto-functions", str(out / "image.elf"),
           "--symbol-prefix", args.name + "_", "--report", str(out / "lift.json"), "--output", str(out),
           "--return-entries"]
    for opt in ("code_end", "extra_funcs", "force_indirect"):
        if getattr(args, opt):
            cmd += ["--" + opt.replace("_", "-"), getattr(args, opt)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    (out / "lift.log").write_text(r.stdout + r.stderr, encoding="utf-8")
    print(r.stdout[-1500:], r.stderr[-1500:])
    if r.returncode:
        return r.returncode
    from build_spu_workloads import debase_includes
    for f in ("spu_recomp.c", "spu_recomp.h"):
        debase_includes(str(out / f))
    rep = json.loads((out / "lift.json").read_text())
    (out / "pm.json").write_text(json.dumps(dict(name=args.name, ea=args.ea, size=args.size, fp=f"0x{fp:016X}",
                                                 entry=PM_BASE, unsupported=rep.get("unsupported"),
                                                 functions=len(rep.get("functions", []))), indent=1))
    print("unsupported:", rep.get("unsupported"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
