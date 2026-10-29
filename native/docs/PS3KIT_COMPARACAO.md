# ps3kit × GOW3 Native (ps3recomp v0.18 + `native/ps3recomp-gow3.patch`)

Comparação feita em 29/10/2026 sobre um clone local do ps3kit (`arnaldolima1/ps3kit`, ramo padrão, commit
`a6032d51`, 2.259 commits), autorizada pelo autor. O ps3kit é privado: este relatório só descreve, cita
nomes de arquivo e função e não traz código dele.

## O que é o ps3kit

É um fork privado do ps3recomp feito para o port de God of War: Ascension (BCES01741), sobre o upstream
**v0.17.0** com várias correções de SPU trazidas depois, uma a uma (`README.md`, seção "What this fork adds";
o `CHANGELOG.md` ainda para na v0.14). O nosso projeto usa o ps3recomp **v0.18.0** (commit `4e8f3ca8`,
`native/PS3RECOMP_COMMIT.txt`) mais dois patches nossos. Os dois jogos usam o mesmo motor da Santa Monica
(Wws_Job, Edge, RsxSync, MLAA nos SPUs), então boa parte dos problemas é a mesma.

## 1. O que os dois resolvem

| Tema | ps3kit | Nosso (`ps3recomp-gow3.patch` + `native/game`) | Melhor |
|---|---|---|---|
| **Taskset2** (`cellSpursCreateTaskset2`, `_cellSpursTasksetAttribute2Initialize`) | Em `libs/spurs/cellSpurs.c`: cria com tamanho 0x2900, lendo do atributo só o argumento do taskset; prioridade e contenção máxima ficam no padrão | Mesmo tamanho 0x2900, e também passa a prioridade por SPU e a `maxContention` do atributo para `spurs_create_taskset` | **Nosso**, um pouco mais fiel ao atributo; o resto é equivalente |
| **SPURS2** (`cellSpursInitializeWithAttribute2`, 32 workloads) | Tem (commit `b2907d5d`): a segunda metade dos workloads com os campos próprios da instância (readyCount2, wklSignal2, wklState2, wklInfo2) e a flag de 32 workloads | Não tem: o kernel do HLE vai até 16 workloads | **ps3kit**. O GOW3 usa 12 workloads e por isso não precisou, mas é uma lacuna nossa |
| **Task2** (`_cellSpursTaskAttribute2Initialize`, `cellSpursCreateTask2`) | Lê `sizeContext` (+0x04), a palavra baixa de `eaContext` (+0x0C) e o `lsPattern` (+0x10); a inicialização zera só os 0x24 primeiros bytes | Mesmos campos (`eaContext` lido como u64 e truncado) | **Empate** |
| **Workload flag** (`cellSpursGetWorkloadFlag`, `_cellSpursWorkloadFlagReceiver`) | **Não tem**: as duas funções só aparecem na tabela de NIDs (`tools/nid_database.py`), e o kernel não olha o flag em `spurs+0x6C`/`+0x77` | Tem as duas funções e o kernel dispara o receptor quando o flag zera, como o RPCS3. O receptor usa CAS no byte +0x77, e há a correção do travamento por `vm_write32` dentro do lock-line | **Nosso**. É o que faz o RsxSync (wid 11) rodar no GOW3 |
| **Rodada RsxSync/MLAA perdida** (o RSX recompilado é rápido demais) | `GCM_ROUND_GATE` / `GCM_ROUND_RING` / `GCM_ROUND_GATE_MODE` (`libs/video/cellGcmSys.c`, `runtime/ppu/tests/boot_main.cpp`, `runtime/spu/spu_channels.c`). Segura o relatório que inicia a próxima rodada até as tarefas da rodada atual terminarem, olhando o progresso do próprio jogo; funciona com o RSX do RPCS3 e com o walker do runtime | `GCM_SEMA_ACQUIRE=1` (o `SEMAPHORE_ACQUIRE` passa a bloquear) e park sem atalho (`GCM_PARK_GRACE_MS` longo), ligados pelo `gow3_build.py` | **ps3kit**, mais preciso: atua só no ponto da corrida e mede menos espera. O nosso é genérico e mais simples, mas deixa o RSX parado durante toda a rodada |
| **Espera do park** | `GCM_PARK_WAIT_MS` (nome diferente do nosso) | `GCM_PARK_GRACE_MS` | Mesma ideia; atenção ao nome da variável |
| **LFQueue** (`_cellSpursLFQueueInitialize`, `_cellSpursLFQueuePushBody`) | HLE próprio do push em `cellSpurs.c`: anel com os índices de push e pop, espera por espaço quando bloqueante e acorda a tarefa estacionada. Não há `_cellSpursLFQueuePopBody` | LLE seletivo: a libsre do firmware do usuário é recompilada, só as três funções da LFQueue (push, pop e init) são ligadas a ela, e só a função de sinal é trocada (`native/game/gow3_libsre_lle.cpp`) | **Nosso** em fidelidade (é o código da Sony e cobre o pop); **ps3kit** em simplicidade (não precisa de firmware nem de passo extra) |
| **Edge Zlib** | `PS3_EDGE_ZLIB_HLE=1`: o pedido de descompressão vai ao host por um inflate próprio (`libs/codec/edge_inflate.cpp`, vindo do port do Twisted Metal), lido do elemento de 32 bytes da fila do Ascension | O programa SPU Edge Zlib traduzido roda de verdade; precisou de `--code-end` no `build_spu_workloads.py` | **ps3kit** em velocidade (host); **nosso** em fidelidade. O layout do elemento é o do Ascension, e ninguém conferiu se é igual no GOW3 |
| **cellGcm: tabela de offsets viva** | Tem (`s_offset_tables_published` em `libs/video/cellGcmSys.c`) | Tem (no nosso patch, sobre a v0.18) | **Empate** |
| **cellGcm: `put` sem IO mapeado** | Trata o `put` inválido (`land == 0xFFFFFFFF`) no walker | Não persegue o `put` sem página de IO (a varredura travava a janela) | Equivalentes em intenção; ninguém comparou caso a caso |
| **Sinal de tarefa (bit `signalled`)** | Leitura-modificação-escrita sob o lock-line, como o upstream, e teste próprio (`runtime/spu/tests/test_spurs_signalled_atomic.c`). O WAIT_SIGNAL ainda testa o bit e só o apaga depois | Mesma base, e o WAIT_SIGNAL consome o bit no instante em que o vê (`spu_signalled_take` em `runtime/spu/spu_workload.c`), como o kernel do SPURS | **Nosso**: fecha a janela em que um segundo sinal se perdia. O teste do ps3kit é melhor como cobertura |
| **cellVdec com fila cheia** | Guarda as AUs (`pend[]`, `pendCount` em `libs/codec/cellVdec.c`) e as decodifica quando há espaço, com o AUDONE depois | Mesma ideia (`vdec_pump`), e a nossa copia os bytes do AU, caso o jogo reaproveite o buffer; também desligamos o "idle drain" para o GOW3 | **Empate** na ideia; o nosso é mais seguro contra buffer reaproveitado, o deles não aloca memória |
| **Título do jogo** | `cellGame_init_from_paramsfo` em `libs/system/cellGame.c` | O mesmo (veio do upstream), chamado por `gow3_libsre_lle.cpp` | **Empate** |
| **Coerência SPU/RSX** | `ps3rsx_dma_put`: os PUTs das SPUs entram no protocolo de reserva do RPCS3 (`gpu/README.md`), e os labels e relatórios do RSX quebram reservas | Só a coerência do runtime (lock-line, bitmap de reservas) | **ps3kit**, porque tem o RSX do RPCS3; para o walker do runtime os dois são iguais |

