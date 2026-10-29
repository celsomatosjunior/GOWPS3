"""Patches de terceiros do RPCS3 (o patch.yml da comunidade, que o RPCS3 do usuário baixa) aplicados ao EBOOT.ELF
do GOW3 antes da tradução. Só lê o patch.yml do usuário: nenhum patch é copiado para o repositório.

  rpcs3_patches.py --patch-yml <rpcs3>/patches/patch.yml --listar
  rpcs3_patches.py --patch-yml ... --elf EBOOT.ELF --saida EBOOT.patch.ELF --aplicar "Skip any videos with X button" ...

Escolhe os patches PPU cujo campo Games tem o título (BCES00510) com a versão do EBOOT (01.00). Aplica as escritas
em endereços absolutos (be16, be32, be64, byte, bef32, bef64, utf8) e as listas por `load`; patches de SPU e de
outros tipos são recusados com aviso, porque aqui não há memória viva para eles.
"""
import argparse, struct, sys
from pathlib import Path

import yaml
from yaml.events import AliasEvent, ScalarEvent, SequenceStartEvent


class _Loader(yaml.SafeLoader):
    """O patch.yml redefine âncoras; o RPCS3 aceita e vale a última."""

    def compose_node(self, parent, index):
        if self.check_event(AliasEvent):
            return self.anchors[self.get_event().anchor]
        anchor = self.peek_event().anchor
        self.descend_resolver(parent, index)
        if self.check_event(ScalarEvent):
            node = self.compose_scalar_node(anchor)
        elif self.check_event(SequenceStartEvent):
            node = self.compose_sequence_node(anchor)
        else:
            node = self.compose_mapping_node(anchor)
        self.ascend_resolver()
        return node


def _versao_ok(lista, versao):
    if lista is None:
        return False
    for v in lista if isinstance(lista, list) else [lista]:
        if str(v) == "All" or str(v) == versao or (isinstance(v, float) and abs(v - float(versao)) < 1e-9):
            return True
    return False


def patches_do_jogo(patch_yml: Path, titulo: str, versao: str) -> dict:
    d = yaml.load(patch_yml.read_text(encoding="utf-8"), Loader=_Loader)
    achados = {}
    for chave, bloco in d.items():
        if not str(chave).startswith("PPU-") or not isinstance(bloco, dict):
            continue
        for nome, p in bloco.items():
            if not isinstance(p, dict):
                continue
            for _, ids in (p.get("Games") or {}).items():
                if isinstance(ids, dict) and titulo in ids and _versao_ok(ids[titulo], versao):
                    achados[nome] = dict(hash=chave, autor=p.get("Author"), notas=p.get("Notes"),
                                         ops=p.get("Patch") or [])
    return achados


def _expande(ops):
    for op in ops:
        if op and op[0] == "load":
            yield from _expande(op[1] if isinstance(op[1], list) else [])
        else:
            yield op


def aplica(elf: bytes, ops) -> tuple[bytearray, list[str]]:
    data = bytearray(elf)
    phoff, = struct.unpack_from(">Q", data, 0x20)
    es, n = struct.unpack_from(">HH", data, 0x36)
    segs = []
    for i in range(n):
        p_type, _, off, vaddr, _, filesz = struct.unpack_from(">IIQQQQ", data, phoff + i * es)
        if p_type == 1:
            segs.append((vaddr, filesz, off))
    fmt = {"be16": ">H", "be32": ">I", "be64": ">Q", "byte": ">B", "bef32": ">f", "bef64": ">d"}
    feitos = []
    for op in _expande(ops):
        tipo, ea, valor = op[0], int(op[1]), op[2]
        if tipo == "utf8":
            raw = str(valor).encode("utf-8")
        elif tipo in fmt:
            raw = struct.pack(fmt[tipo], float(valor) if tipo.startswith("bef") else int(valor))
        else:
            raise ValueError(f"tipo de patch não suportado: {tipo}")
        for vaddr, filesz, off in segs:
            if vaddr <= ea and ea + len(raw) <= vaddr + filesz:
                o = off + ea - vaddr
                antes = bytes(data[o:o + len(raw)])
                data[o:o + len(raw)] = raw
                feitos.append(f"{tipo} 0x{ea:08X}: {antes.hex()} -> {raw.hex()}")
                break
        else:
            raise ValueError(f"0x{ea:08X} fora dos dados dos segmentos do ELF ({tipo})")
    return data, feitos


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--patch-yml", required=True, type=Path)
    ap.add_argument("--titulo", default="BCES00510")
    ap.add_argument("--versao", default="01.00")
    ap.add_argument("--listar", action="store_true")
    ap.add_argument("--elf", type=Path)
    ap.add_argument("--saida", type=Path)
    ap.add_argument("--aplicar", action="append", default=[], help="nome do patch, como no RPCS3 (repetível)")
    a = ap.parse_args()
    ps = patches_do_jogo(a.patch_yml, a.titulo, a.versao)
    if a.listar or not a.aplicar:
        for nome, p in ps.items():
            tipos = sorted({op[0] for op in _expande(p["ops"])})
            print(f"{nome}  [{p['autor']}]  {len(p['ops'])} op(s) {tipos}")
        return 0
    data = a.elf.read_bytes()
    for nome in a.aplicar:
        if nome not in ps:
            sys.exit(f"patch não encontrado para {a.titulo} {a.versao}: {nome!r}")
        data, feitos = aplica(data, ps[nome]["ops"])
        print(f"{nome} ({ps[nome]['autor']}):")
        for f in feitos:
            print("   ", f)
    a.saida.write_bytes(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
