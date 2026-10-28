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

## O que esperar

O ps3recomp traduz e compila o jogo; fazê-lo rodar é o trabalho que vem depois (como no God of War:
Ascension, que levou cerca de 8 dias do EBOOT ao primeiro nível). A primeira execução deve parar em
alguma biblioteca do firmware ainda não implementada ou num comportamento do runtime; o resumo do
passo `rodar` mostra onde. Isso é o começo, não o fim.

Nada do que é gerado (código traduzido, executável, logs com endereços do jogo) deve ir para o GitHub:
a guarda do repositório (`native/tools/check_no_game_data.py`) bloqueia.
