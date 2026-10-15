# Auditoria: ps3recomp e ports de referência (GOW3 PS3 NATIVE)

**Data:** 15/10/2026. Tudo o que está marcado como **verificado** foi executado nesta máquina ou no GitHub Actions. O que está marcado como **declarado** vem da documentação dos projetos e não foi verificado.

## Projetos analisados

| Projeto | Commit | Licença | Uso aqui |
|---|---|---|---|
| [sp00nznet/ps3recomp](https://github.com/sp00nznet/ps3recomp) | `a2c2010` | MIT | Base da recompilação (ferramentas + runtime) |
| [soyjxck/dod3-recomp](https://github.com/soyjxck/dod3-recomp) | `f7d7150` | MIT | Referência de port completo (Drakengard 3) |
| [sp00nznet/scottpilgrim](https://github.com/sp00nznet/scottpilgrim) | `f8d9f22` | MIT | Referência de port em andamento |
| [deadinside28/bloodborne_pc](https://github.com/deadinside28/bloodborne_pc) | `3c57da4` | ver repositório | PS4 (x86-64 nativo); só ideias de organização |
| [FelipePrado0/gow3_pc](https://github.com/FelipePrado0/gow3_pc) | — | GPL-2.0+ | PS4; só ideias de organização |
| [RPCS3/rpcs3](https://github.com/RPCS3/rpcs3) | `4d5def5` | GPL-2.0 | Referência de comportamento; **não é dependência** do executável nativo |

O MIT é compatível com a GPL-2.0 deste projeto. O ps3recomp declara que não contém código do RPCS3.

## ps3recomp: componentes

| Componente | Onde fica | Situação |
|---|---|---|
| Parser ELF/SELF, `unfself` (só fSELF de depuração, sem cifra) | `tools/elf_parser.py`, `tools/unfself.py` | Verificado: o `unfself` recusa SELF de varejo |
| Loader PPU (OPD, TOC, segmentos, importações por NID) | `tools/ppu_loader.py` | Verificado num ELF sintético |
| Detecção de funções | `tools/find_functions.py`, OPD do loader | Declarado: no Scott Pilgrim, 57.318 funções |
| **Lifter PPU** (PowerPC → C++) | `tools/ppu_lifter.py` (4.665 linhas) | **Verificado: 97/97 casos idênticos ao PowerPC (ver abaixo)** |
| Disassembler/lifter SPU | `tools/spu_disasm.py`, `tools/spu_lifter.py` | Não executado: o autoteste exige o compilador SPU do SDK da Sony |
| Memória (big-endian, 4 GB virtuais) | `runtime/memory`, `runtime/ppu/ppu_loader.cpp` | Verificado indiretamente (teste de boot) |
| Endianness | `include/ps3emu/endian.h` | Verificado indiretamente (o corpus lê e escreve memória) |
| Serviços LV2 (threads, mutex, eventos, memória, fs) | `runtime/syscalls`, `libs/system` | Declarados "completos"; teste de boot sintético verificado |
| HLE (cellGcm, cellAudio, cellPad, cellSaveData, SPURS...) | `libs/` (cerca de 100 mil linhas) | Declarados 93 completos e 5 parciais (SPURS e mídia, parciais) |
| RSX → Direct3D 12 | `runtime/rsx` | Declarado: o backend que roda jogos hoje |
| Integração com Windows | clang-cl, XInput, WASAPI | CI do projeto; verificação própria no `native.yml` |

### O que foi verificado

1. **Compilação no Linux** (GCC 13, 22 s): ok. `ctest`: 3 de 3 passaram.
2. **Suíte de conformidade do lifter:** 1.533 checagens passaram, 0 falharam (`tools/test_ppu_lift.py`). Os testes de desvios e de tabelas de salto também passaram.
3. **Boot sintético do runtime** (`ps3recomp_boot_smoke`): PASS. Carrega um ELF no formato do PS3, executa a thread do convidado, faz 3 flips pela FIFO do RSX e roda o handler de vblank.
4. **Teste diferencial deste projeto** (`native/ppu_diff`):
   - 17 funções nossas compiladas para PowerPC com `gcc -mcpu=cell -mcmodel=small`;
   - executadas no QEMU (`qemu-ppc64`) como referência;
   - recompiladas pelo `ppu_lifter` e compiladas para x86-64;
   - resultado: **97/97 casos idênticos** no Linux e no Windows x64 (MinGW + Wine localmente, clang-cl no GitHub Actions).
   - Cobertura: aritmética 32/64 bits, divisão, multiplicação alta, rotações, `cntlzw`, bswap, pilha, recursão, chamadas entre funções, `switch` com tabela de salto, dados globais via TOC e ponto flutuante simples/duplo (bit a bit).

### Limitações encontradas (e o que foi feito)

| Achado | Causa | Ação |
|---|---|---|
| `switch` caía numa "chamada indireta não recompilada" | O detector de tabelas só conhecia `lwzx`; o GCC usa `lwax` | Patch de 2 linhas (`native/ps3recomp-elfv1.patch`) |
| TOC errado (0x100016B0 em vez de 0x100E7E00) | O lifter lê descritores no formato do PS3 `{u32 código, u32 TOC}`; o ELF de teste usa ELFv1 de 64 bits | O mesmo patch faz `--toc` valer também para ELF |
| Tabela com endereço calculado por `addis/addi` a partir do TOC não é reconhecida | Modelo de código "medium" do GCC moderno | Corpus compilado com `-mcmodel=small`, que é a forma do código do PS3. O código do God of War III vem do toolchain do PS3, não deste GCC |
| 62 marcadores `TODO` no C gerado | Palavras de dados (`.long` das tabelas) e preenchimento dentro do intervalo das funções | Não executam; conferido no C gerado |

## Ports de referência: o que roda de verdade

- **Drakengard 3** (`dod3-recomp`): declarado jogável no Windows e no macOS, distribuído com instalador. O instalador **decifra** o executável da atualização a partir de chaves que o usuário informa. Isso é contorno de proteção, e este projeto não vai repetir.
- **Scott Pilgrim**: declarado em "boota, abre janela D3D12 a 32 fps e carrega os dados, sem geometria". São 59.429 funções recompiladas num executável de 101 MB. O EBOOT foi decifrado com `rpcs3 --decrypt` sobre um pacote "Crack-4.21" (está no PROGRESS.md). **Não é um caminho aceitável para este projeto.**
- Os dois provam que o caminho funciona para jogos inteiros. Nenhum dos dois é o God of War III.

## Bloqueio principal para o God of War III

Todo o pipeline começa por um **EBOOT em ELF decifrado**. O `EBOOT.BIN` do disco (BCES00510) é um SELF de varejo cifrado. Este projeto **não** implementa decifragem. O que já dá para fazer sem decifrar:

- `native/tools/analyze_gow3.py` lê PARAM.SFO e os cabeçalhos públicos do SELF: tipo, revisão de chave, versão, segmentos e quais estão cifrados;
- com um `EBOOT.ELF` preparado pelo próprio usuário, a mesma ferramenta gera o relatório de funções, importações (com cobertura do HLE), programas SPU e uma amostra recompilada.

## Riscos técnicos para o God of War III

1. **SPU/SPURS:** o jogo usa muito os SPUs. O suporte a SPURS do ps3recomp é declarado parcial, e o Scott Pilgrim parou justamente numa tarefa SPU de áudio.
2. **Tamanho:** jogos AAA têm dezenas de milhares de funções (o Uncharted tem 14.104). Isso significa centenas de MB de C++ e compilação demorada.
3. **Gráficos:** o RSX → D3D12 roda em ports menores. Um jogo da escala do God of War III vai exigir correções no backend.
4. **Validação:** a comparação com o comportamento de referência (RPCS3) precisa de rastreamento no nível de chamadas de sistema e quadros, a construir nas etapas seguintes.
