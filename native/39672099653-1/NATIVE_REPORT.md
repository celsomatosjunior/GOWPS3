# GOW3 PS3 NATIVE — relatório da recompilação estática

Execução: https://github.com/celsomatosjunior/GOWPS3/actions/runs/39672099653

## Escada de progresso

| Etapa | Situação |
|---|---|
| 1. Ferramentas compiladas (ps3recomp no Windows, clang-cl) | ❌ failure |
| 2. Executável do God of War III analisado | ⬜ aguardando o EBOOT do jogo (ferramenta `native/tools/analyze_gow3.py` pronta) |
| 3. Código PPU recompilado | 🟨 corpus de teste: ✅ Windows x64, ✅ Linux; God of War III: ⬜ |
| 4. Código SPU recompilado | ⬜ |
| 5. Runtime inicializado | ⬜ |
| 6. Primeiro quadro renderizado | ⬜ |
| 7. Menu principal | ⬜ |
| 8. Gameplay | ⬜ |
| 9. Salvamento e carregamento | ⬜ |
| 10. Jogo completo | ⬜ |

## Teste diferencial PPU (código PowerPC real, não do jogo)

O corpus (`native/ppu_diff/corpus.c`, código do projeto) foi compilado para PowerPC com `gcc -mcpu=cell`, executado no QEMU como referência, recompilado para C pelo `ppu_lifter` do ps3recomp e compilado para x86-64.

- Funções recompiladas: 18; linhas de C geradas: 933; casos: 97
- Windows x64 (clang-cl): Recompilado x PowerPC no QEMU: 97/97 casos idênticos
- Linux x64 (clang): Recompilado x PowerPC no QEMU: 97/97 casos idênticos
- Executável Windows: arquivo: ppu_diff_lifted.exe  tamanho: 206848  sha256: 1E31E4E0C0B5868188E3B6AD4AFBD6F57F6D103BA9ADE0CFE79CEE435556A579

## ps3recomp no Windows

- Compilador: clang version 20.1.8
- ctest: sem resultado
- Conformidade de instruções (compiladas e executadas no Windows): sem resultado
- Andaime de boot PPU: ?

## O que isto NÃO prova

- Nada aqui executou código do God of War III.
- Recompilar e executar um corpus pequeno não garante que o jogo inteiro funcione: faltam a análise do executável real, SPU, runtime do sistema e gráficos (etapas 2 a 10).
