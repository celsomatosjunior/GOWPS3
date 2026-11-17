# Origem dos componentes de terceiros no GOW3 nativo

Este arquivo lista o código copiado ou adaptado de outros projetos que entra no GOW3 nativo. O GOW3 nativo é
formado pelo GOWPS3 mais os patches `native/ps3recomp-*.patch` sobre o ps3recomp 4e8f3ca8.

Para cada componente estão registrados o repositório, o commit de origem, o caminho original, a licença e o que
mudou aqui. A licença foi conferida no commit de origem em 17/11/2026.

Os créditos e avisos originais ficam como estão: cabeçalhos, `README`, `VENDOR.txt`, `MANIFEST.txt` e `LICENSE`.
Nos arquivos copiados ou adaptados, um comentário acrescenta a origem e as mudanças sem substituir esses créditos.

**Uso do código do Arnaldo Lima:** ele autorizou, em 11/11/2026, o uso e a publicação do código dele no GOW3.
O que entra aqui são componentes incorporados. O ps3kit original completo não é republicado como espelho nem
como projeto independente.

## Licença do resultado

- O ps3recomp e o GOWPS3 são MIT.
- A pasta `gpu/` do ps3recomp contém o RSX do RPCS3, que é **GPL-2.0**. Ela e todo executável que a liga (o GOW3
  nativo com a ponte do RSX, o padrão desde 13/11) ficam sob GPL-2.0.
- Sem a ponte (com `PS3_RSX=live`, o live draw), o resto continua MIT. Ver `gpu/README.md`.

## Componentes

| # | Componente (onde está aqui) | Origem: repositório, commit, caminho | Licença na origem | Adaptações aqui |
|---|---|---|---|---|
| 1 | `gpu/rsx/` do ps3recomp (RSX do RPCS3: NV4097, decompiladores de shader, Vulkan/OpenGL, `Emu/Memory`, `Utilities`, `util`) | github.com/RPCS3/rpcs3, commit 1b336f41f, os arquivos listados em `gpu/rsx/MANIFEST.txt`; trazido pelo ps3kit (abaixo) | GPL-2.0 | As mudanças do ps3kit estão em `gpu/rsx/VENDOR.txt`. As nossas levam a marca `ps3recomp:` no código: relatórios e labels dentro do lock de linha (`ps3recomp_store.h`, `nv47_sync.hpp`, `nv4097.cpp`; ps3recomp bd87a475) e diagnóstico de saltos do FIFO (`RSXFIFO.cpp`; 3b325623, 8287cda3) |
| 2 | `gpu/bridge/`, `gpu/shim/`, `gpu/tests/`, `gpu/tools/vendor_rpcs3.py`, `gpu/CMakeLists.txt`, `gpu/ps3rsx.cmake`, `gpu/README.md` | github.com/arnaldolima1/ps3kit (privado), ramo `ascension-perf`, commit 2e972569, pasta `gpu/` (Arnaldo Lima) | GPL-2.0 (o `gpu/README.md` da origem declara a pasta GPL-2.0 por ligar o RPCS3); o resto do ps3kit é MIT (LICENSE de sp00nznet) | Importado em ps3recomp affda8fe (11/11). Mudanças: `vm_commit` sobre o vm do RPCS3 e pilhas de callback (37528aa0), `ps3rsx.cmake` versionado (2f2903e7), ganchos de lock (bd87a475) |
| 3 | `gpu/third_party/imgui/` | Dear ImGui, vindo pelo ps3kit 2e972569 | MIT (`gpu/third_party/imgui/LICENSE.txt`) | nenhuma |
| 4 | `gpu/third_party/glslang`, `gpu/third_party/asmjit` (submódulos; o patch não os leva) | github.com/KhronosGroup/glslang f0bd0257c308; github.com/asmjit/asmjit 416f7356967c | glslang: BSD-3-Clause e outras (`LICENSE.txt` dele); asmjit: Zlib | nenhuma; obtidos à parte (ver LEIA-ME, instalação) |
| 5 | `gpu/rsx/3rdparty/stblib` | stb, via RPCS3 1b336f41f | MIT / domínio público (`stb/LICENSE`) | nenhuma |
| 6 | `libs/video/cellGcmSys.c/.h` do ps3recomp: RSX externo (`CellGcmRsxHooks`, espelho do mapa de IO, relatórios em +2 MB + 0x1400, memória de vídeo do sistema) | ps3kit 2e972569, `libs/video/cellGcmSys.c` | MIT (ps3kit) | Adaptado ao nosso cellGcmSys; cada trecho comentado com "ps3kit"/"From Arnaldo Lima's ps3kit" (affda8fe) |
| 7 | `runtime/memory/vm.h`: `vm_commit` aceita faixa já mapeada | ps3kit 2e972569 | MIT | comentário "(ps3kit, Arnaldo Lima, 2e972569)" (37528aa0) |
| 8 | `runtime/spu/spu_jobcap_state_ps3kit.c` (estado inicial do job na gravação/reprodução) | ps3kit `ascension-perf` 2e972569, `runtime/spu/spu_jobcap.c` (`sjc_state`, `state_save`, `state_load`) | MIT | Sem `resident_code`/`pic_delta`; cabeçalho de origem no arquivo |
| 9 | `runtime/spu/spu_channels.c` (`SPU_IBL`) e `tools/spu_ibl.py` | ps3kit 6e5d0707, `tools/spu_lifter.py` (`local_indirect_branches`, `SPU_LIFT_IBL`), que segue o `ib_local.py` de otavix010 | MIT (ps3kit; gow-ascension-pc de otavix010) | Aplicado ao policy module do GOW3; desligado por padrão (`SPU_IBL=1`); créditos nos dois arquivos (9d318b63) |
| 10 | `tools/spu_cc_pn.py` (`--spu-pn`) | github.com/otavix010/gow-ascension-pc 5370a01, `scripts/spu_cc_interno.py`; separação `SPU_DIRECT_PN/_TR` do ps3kit (Arnaldo) | MIT (otavix010 and contributors; ps3kit) | Adaptado ao nosso tradutor; desligado (neutro); créditos no arquivo |
| 11 | `native/game/gow3_rsx_rpcs3.cpp` do GOWPS3 (seleção da ponte, início do RSX, ganchos do GCM, tratador de falhas) | ps3kit `ascension-perf` 2e972569, `runtime/ppu/tests/boot_main.cpp` (`ps3rsx_select`, `rpcs3_rsx_start`, `s_rpcs3_hooks`, tratador de falhas) | GPL-2.0 (liga a ponte) | Adaptado ao main do GOW3 (GOWPS3 7c856ed, c36dfe2 e seguintes); cabeçalho de origem no arquivo |
| 12 | `native/game/gow3_diag.cpp`: prioridade do PPU e afinidade de threads | Ideia e topologia de `PS3_PPU_PRIO` (arnaldolima1/gow-ascension-pc, `ascension_defaults.cpp`, MIT) e `PS3_HOST_PIN` (ps3kit 463d832b, `perf_threads.c`, MIT) | MIT | Reescrito aqui; créditos nos comentários |

