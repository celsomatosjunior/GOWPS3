# GOW3 PS3 NATIVE (branch `native-recomp`)

Este é o trabalho de recompilação estática do God of War III (PS3) para Windows x64, sobre o [ps3recomp](https://github.com/sp00nznet/ps3recomp) (MIT). O objetivo final é o `GOW3_PS3_NATIVE.exe`, que roda **sem** RPCS3.

A versão funcional baseada em RPCS3 continua intacta na branch `main`. Ela serve de referência de execução e de comparação.

## Onde estamos

| Etapa | Situação |
|---|---|
| 1. Ferramentas compiladas | ps3recomp compila e passa nos testes (Linux verificado; Windows no `native.yml`) |
| 2. Executável do jogo analisado | Ferramenta pronta, **aguardando o EBOOT do jogo** |
| 3. Código PPU recompilado | Corpus de teste: 97/97 casos idênticos ao PowerPC. God of War III: pendente |
| 4 a 10 | Não iniciadas |

Detalhes: [docs/AUDITORIA_PS3RECOMP.md](docs/AUDITORIA_PS3RECOMP.md). O relatório de cada execução do CI fica no artefato `NATIVE_REPORT` e no ramo `ci-logs` (`native/<execução>/`).

## Conteúdo

- `ppu_diff/`: teste diferencial PPU. Compila código C nosso para PowerPC/Cell e executa no QEMU (referência). Depois recompila com o lifter do ps3recomp, compila para x86-64 e compara caso a caso.
- `tools/analyze_gow3.py`: relatório do executável do jogo. Sem decifrar nada, lê PARAM.SFO e os cabeçalhos SELF. Com um `EBOOT.ELF` preparado pelo usuário, lista funções, importações por biblioteca com cobertura HLE, programas SPU e uma amostra recompilada.
- `tools/make_report.py`: monta o relatório do CI.
- `ps3recomp-elfv1.patch`: duas correções no lifter (`lwax` em tabelas de salto e `--toc` para ELF).
- `PS3RECOMP_COMMIT.txt`: commit fixado do ps3recomp.

## Rodar localmente

```sh
git clone https://github.com/sp00nznet/ps3recomp && git -C ps3recomp checkout $(cat native/PS3RECOMP_COMMIT.txt)
git -C ps3recomp apply ../native/ps3recomp-elfv1.patch
pip install -r ps3recomp/requirements.txt

# teste diferencial (Linux: gcc-powerpc64-linux-gnu e qemu-user)
python native/ppu_diff/run.py generate --ps3recomp ps3recomp --out bundle
cmake -S bundle -B bundle/build -G Ninja && cmake --build bundle/build
bundle/build/ppu_diff_lifted bundle/corpus.elf > bundle/out.txt
python native/ppu_diff/run.py compare --bundle bundle --output bundle/out.txt

# análise do jogo (arquivos do usuário; nada é copiado para o repositório)
python native/tools/analyze_gow3.py "D:\Jogos\God of War III" --ps3recomp ps3recomp --out relatorio_gow3
python native/tools/analyze_gow3.py "D:\Jogos\God of War III" --elf EBOOT.ELF --ps3recomp ps3recomp --out relatorio_gow3 --lift-sample 50
```

## Regras

- Nenhum arquivo do jogo, firmware ou chave entra no repositório.
- Este projeto não decifra SELF de varejo.
- O RPCS3 é só referência de comportamento.