## 2. O que só o ps3kit tem

- **Ponte com o RSX do RPCS3** (`gpu/`). Com `PS3_RSX=rpcs3`, o desenho é feito pelo RSX do RPCS3 (máquina de
  estados NV4097, decompiladores de shader, backends Vulkan e OpenGL) no lugar do live draw. A pasta tem:
  - `gpu/rsx/`: o código do RPCS3 (commit `1b336f41f`) de que o RSX precisa (`Emu/RSX`, `Emu/Memory`,
    `Utilities`, `util`), com `MANIFEST.txt` e `VENDOR.txt` e as mudanças marcadas `ps3recomp:`;
  - `gpu/shim/`: o que esse código espera do resto do emulador (`emu.cpp`, `cpu_thread.cpp`, `lv2_rsx.cpp`,
    stubs);
  - `gpu/bridge/`: a ligação com o runtime. `ps3rsx_init_memory` põe a memória do jogo no `vm` do RPCS3,
    `ps3rsx_start` liga o RSX a um contexto GCM em `CELL_GCM_RSX_CONTEXT` (0x2E000000), e há o espelho do mapa
    de IO e dos buffers de tela, flips pelo método 0xE920, faltas em páginas protegidas
    (`ps3rsx_handle_fault`) e uma interface C em `ps3rsx.h`;
  - do lado do runtime: `CellGcmRsxHooks` e `cellGcm_set_rsx_hooks` em `libs/video/cellGcmSys.h`, ligados em
    `runtime/ppu/tests/boot_main.cpp`;
  - `gpu/ps3rsx.cmake` (`ps3rsx_link`) liga o port à biblioteca, com pilhas de 8 MB;
  - `gpu/tests/ps3rsx_flip_smoke.c` testa o RSX sem jogo;
  - diagnósticos: `PS3_FLIP_DUMP`, `PS3RSX_DUMP`, `PS3RSX_LOG`, `PS3_RSX_FIFO`, `PS3_RSX_DMA_LOCK`.

  Ajustes que o Ascension pediu ao RPCS3, que interessam ao GOW3 por ter o mesmo RsxSync:
  - escrita de labels e relatórios avisada ao host (`g_ps3recomp_rsx_write_hook`);
  - relatório tipo 255 desalinhado escrito sem o atômico de 16 bytes;
  - uma espera antes desse relatório (`g_ps3recomp_rsx_report_hold`), para a rodada pós-processo não perder o
    sinal.

  Licença: tudo que liga `gpu/` vira GPL-2.0.
