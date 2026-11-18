# GOW3 Native: o God of War III inteiro, traduzido e compilado

`gow3_build.py` faz, no computador do usuário e sobre a cópia dele do jogo:

| Passo | O que faz |
|---|---|
| `elf` | Acha o EBOOT.ELF: `--elf`, o que o GOW3_Native_Analyzer já gerou (pasta `cache` dele) ou pede ao RPCS3 do usuário |
| `carregar` | `ppu_loader.py` do ps3recomp: funções (.opd), importações do firmware, segmentos, TOC |
| `traduzir` | `ppu_lifter.py --hle-stubs --chunks N`: todo o código PPU em C++ (as importações viram chamadas ao HLE do runtime) |
| `projeto` | Copia `templates/project` do ps3recomp e configura com CMake (Windows: clang-cl do Visual Studio + Ninja) |
| `compilar` | Compila `GOW3Native.exe` |
| `rodar` | Roda o executável por `--segundos`, com a pasta do jogo como `/dev_bdvd`, e resume o log |

Cada passo grava `logs/<passo>.log`; o andamento vai para `resumo.txt` e o estado para `estado.json`. Um passo
pode ser repetido sozinho: `--passos compilar,rodar`.

O histórico completo (decisões, medidas, experimentos descartados e seus motivos) está em
[HISTORICO.md](HISTORICO.md). A origem e a licença de cada componente de terceiros estão em
[../docs/ORIGEM_COMPONENTES.md](../docs/ORIGEM_COMPONENTES.md).

## Estado atual (17/11/2026)

- **Roda:** abertura, menus e a fase do Poseidon com combate, com imagem completa. Testes de 600 s em combate
  rodam sem travar.
- **Velocidade:** ~12,5-13 quadros reais/s na fase. O RPCS3 faz ~22 na mesma cena, então o nativo está em
  ~57-60% dele.
  - O gargalo é a cadeia serial das listas EDGE (wids 8-10) nas SPUs, a ~29,5 us por job.
  - O RSX fica quase todo ocioso.
- **Ligado por padrão:**

  | O quê | Como desligar |
  |---|---|
  | RSX do RPCS3 (ponte `gpu/`) | `PS3_RSX=live` volta ao live draw D3D12 |
  | Executor Wws próprio nas listas EDGE | `GOW3_WWS_EXEC=0` |
  | Relatórios e labels do RSX dentro do lock de linha (corrige a travada do label 0x51) | `PS3_RSX_STORE_LOCK=0` |
  | No tradutor SPU: `--spu-vivos seguro`, `shufb-inv`, `SPU_CFLT_INT` | — |
  | No tradutor SPU: recarga após chamadas | `--no-spu-recarga` |
  | No tradutor SPU: folha 912f:4C48 fundida | `--sem-fundir-folha` |
  | Núcleos EDGE nativos (locais, `edge_nativo`) | — |

- **Versão funcional:** o ramo `native-recomp`. O ps3recomp de trabalho é o ramo local `integra-17nov`; o
  que vai para o repositório são os patches.
- **Envio:** aos dois repositórios. O último foi em 18/11; o próximo regular, em 24/11.

## Instalação

### Pré-requisitos (Windows)

- Python 3.12 e Git.
- Visual Studio 2022 Build Tools, com "Desenvolvimento para desktop com C++" e "Ferramentas C++ do Clang":
  `winget install Microsoft.VisualStudio.2022.BuildTools --override "--quiet --wait --add Microsoft.VisualStudio.Workload.VCTools --add Microsoft.VisualStudio.Component.VC.Llvm.Clang --includeRecommended"`
- CMake e Ninja: `winget install Kitware.CMake Ninja-build.Ninja`.
- Vulkan SDK, para a ponte do RSX. Foi testado com o 1.4.363.0.
- FFmpeg LGPL compartilhado, da série das DLLs, para os vídeos (`--ffmpeg <pasta com include/ e bin/>`).
- 16 GB de memória ou mais. Com menos memória, aumente `--arquivos`.
- O RPCS3 do usuário, para gerar o EBOOT.ELF e converter a libsre do firmware dele.

### ps3recomp com os patches

Base: ps3recomp 4e8f3ca8 (v0.18.0), o commit de `native/PS3RECOMP_COMMIT.txt`. Os três patches já contêm o
`ps3recomp-elfv1.patch`; não o aplique à parte.

