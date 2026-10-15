# GOW3_Native_Analyzer (Fase 2)

Programa Windows para analisar o executável do God of War III (BCES00510) no computador do usuário e
testar a recompilação estática das primeiras funções PPU reais.

| Arquivo | Papel |
|---|---|
| `gow3_analyzer/formats.py` | identifica SELF/ELF/PARAM.SFO, SHA-256, cifra (não decifra nada) |
| `gow3_analyzer/analysis.py` | funções PPU, importações/NIDs, syscalls, PRX, SPU, fluxo, grafo, candidatas |
| `gow3_analyzer/recomp_test.py` | ps3recomp `ppu_lifter` → C++ → zig/clang → `GOW3_Native_RecompTest.exe`; teste diferencial |
| `gow3_analyzer/reference.py` | CPU de referência (Unicorn/QEMU) rodando o código PowerPC original |
| `gow3_analyzer/state.py` | estados iniciais determinísticos (mesmo gerador no C++) |
| `runtime/recomp_test_runtime.cpp` | runtime mínimo: memória big-endian por páginas, falhas, despacho indireto |
| `gow3_analyzer/report.py` | relatórios JSON, CSV e HTML (só metadados) |
| `gow3_analyzer/gui.py`, `cli.py` | janela e linha de comando |
| `build_exe.py` | empacota com PyInstaller e gera `GOW3_Native_Analyzer_Windows_x64.zip` |
| `tests/` | ELF sintético no formato de EBOOT, SELF de varejo sintético, validação Unicorn × QEMU, autoteste com mutação |

## Método do teste diferencial

O mesmo estado inicial (32 GPRs, 32 FPRs, CR, XER, CTR, LR, imagem do ELF, área de rascunho
preenchida por semente, pilha) é executado:

* pelo código recompilado (x86-64), e
* pelo código de máquina PowerPC original no Unicorn 2.1.4 (QEMU TCG, PPC64 big-endian).

Comparam-se todos os registradores e todos os bytes escritos. A referência é validada no CI contra
o `qemu-ppc64` nos 97 casos do corpus. O teste de mutação prova que um erro no código recompilado é
detectado.

Achados sobre a referência (verificados no código do Unicorn 2.1.4 e documentados no relatório):

* `ctl_set_cpu_model` com modelo PPC64 escolhe uma CPU de 32 bits (índice sem deslocamento); usa-se
  o modelo padrão de 64 bits com TLB "virtual".
* `UC_PPC_REG_XER` não traz SO/OV/CA; o XER é lido executando `mfxer` na página sentinela.
* `fctiw*/fctid*` fora do intervalo devolvem 0x80000000 (QEMU 5); a referência aplica a saturação
  do ISA nesses endereços.
* Após `fctiw/fctiwz` os 32 bits altos do FPR são indefinidos pelo ISA; diferença só neles é contada
  à parte.

Limitações: só funções folha sem syscalls, NIDs, VMX ou instruções dependentes do sistema; estados
sintéticos não são o estado do jogo em execução.