- **Live draw no macOS** pelo vkd3d (`PS3RECOMP_LIVE_DRAW_VKD3D`, `libs/video/rsx_live_draw_vkd3d.{h,c}`).
- **Comparação quadro a quadro** entre os dois desenhos (`PS3_FLIP_DUMP` do RSX do RPCS3, `LD_RECORD=<mp4>`
  do live draw).
- **Jobs SPU nativos** (`libs/spu_hle/gowa_drawcmd`, só x86): os jobs de geometria do módulo 218 do Ascension
  em código nativo, e as listas Wws dos workloads 15–17 fora do SPURS (`GOWA_WWS_EXEC`). No GOW3 os jobs Wws
  ainda rodam no interpretador SPU (ver o LEIA-ME), então essa é a referência de como acelerá-los.
- **SPURS2** (32 workloads), citado acima.
- **Ordenação de memória arm64** no DMA das SPUs (PUT = release, GET = acquire).
- **Planos e medições do Ascension** em `docs/` (`ASCENSION_*`, `SPURS_SCHEDULING.md`, `FIRMWARE_LLE.md`,
  `SPU_FALLBACK.md`), úteis como referência de método.

## 3. O que só nós temos

- O workload flag inteiro (funções, receptor e disparo no kernel) e a correção do travamento ao consumi-lo.
- O LLE seletivo da libsre para a LFQueue (`gow3_libsre_lle.cpp`, `lift_prx.py --raw`) e a troca da função
  de sinal.
- `--code-end NOME=ADDR` no `build_spu_workloads.py` (o Edge Zlib do GOW3 tem texto depois do código). O
  ps3kit tem `--code-end` no `spu_lifter.py` e no `ppu_lifter.py`, não no `build_spu_workloads.py`.
- O policy module Wws registrado à parte (`lift_pm.py`, `monta_spu_dir.py`).
- O fim do código pelas seções executáveis (PR do Arnaldo no nosso `gow3_build.py`: 11.482 funções e 0 TODO).
- `--ffmpeg`, `RSX_LIVE_DRAW` por padrão no passo `rodar` (`gow3_rsx.cpp`) e os diagnósticos `GOW3_*`.

## 4. O que muda no `gow3_build.py` para compilar sobre o ps3kit

