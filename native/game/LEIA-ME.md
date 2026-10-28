# GOW3 Native: o God of War III inteiro, traduzido e compilado

`gow3_build.py` faz, no computador do usuário e sobre a cópia dele do jogo:

| Passo | O que faz |
|---|---|
| `elf` | Acha o EBOOT.ELF: `--elf`, o que o GOW3_Native_Analyzer já gerou (pasta `cache` dele) ou pede ao RPCS3 do usuário |
| `carregar` | `ppu_loader.py` do ps3recomp: funções (.opd), importações do firmware, segmentos, TOC |
| `traduzir` | `ppu_lifter.py --hle-stubs --chunks N`: todo o código PPU em C++ (as importações viram chamadas ao HLE do runtime) |
| `projeto` | Copia `templates/project` do ps3recomp e configura com CMake (Windows: clang-cl do Visual Studio + Ninja). Os programas SPU embutidos no EBOOT são achados e traduzidos pelo próprio modelo |
| `compilar` | Compila `GOW3Native.exe` |
| `rodar` | Roda o executável por `--segundos`, com a pasta do jogo como `/dev_bdvd`, e conta no log NIDs não implementados, chamadas indiretas sem destino, falhas de memória e flips de quadro |

Cada passo grava `logs/<passo>.log`; o andamento vai para `resumo.txt` e o estado para `estado.json`.
Um passo pode ser repetido sozinho: `--passos compilar,rodar`.

## Pré-requisitos (Windows)

- Python 3.12 e Git
- Visual Studio 2022 Build Tools com "Desenvolvimento para desktop com C++" e "Ferramentas C++ do Clang":
  `winget install Microsoft.VisualStudio.2022.BuildTools --override "--quiet --wait --add Microsoft.VisualStudio.Workload.VCTools --add Microsoft.VisualStudio.Component.VC.Llvm.Clang --includeRecommended"`
- CMake e Ninja: `winget install Kitware.CMake Ninja-build.Ninja`
- O ps3recomp no commit de `native/PS3RECOMP_COMMIT.txt`, com `native/ps3recomp-elfv1.patch`
- 16 GB de memória ou mais (menos memória: aumente `--arquivos`)

## Uso

```powershell
python native\game\gow3_build.py --jogo "I:\Games\PS3\...\God.Of.War.3.PS3" --ps3recomp I:\GOW3_Native\ps3recomp --trabalho I:\GOW3_Native\trabalho
```

## SPUs (programas embutidos e policy module)

O modelo do ps3recomp exige cobertura completa dos SPUs, e dois casos do God of War III pedem passos à
parte. Por isso a SPU_DIR é montada fora do CMake e passada com `--spu-dir`. Requer
`native/ps3recomp-gow3.patch` aplicado ao ps3recomp, além do `ps3recomp-elfv1.patch`.

1. Programas SPU embutidos (8). O Edge Zlib (`spu_83b0bc05…`) tem texto de assert depois do código, a
   partir de LS 0xAA80, e por isso recebe `--code-end`:
   ```powershell
   python ps3recomp\tools\build_spu_workloads.py --input <trabalho>\EBOOT.ELF --lifted <trabalho>\spu --out <trabalho>\spu\spu_workloads.c --constructor --code-end spu_83b0bc054de1b6ecba6f7dfa763ea2f2bcf2535183c567607bedbeeeb037ed9a=0xAA80
   ```
2. O policy module "Wws_Job" é um binário SPU cru, de 12.032 bytes em 0x49FF80, carregado em LS 0xA00.
   O runtime o procura pela impressão FNV-1a-64, que é conferida aqui:
   ```powershell
   python native\game\lift_pm.py <trabalho>\EBOOT.ELF --ps3recomp ps3recomp --ea 0x49FF80 --size 12032 --fp 0x7AE3FE49074DF128 --name pm_wwsjob --out <trabalho>\spu_pm
   python native\game\monta_spu_dir.py --programas <trabalho>\spu --pms <trabalho>\spu_pm --out <trabalho>\spu_dir
   python native\game\gow3_build.py ... --spu-dir <trabalho>\spu_dir
   ```

O `ps3recomp-gow3.patch` também traz `cellSpursCreateTaskset2` e `_cellSpursTasksetAttribute2Initialize`
(NIDs 0x4A6465E3 e 0xC2ACDF43), que o jogo chama três vezes cada durante a inicialização.

O runtime guarda `/dev_hdd1` em `<pasta do jogo>\cache`. Um cache FIOS incompleto, deixado por uma
execução interrompida, faz o jogo reabrir `cache.idx` sem parar. Para começar limpo, tire essa pasta
dali (ela não faz parte do jogo).

## Onde está (28/10/2026)

- Recompilação: 11.060 funções reais, nenhuma instrução sem tradução. Os TODO restantes estão só nas
  7.855 "funções" extras, que são dados lidos como código. `GOW3Native.exe` (117 MB), compilado com
  clang-cl em cerca de 5 minutos.
- Inicialização: módulos do sistema, SPURS "Big"/"Little", threads FIOS, abertura dos PSARC, GCM e
  janela D3D12. Os 8 SPUs e o PM foram resolvidos.
- **Parada atual: `_cellSpursLFQueuePushBody` (NID 0x8A85674D) não está implementada.** O PPU lê os
  dados zlib e tenta empurrá-los para a tarefa SPU do Edge Zlib por um LFQueue. Sem o push, a tarefa
  fica em WAIT_SIGNAL e o PPU fica em EventFlagWait. O consumidor é o próprio código SPU, que acessa a
  linha de 128 bytes da fila por GETLLAR/PUTLLC; por isso o push precisa seguir exatamente o algoritmo
  do CellSyncLFQueue em big-endian (push/pop, bs[], v1, eaSignal) e sinalizar a tarefa.

## O que esperar

O ps3recomp traduz e compila o jogo; fazê-lo rodar é o trabalho que vem depois (como no God of War:
Ascension, que levou cerca de 8 dias do EBOOT ao primeiro nível). A primeira execução deve parar em
alguma biblioteca do firmware ainda não implementada ou num comportamento do runtime; o resumo do
passo `rodar` mostra onde. Isso é o começo, não o fim.

Nada do que é gerado (código traduzido, executável, logs com endereços do jogo) deve ir para o GitHub:
a guarda do repositório (`native/tools/check_no_game_data.py`) bloqueia.