## Só local (não publicado)

| Componente | Origem | Licença na origem | Por que fica local |
|---|---|---|---|
| `GOW3_trabalho\edge_nativo\gow3_edge_idx*.h`: descompressão de índices do EDGE | github.com/arnaldolima1/ascension-native (privado) 8157f09, `render/geometry/indices.c` e gancho `e4d0` de `native_hooks.c` | sem arquivo de licença (uso autorizado pelo Arnaldo em 12/11) | Os núcleos `edge_nativo` têm endereços e constantes do jogo (regra: nada derivado do jogo no repositório) |
| `GOW3_trabalho\wws_exec\gow3_wws_const.h` | gerado de despejos do jogo | n/a | dados do jogo |

## Só ideias (sem código copiado)

- Gravação e reprodução de jobs SPU (`spu_jobcap.c`, `spu_jobreplay.c`): mesma ideia do `SPU_JOBCAP` do ps3kit.
- Disposição da pasta `gpu/` (só o código de GPU do emulador mais um shim), como no `FelipePrado0/gow3_pc`
  (registrado no `gpu/README.md` da origem).
- Notas do SpartanPort (FelipePrado0, GPL) e do executor Wws do ascension-native: só leitura.

## Como manter

Ao copiar ou adaptar algo novo:

1. Conferir a licença no commit de origem.
2. Pôr no arquivo um comentário com a origem (repositório, ramo, commit, caminho) e o que mudou, sem tirar os
   créditos que já existem.
3. Acrescentar uma linha aqui.

Código do RPCS3 recebe a marca `ps3recomp:` nas mudanças, como pede o `VENDOR.txt`.