```powershell
git clone https://github.com/sp00nznet/ps3recomp; cd ps3recomp; git checkout 4e8f3ca8
git apply --whitespace=nowarn <GOWPS3>\native\ps3recomp-gow3.patch    # runtime, SPURS, executor Wws, GCM, ferramentas
git apply --whitespace=nowarn <GOWPS3>\native\ps3recomp-gpu-1.patch   # gpu/rsx/Emu (RSX do RPCS3, GPL-2.0)
git apply --whitespace=nowarn <GOWPS3>\native\ps3recomp-gpu-2.patch   # o resto de gpu/ (ponte do ps3kit, GPL-2.0)
# dependências da ponte (os patches só registram os commits):
git clone https://github.com/KhronosGroup/glslang gpu\third_party\glslang; git -C gpu\third_party\glslang checkout f0bd0257c308
git clone https://github.com/asmjit/asmjit gpu\third_party\asmjit;       git -C gpu\third_party\asmjit checkout 416f7356967c
```

Notas:

- Num clone já usado, limpe também os arquivos ignorados antes de aplicar (`git clean -fdx`). Um
  `gpu/ps3rsx.cmake` velho faz o `gpu-2` falhar.
- Sem LF/CRLF uniformes, o `rsx_live_draw.c` pode diferir só no fim de linha. Isso não afeta a compilação.

### A ponte do RSX (MSVC; o código do RPCS3 não compila com clang-cl)

Num prompt "x64 Native Tools", com o `VULKAN_SDK` definido:

```bat
cmake -S ps3recomp\gpu -B <trabalho>\gpu-build -G Ninja -DCMAKE_C_COMPILER=cl -DCMAKE_CXX_COMPILER=cl -DCMAKE_BUILD_TYPE=Release
ninja -C <trabalho>\gpu-build ps3rsx_flip_smoke
```

**Toda mudança em `ps3recomp/gpu` exige compilar a ponte de novo.** O `gow3_build.py` liga a `ps3rsx.lib` pronta
e não percebe uma ponte velha.

### SPUs (programas embutidos, policy module e módulos de job)

1. Programas SPU embutidos (8). O Edge Zlib tem texto de assert depois do código, por isso recebe `--code-end`:
   ```powershell
   python ps3recomp\tools\build_spu_workloads.py --input <trabalho>\EBOOT.ELF --lifted <trabalho>\spu --out <trabalho>\spu\spu_workloads.c --constructor --code-end spu_83b0bc054de1b6ecba6f7dfa763ea2f2bcf2535183c567607bedbeeeb037ed9a=0xAA80
   ```
2. Policy module "Wws_Job": é um binário SPU cru, de 12.032 bytes em 0x49FF80, carregado em LS 0xA00.
   ```powershell
   python native\game\lift_pm.py <trabalho>\EBOOT.ELF --ps3recomp ps3recomp --ea 0x49FF80 --size 12032 --fp 0x7AE3FE49074DF128 --name pm_wwsjob --out <trabalho>\spu_pm
   python native\game\monta_spu_dir.py --programas <trabalho>\spu --pms <trabalho>\spu_pm --out <trabalho>\spu_dir
   ```
3. Módulos de job Wws (24, nativos):
   ```powershell
   python ps3recomp\tools\lift_jobmods.py --engine-elf <trabalho>\EBOOT.ELF --base-zero --out <trabalho>\spu_jobs --register <trabalho>\spu_jobs\jobmods_register.c
   ```
   Opcional: sementes por módulo (`--module-funcs`), tiradas dos pcs que o interpretador SPU recebe numa execução
   com `SPU_INTERP_PCLOG` e divididas por `native/tools/jobmod_seeds.py` (ver HISTORICO, 29/10). Elas tiram do
   interpretador as entradas alcançadas só por salto indireto; o jogo roda sem elas.

### libsre (LLE seletivo da LFQueue)

O ps3recomp não tem `_cellSpursLFQueuePushBody`, e o consumidor da fila é o código SPU do jogo. Por isso a libsre
do firmware do usuário é recompilada e só a LFQueue é ligada a ela:

```powershell
# <lle> = <trabalho>\firmware\libsre_lle
# 1. o RPCS3 do usuário converte uma cópia da libsre do firmware (gera <trabalho>\firmware\rpcs3_conversao\libsre.prx)
copy <RPCS3>\dev_flash\sys\external\libsre.sprx <trabalho>\firmware\
python native\tools\converte_sprx.py <trabalho>\firmware\libsre.sprx <RPCS3>\rpcs3.exe
# 2. imagem, funções e importações
python ps3recomp\tools\lift_prx.py <trabalho>\firmware\rpcs3_conversao\libsre.prx --base 0x30000000 --output <lle>
# 3. as importações viram a lista [{library,nid,stub}] de --hle-stubs
python -c "import json,sys; d=json.load(open(sys.argv[1])); json.dump([{'library':l,'nid':n,'stub':s} for l,m in d.items() for n,s in m.items()], open(sys.argv[2],'w'))" <lle>\libsre_imports.json <lle>\libsre_hle_stubs.json
# 4. tradução
python ps3recomp\tools\ppu_lifter.py <lle>\libsre_image.bin --raw --base 0x30000000 --toc 0x30039AB0 --functions <lle>\libsre_functions.json --hle-stubs <lle>\libsre_hle_stubs.json --symbol-prefix libsre_ --single-file --header-name libsre_recomp.h --source-name libsre_recomp.cpp --output <lle>\lifted
```

