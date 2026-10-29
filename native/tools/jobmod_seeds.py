"""Divide os pcs que o interpretador SPU recebeu (SPU_INTERP_PCLOG, linhas "imagem 0xPC res=... hdr=...") em
sementes por módulo de job, para o --module-funcs do ps3recomp/tools/lift_jobmods.py.

Os 16 bytes em LS 0x4000 (hdr=) identificam o módulo que estava no buffer de código do job: procurados no
EBOOT.ELF, dão o EA do módulo e, pelo manifesto de uma tradução com --base-zero, o nome. Grava
<trabalho>/seeds/seeds_<prefixo>.txt e imprime os argumentos --module-funcs.

  jobmod_seeds.py --trabalho <pasta> [--manifesto <spu_jobs>/jobmods_manifest.json] pcs1.txt [pcs2.txt ...]
"""
import argparse
import json
import struct
import sys
from pathlib import Path


def segmentos(elf):
    phoff, = struct.unpack_from(">Q", elf, 0x20)
    phnum, = struct.unpack_from(">H", elf, 0x38)
    out = []
    for i in range(phnum):
        t, _fl, off, va, _pa, fsz = struct.unpack_from(">IIQQQQ", elf, phoff + i * 56)
        if t == 1:
            out.append((off, va, fsz))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trabalho", required=True, help="pasta de trabalho (tem EBOOT.ELF e spu_jobs/)")
    ap.add_argument("--manifesto", help="jobmods_manifest.json com todos os módulos (padrão: <trabalho>/spu_jobs)")
    ap.add_argument("pcs", nargs="+", help="arquivos do SPU_INTERP_PCLOG")
    args = ap.parse_args()
    work = Path(args.trabalho)
    elf = (work / "EBOOT.ELF").read_bytes()
    segs = segmentos(elf)

    def va_de(o):
        for off, va, fsz in segs:
            if off <= o < off + fsz:
                return va + o - off

    manifesto = Path(args.manifesto or work / "spu_jobs" / "jobmods_manifest.json")
    mods = {x["ea"]: x["name"] for x in json.loads(manifesto.read_text())}
    sementes, cache = {}, {}
    for arq in args.pcs:
        for linha in open(arq):
            f = linha.split()
            if len(f) < 4 or not f[3].startswith("hdr="):
                continue
            pc = int(f[1], 16)
            if pc < 0x4000:
                continue
            h = f[3][4:]
            if h not in cache:
                at = elf.find(bytes.fromhex(h))
                cache[h] = mods.get(va_de(at)) if at != -1 else None
            if cache[h]:
                sementes.setdefault("_".join(cache[h].split("_")[:2]), set()).add(pc)
    pasta = work / "seeds"
    pasta.mkdir(exist_ok=True)
    saida = []
    for prefixo, pcs in sorted(sementes.items()):
        arq = pasta / f"seeds_{prefixo}.txt"
        arq.write_text("".join(f"0x{p:05X}\n" for p in sorted(pcs)))
        print(f"{prefixo}: {len(pcs)}", file=sys.stderr)
        saida.append(f'"--module-funcs={prefixo}=@{arq.as_posix()}"')
    print(" ".join(saida))


if __name__ == "__main__":
    main()