1. **`--ps3recomp` passa a apontar para o checkout do ps3kit.** O `ps3recomp-elfv1.patch` não é mais
   necessário: o `ppu_lifter.py` do ps3kit já tem `--toc`. O `ps3recomp-gow3.patch`, porém, **não aplica
   como está**, porque foi feito sobre a v0.18. Seria preciso um patch novo, só com o que falta no ps3kit:
   - `cellSpursGetWorkloadFlag`, `_cellSpursWorkloadFlagReceiver` e o disparo do receptor no kernel;
   - a inicialização do flag (+0x6C = −1, +0x77 = 0xFF);
   - o `spu_signalled_take` no WAIT_SIGNAL;
   - `--code-end` no `build_spu_workloads.py`;
   - os diagnósticos (`SPURS_PM_TRACE`, `SPURS_FLAG_DBG`, `SPU_SIG_TRACE_TS`, `SPU_DMA_IMG`, `VDEC_AUDBG`,
     `TEX_DRAWLOG`).

   Taskset2, Task2, o push da LFQueue, a tabela de offsets e as AUs retidas do vídeo já existem lá e saem do
   patch.
2. **Variáveis do passo `rodar`:**
   - `GCM_PARK_GRACE_MS` vira `GCM_PARK_WAIT_MS`;
   - avaliar `GCM_ROUND_GATE` no lugar de `GCM_SEMA_ACQUIRE=1`. Para isso é preciso achar o descritor da rodada
     do GOW3, o equivalente do 0x9BAC30 do Ascension. Pelo que já mapeamos, fica perto dos descritores de job
     do RsxSync (0x64A750 / 0x64A760 / 0x64A860 / 0x64A960) e dos contadores 0x64AA78–0x64AA80;
   - `VDEC_IDLE_DRAIN_MS` não existe no cellVdec do ps3kit, que não tem esse dreno, então pode sair.
3. **LFQueue e Edge Zlib:** dá para manter o `--lle-libsre`, desde que o patch novo desligue o push HLE do
   ps3kit para não registrar o mesmo NID duas vezes. Ou testar `PS3_EDGE_ZLIB_HLE=1`, conferindo antes o layout
   de 32 bytes do elemento no GOW3.
4. **Modelo de projeto:** o `templates/project/main.cpp` do ps3kit tem os mesmos três `rsx_backend_*` do D3D12,
   então o `use_gow3_rsx()` continua valendo para o live draw. O `CMakeLists.txt` do modelo aceita `SPU_DIR`
   (`--spu-dir` funciona), mas não tem `PORT_SPU_INPUTS`: sem `--spu-dir`, os SPUs teriam de vir de outro
   lugar.
5. **Para usar o RSX do RPCS3** (`PS3_RSX=rpcs3`):
   - compilar antes `gpu/` com o MSVC `cl`, não com o clang-cl: o RPCS3 não compila com o clang-cl. Pede
     Vulkan SDK e os submódulos `gpu/third_party/glslang` e `asmjit`, mais o alvo `ps3rsx_flip_smoke`;
   - ligar o executável com `ps3rsx_link` (`gpu/ps3rsx.cmake`), o que no `gow3_build.py` é um passo novo de
     projeto, com o caminho da build de `gpu/`;
   - levar ao nosso `main.cpp` (pelo `gow3_rsx.cpp`) o que o `boot_main.cpp` do ps3kit faz:
     - pegar a memória de `ps3rsx_init_memory()` antes de o runtime criar a sua;
     - registrar os `CellGcmRsxHooks`;
     - desligar o walker do FIFO e o live draw;
     - deixar o ticker só com a janela e o vblank;
     - mandar as faltas de página do RSX para `ps3rsx_handle_fault`;
   - a build que liga o RSX do RPCS3 fica GPL-2.0, como o nosso repositório já é.

## Recomendação

O caminho mais curto é **continuar na v0.18 e trazer as ideias do ps3kit uma a uma**, cada qual escrita de
novo: o round gate no lugar do `GCM_SEMA_ACQUIRE`, o SPURS2 se for preciso, e os jobs Wws nativos para
acelerar. Os motivos:
- o GOW3 já fecha a cadeia de quadros e mostra o logo e a abertura com o live draw;
- o ps3kit está numa base mais antiga (v0.17) e não tem o workload flag, de que o GOW3 depende.

O RSX do RPCS3 vale como **segundo motor de comparação** quando o live draw empacar num quadro: é a melhor
referência de imagem que existe, mas a integração é grande (MSVC, Vulkan, GPL, troca da memória do runtime).
Se o Arnaldo preferir que o GOW3 viva dentro do ps3kit, o item 4 é a lista de trabalho.
