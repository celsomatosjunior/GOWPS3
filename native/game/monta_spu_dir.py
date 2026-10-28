"""Monta a SPU_DIR do projeto: os programas SPU do build_spu_workloads + os policy modules do lift_pm.py.

O spu_workloads.c gerado ganha, antes do spu_begin_image(0) final, o registro de cada PM pela
impressão FNV-1a-64 dos bytes que o jogo passa a AddWorkload (pm.json do lift_pm.py).

    python monta_spu_dir.py --programas GOW3_trabalho/spu --pms GOW3_trabalho/spu_pm --out GOW3_trabalho/spu_dir
"""
import argparse
import json
import re
import shutil
from pathlib import Path

PM_IMAGE_ID_BASE = 0x10A00000  # fora da faixa dos ids derivados do sha256 (0x10000000 | sha[:7])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--programas", required=True)
    ap.add_argument("--pms", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    progs, pms, out = Path(args.programas), Path(args.pms), Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for d in sorted(p for p in progs.iterdir() if (p / "spu_recomp.c").is_file()):
        shutil.copytree(d, out / d.name)
    reg = (progs / "spu_workloads.c").read_text(encoding="utf-8")
    used = {int(n) for n in re.findall(r"spu_begin_image\((\d+)\)", reg)}
    decls, calls = [], []
    for i, d in enumerate(sorted(p for p in pms.iterdir() if (p / "pm.json").is_file())):
        meta = json.loads((d / "pm.json").read_text())
        shutil.copytree(d, out / d.name)
        image_id = PM_IMAGE_ID_BASE + i + 1
        if image_id in used:
            raise SystemExit(f"image id {image_id} já usado")
        prefix, entry = meta["name"] + "_", f"spu_func_{meta['entry']:08X}"
        if prefix + entry + "(" not in (d / "spu_recomp.h").read_text():
            raise SystemExit(f"{meta['name']}: o cabeçalho não tem a entrada {entry}")
        decls.append(f"extern void {prefix}{entry}(spu_context*);\nextern void {prefix}spu_recomp_register(void);")
        calls.append(f"    /* {meta['name']}: policy module de 0x{meta['ea']:X}, {meta['size']} bytes */\n"
                     f"    spu_begin_image({image_id}); {prefix}spu_recomp_register();\n"
                     f"    spu_workload_register_img({meta['fp']}ULL, {prefix}{entry}, {image_id}, \"{meta['name']}\");")
    if calls:
        reg = reg.replace("\nvoid spu_register_all(void)", "\n/* policy modules (scripts/lift_pm.py) */\n" +
                          "\n".join(decls) + "\n\nvoid spu_register_all(void)", 1)
        head, sep, tail = reg.rpartition("    spu_begin_image(0);")
        if not sep:
            raise SystemExit("spu_workloads.c sem o spu_begin_image(0) final")
        reg = head + "\n".join(calls) + "\n" + sep + tail
    (out / "spu_workloads.c").write_text(reg, encoding="utf-8")
    print(f"SPU_DIR {out}: {len(list(out.glob('*/spu_recomp.c')))} imagens, {len(calls)} policy module(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