`gow3_libsre_lle.cpp` carrega `libsre_image.bin` de junto do `.exe`, sem embutir a imagem. Sem a libsre o título
vira BLES00000 e o jogo não passa da inicialização. Nada derivado do firmware vai para o repositório.

### Compilar

```powershell
python native\game\gow3_build.py --jogo "<pasta do jogo>" --ps3recomp <ps3recomp> --trabalho <trabalho> --pular-videos --spu-jobs <trabalho>\spu_jobs --spu-dir <trabalho>\spu_dir --ffmpeg <ffmpeg> --rsx-rpcs3 <trabalho>\gpu-build
```

O build acha `<trabalho>\firmware\libsre_lle` sozinho. `--pular-videos` aplica a uma cópia local do EBOOT o patch
que deixa o X pular os vídeos, como no RPCS3.

### Save e cache

- **Save:** o jogo lê `BCES00510-USERDATA` em `<trabalho>/gamedata/dev_hdd0/home/00000001/savedata/`. Copie-o do
  RPCS3. Sem ele, o boot segue o caminho de "primeira vez". O save é do usuário e fica só no PC dele.
- **Saves do jogo** (validado em 18/11 com cópias dos saves do RPCS3 do Celso; os do RPCS3, `BCES00510-<data>`,
  podem ser copiados para a mesma pasta, com `cp -p`/`robocopy /COPY:DAT` para manter as datas):
  - O GOW3 pede a lista por data de modificação, decrescente, com o foco no topo. O primeiro item é o
    `BCES00510-AUTOSAVE`, que o próprio jogo atualiza a cada checkpoint ("(Guardar Automaticamente) <área>").
  - **Carregar** mostra essa lista para o jogador escolher. Aqui o runtime não desenha o diálogo do sistema e vale
    o foco inicial pedido pelo jogo (o autosave). `PS3_SAVEDATA_ESCOLHA=<diretório, sufixo da data ou índice>`
    simula outra escolha nos testes; não substitui a escolha pela interface.
  - **Morrer e "Reiniciar a partir do último ponto de verificação"** volta ao checkpoint sem ler arquivo (o jogo
    o guarda na memória).
  - **Salvar manualmente** é no ponto de save (R1), como no console: cria `BCES00510-AAMMDDhhmmss`.
  - O log mostra a lista ordenada, o foco, o diretório carregado (`LOAD dir=`) e o atualizado (`SAVE dir=`).
- **Cache:** o runtime guarda `/dev_hdd1` em `<pasta do jogo>\cache`. Um cache FIOS incompleto, deixado por uma
  execução interrompida, faz o jogo reabrir `cache.idx` sem parar. Para começar limpo, tire essa pasta dali.

## Comandos e variáveis úteis

### Execução

| Variável | Efeito |
|---|---|
| `PS3_RSX=live` | live draw D3D12 no lugar da ponte |
| `PS3_JANELA_FUNDO=1` | a janela não toma o foco; use em medidas |
| `GOW3_PPU_PRIO` | prioridade da thread principal do PPU (padrão: acima do normal) |
| `GOW3_WWS_EXEC=0` | desliga o executor Wws próprio |
| `GOW3_WWS_EXEC_STATS=<s>` | imprime as estatísticas do executor a cada s segundos |

### Medida

- **Quadros reais:** use os flips do GCM (`[flip]`) ou o título da janela com a ponte. O `[fps]` antigo do live
  draw conta cada quadro duas vezes.
- **Velocidade do EDGE:** `SPURS_PM_STATS=10` mais o resumo `us/job(60s)`. O ruído é de ±0,7 us/job por execução.
  Compare sempre execuções alternadas, 12+12.
- **Exatidão de uma mudança no tradutor:**
  1. Grave os jobs com `SPU_JOBCAP`.
  2. Reproduza com `SPU_JOBREPLAY=<captura>,3,0,512` e `SPU_JOBREPLAY_CODE=<ea:tam:...>`.
  3. Compare os DMAs gravados (devem ser iguais) antes de qualquer A/B no jogo.
