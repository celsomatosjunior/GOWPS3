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
- LFQueue resolvida com LLE seletivo da libsre (abaixo): o Edge Zlib descompacta (1.510 blocos em 77 s),
  o jogo cria as threads de áudio, adiciona 12 workloads Wws_Job e abre `CINEMATICS/SMLOGO.M2V`.
- FIFO do RSX fluindo: o jogo grava `put` e o drenador o consome (o `put` alterna entre dois buffers).
  Duas correções no `cellGcmSys` (no `ps3recomp-gow3.patch`): a cópia da tabela de offsets que
  `cellGcmGetOffsetTable` entrega fica viva a cada map/unmap (antes o GOW3 lia uma cópia velha e gravava
  `put = 0xFFFFFFFF`), e um `put` sem IO mapeado não é perseguido (antes a varredura de get..put com 4 GB
  travava a thread da janela, e o Windows a fechava por Application Hang).
- Laço de quadros rodando: ~80 flips/s (`IntroLoaderThread` envia um CLEAR, o marcador de flip 0xFEAD e um
  SEMAPHORE_ACQUIRE por quadro). A tela é preta: só limpezas.
- Tela de boot (``IntroLoaderThread``, ``/INTRO/BOOT0_BCES00510.GTF``): termina sozinha em ~16 s, como no RPCS3
  sem patches (~13 s). Precisou do título correto (PARAM.SFO) e de um save ``BCES00510-USERDATA``.
- **Atenção ao comparar com o RPCS3:** o RPCS3 do usuário tem patches da comunidade ligados para o GOW3
  ("Skip intro", "Skip any videos with X", "Disable MLAA" etc.). Para um gabarito fiel, rodar sem o
  ``config/patch_config.yml`` (guardar uma cópia e restaurar depois), como faz a sessão de 28/10.
- Depois da tela de boot: o jogo registra os tratadores de vblank e de usuário, lê o controle e desenha
  (shaders do jogo, render-to-texture 1280x720). ``ps3recomp-gow3.patch`` traz ``_cellSpursTaskAttribute2Initialize``,
  ``cellSpursCreateTask2``, ``cellSpursGetWorkloadFlag`` e ``_cellSpursWorkloadFlagReceiver`` (receptor 0xFF no init).
  A tela de boot termina aos ~13 s em todas as execuções (o receptor do workload flag usa uma troca atômica;
  com o lock global do lock-line a thread principal travava dentro dele).
- **Parada atual:** depois da tela de boot a thread principal espera em ``func_0028DA14`` (sincronia de buffer
  triplo): o contador de 16 bits do buffer da vez (``S+0x40+i*4``, ``S = *(TOC-0x4C64)``) não zera. As 5 tarefas
  MLAA (taskset2) ficam em WAIT_SIGNAL. O jogo usa o workload flag (receptor wid 11, o PM ``pm_wwsjob``); o
  kernel do HLE agora escala o receptor quando ``flag == 0`` (como o RPCS3), e ``SPURS_FLAG_DBG=1`` mostra as
  condições. Falta achar quem devia zerar aquele contador (provavelmente um job Wws ao fim do quadro).
- Título: `gow3_libsre_lle.cpp` chama `cellGame_init_from_paramsfo` (antes o HLE respondia BLES00000).

## LLE seletivo da libsre (LFQueue)

O ps3recomp não tem `_cellSpursLFQueuePushBody`, e o caminho ANY2ANY do CellSyncLFQueue
(`GetPushPointer2`/`CompletePushPointer2`) também não existe no RPCS3, que roda a libsre original. O
consumidor é o código SPU do jogo, então a fila tem de ser exatamente a da Sony. A libsre do firmware do
usuário é recompilada e só a LFQueue é ligada a ela; o resto do SPURS continua no HLE.

```powershell
# 1. o RPCS3 do usuário converte uma cópia de dev_flash\sys\external\libsre.sprx (gera libsre.prx)
# 2. relocar em 0x30000000 e recompilar
python ps3recomp\tools\lift_prx.py libsre.prx --base 0x30000000 --output <trabalho>\firmware\libsre_lle
#    (converter libsre_imports.json para a lista [{library,nid,stub}] de --hle-stubs)
python ps3recomp\tools\ppu_lifter.py <lle>\libsre_image.bin --raw --base 0x30000000 --toc 0x30039AB0 --functions <lle>\libsre_functions.json --hle-stubs <lle>\libsre_hle_stubs.json --symbol-prefix libsre_ --single-file --header-name libsre_recomp.h --source-name libsre_recomp.cpp --output <lle>\lifted
# 3. compilar com a libsre
python native\game\gow3_build.py ... --spu-dir <trabalho>\spu_dir --lle-libsre <lle>
```

`gow3_libsre_lle.cpp` carrega a imagem relocada de `libsre_image.bin`, ao lado do `.exe`, sem embuti-la
no executável. Ele liga `_cellSpursLFQueueInitialize`, `_cellSpursLFQueuePushBody` e
`_cellSpursLFQueuePopBody` à libsre real e troca só a função de sinal da fila (libsre 0x300127CC). Essa
função procura o taskset nas estruturas internas do SPURS da libsre, que aqui não existem; a versão
nossa entrega o sinal pelo runtime (`spurs_taskset_find` + `spu_taskset_signal_task`). Nada derivado do
firmware vai para o repositório.

## Save

O jogo lê ``BCES00510-USERDATA`` em ``<trabalho>/gamedata/dev_hdd0/home/00000001/savedata/`` (o passo rodar usa
``<trabalho>`` como pasta atual). Sem ele o boot segue o caminho de "primeira vez". O save é do usuário e fica
só no PC dele: copiar do RPCS3 (``dev_hdd0/home/00000001/savedata/BCES00510-USERDATA``).

## O que esperar

O ps3recomp traduz e compila o jogo; fazê-lo rodar é o trabalho que vem depois (como no God of War:
Ascension, que levou cerca de 8 dias do EBOOT ao primeiro nível). A primeira execução deve parar em
alguma biblioteca do firmware ainda não implementada ou num comportamento do runtime; o resumo do
passo `rodar` mostra onde. Isso é o começo, não o fim.

Nada do que é gerado (código traduzido, executável, logs com endereços do jogo) deve ir para o GitHub:
a guarda do repositório (`native/tools/check_no_game_data.py`) bloqueia.