- **Mudanças de uma lista que não é EDGE** (por exemplo a fusão da folha, na lista 4): meça em ms de SPU por
  quadro por lista. O `us/job` das EDGE não as vê.

### Diagnóstico

Desde 17/11, quatro diagnósticos baratos vêm ligados por padrão: `PS3_RSX_FIFO_DIAG=1`,
`GOW3_FLAGWATCH=70038CEC`, `SPU_FLAGGUARD=70038CEC` e `GOW3_STALL=20`.

- `GOW3_DIAG=0` desliga os quatro.
- Uma variável definida no ambiente ou no `.env` prevalece sobre o padrão.
- O custo foi medido num A/B de 6+6 cenas e ficou dentro do ruído: us/job(60s) -0,22% (EP 0,34).

Os demais diagnósticos começam desligados.

| Variável | O que mostra |
|---|---|
| `PS3_RSX_FIFO_DIAG=1` | no erro de FIFO: os últimos 64 cabeçalhos, os últimos 32 saltos do get, e a memória na origem e no destino |
| `GOW3_STALL=<s>` | quando o jogo para: dump do SPURS, do flag e das listas |
| `SPU_FLAGGUARD=<ea>`, `GOW3_FLAGWATCH=<ea>` | escritas de SPU e do RSX numa palavra (ex.: o flag do RsxSync, 0x70038CEC) |
| `SPURS_FLAG_DBG=1` | cada mudança do workload flag |
| `SPURS_PM_TRACE=1` | cada execução de policy module |
| `SPU_SIG_TRACE_TS=<taskset>` | cada despertar de tarefa |
| `SPU_ATOM_EA=<ea>` | atômicos SPU numa linha |
| `GOW3_FIND=<valores>` | onde um u32 aparece na memória |
| `GOW3_DUMP=<ea:len>` | despejo de uma faixa de memória |
| `GOW3_PROF=<...>` | perfil por amostragem (use o exe e o `.map` do mesmo build) |

Os roteiros de teste usados no desenvolvimento ficam fora do repositório:

- inicializações em série;
- caçadas de travada;
- A/B alternado;
- combate com botões roteirizados.

## Problemas conhecidos

| Problema | Taxa | Estado |
|---|---|---|
| **Desync do FIFO do RSX:** o leitor da FIFO via a primeira palavra nova de uma linha (um salto-para-si trocado) e o resto ainda velho | Antes: 2 em ~340 cenas, depois 2 em 60 (caçada 7); 1 virou travada ("Dead FIFO") | Corrigido em 18/11: o PUT de SPU em memória mapeada para o RSX grava o salto-para-si da linha por último (`spu_put_copy`; `SPU_PUT_HOLE_ORDER=0` desliga). 0 em 40 cenas + 12 do A/B. O diagnóstico automático continua ligado |
| **Primeiro zero do flag do RsxSync perdido** (label 0x51 parado em 1, ~13 s) | 1 em ~400 execuções com o lock; 0 em 200 inicializações seguidas | Aberto, com diagnóstico automático. **Não** é o mecanismo antigo do label 0x51, já corrigido pelo lock |
| **"Patamares" de us/job ~2x**, agrupados no tempo, nos dois executáveis de um A/B (15/11) | não se repetiram | Causa desconhecida. `maquina.ps1` agora registra o estado da máquina durante as medidas |
| O Kratos morre em testes longos sem comando ("Estás morto") | — | É o jogo, não um erro |
| `--passos compilar` falha ("PAROU") se o exe ainda estiver aberto | — | Feche o exe e repita |
| Nome dos saves novos com data errada (`BCES00510-18446743773817603022`) | sempre, no Windows | Corrigido em 18/11: a syscall 145 (`time()`) dava o tempo desde que o PC ligou, não a hora real |
| Lista de saves na ordem alfabética do Windows: "Carregar" abria um save manual em vez do autosave | sempre | Corrigido em 18/11: a lista segue `sortType`/`sortOrder` e o foco (`focusPosition`) pedidos pelo jogo |
| O diálogo de escolha de save do sistema não é desenhado (vale o foco inicial do jogo) | — | Aberto; `PS3_SAVEDATA_ESCOLHA` para testes |
| Validação da instalação fora do ambiente de desenvolvimento; progressão além da Tumba de Ares | — | Na fila |

Nada do que é gerado (código traduzido, executável, logs com endereços do jogo) deve ir para o GitHub. A guarda
do repositório (`native/tools/check_no_game_data.py`) bloqueia.
