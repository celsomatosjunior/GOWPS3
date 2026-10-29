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
- **Laço principal fechando quadros (29/10/2026).** A cadeia de cada quadro, achada com o gabarito do
  RPCS3 lido pela sonda GDB (`native/tools/rpcs3_gdb_amostra.py`):
  1. o RSX grava um `GET_REPORT` em memória principal cujo campo de preenchimento (zero) cai em cima do
     workload flag do SPURS (`spurs+0x6C`), e outros três em `0x7003ACB0/C0/D0`, um por buffer;
  2. o flag em zero dispara o workload `Wws_Job/RsxSync` (wid 11), cujo job (código SPU em 0x426B80) sinaliza
     as 5 tarefas MLAA do taskset 0x70041A80;
  3. cada tarefa MLAA desconta 1 de um contador Wws (`0x64AA78/7C/80`, começa em 5; `0x0000FF00` = livre);
  4. com ele livre, os jobs `Wws_Job/EDGE0..2` rodam e zeram o contador do buffer triplo (`S+0x40+i*4`) que
     `func_0028DA14` espera.

  Três correções:
  - o kernel do SPURS travava ao consumir o flag (`vm_write32` dentro do lock-line, que ele mesmo pega);
  - o RSX precisa esperar os SPUs como no hardware: `GCM_SEMA_ACQUIRE=1` e `GCM_PARK_GRACE_MS` longo, que o
    passo `rodar` agora liga por padrão. Sem isso o RSX terminava dois quadros de uma vez, os dois sinais do
    RsxSync se fundiam e duas tarefas MLAA pulavam um quadro;
  - o WAIT_SIGNAL do runtime consome o bit `signalled` no mesmo instante em que o vê, como o kernel do SPURS.

  Resultado, em 3 de 3 execuções de 70 s: o jogo sai da espera, abre `CINEMATICS/SMLOGO.M2V` no `cellVdec`
  (330 unidades decodificadas) e os flips continuam.
- Depois do logo, em execuções de 2–3 min, aparece uma imagem do jogo (nuvens, relevo e raios, com cores
  erradas, rosadas), mas ela fica parada. O jogo segue a ~38 quadros/s (o label 0x480 do RSX sobe ~190 a
  cada 5 s), porém o backend recebe só ~3 desenhos de tela inteira por quadro, sem geometria
  (`PERF=1`: "0k verts"). Pontas a seguir:
  - as tarefas MLAA leem e gravam o quadro na memória principal (EA 0x70A80000, 5120 bytes por linha;
    `SPU_DMA_IMG=315634988` mostra as listas DMA), mas o backend D3D12 não grava nessa memória o que a GPU
    desenha, nem relê o que os SPUs escreveram;
  - os jobs Wws (Edge e os outros) são carregados em tempo de execução e rodam no interpretador SPU.
- **Vídeo (29/10/2026):** `--ffmpeg <pasta>` liga a decodificação real no `cellVdec`. A pasta é um FFmpeg
  LGPL compartilhado da série das DLLs (9.0: `avcodec-63`, `avutil-61`; por exemplo
  `ffmpeg-n9.0-latest-win64-lgpl-shared-9.0` do BtbN). O build passa os cabeçalhos ao CMake e copia as DLLs
  para junto do .exe; nada disso vai para o repositório. Duas correções no `cellVdec`
  (`ps3recomp-gow3.patch`):
  - com a fila de imagens cheia, o AU fica guardado e recebe o AUDONE quando o jogo tira uma imagem; antes o
    runtime respondia BUSY sem AUDONE e o player parava no quadro 18;
  - o "idle drain" fica desligado para o GOW3 (`VDEC_IDLE_DRAIN_MS=0`): o flush dele apagava as referências
    e as AUs seguintes não davam imagem.

  Com isso o `SMLOGO.M2V` decodifica inteiro, e as imagens corretas chegam à memória (0x75200000, RGBA). Na
  tela, porém, ainda não aparecem.
- **Imagem na tela (29/10/2026): o logo da Santa Monica e a abertura da história, com as legendas em
  português.** O que mudou:
  - o passo `rodar` liga o motor "live draw" (`RSX_LIVE_DRAW=1`); `gow3_rsx.cpp` escolhe o motor em tempo de
    execução e o `gow3_build.py` (`use_gow3_rsx`) troca os `rsx_backend_*` do `main.cpp` do modelo;
  - com o fim do código pelas seções executáveis (PR #1 do Arnaldo), a tradução caiu de 1,3 GB para 73 MB de
    C++ (11.482 funções, nenhuma instrução sem tradução), o executável de 119 para 58 MB e a compilação do zero
    para ~3,5 min.

  Numa execução de 120 s: 4.430 flips (~37/s) e 1.314 AUs de vídeo, sem erros. `LD_FRAME_DUMP=<pasta>`
  (com `LD_FRAME_DUMP_EVERY`) salva os quadros do live draw.
- **Menu principal (29/10/2026).** O caminho até ele:
  1. compilar com `--pular-videos`, que aplica numa cópia local do EBOOT (`EBOOT.pular_videos.ELF`) o patch
     "Skip any videos with X button" dos patches da comunidade do RPCS3 (autor: illusion; EBOOT 1.00:
     `be16 0x0026FD18 = 0x901F`, ou seja, `stw r6,0xF5C(r31)` vira `stw r0,0xF5C(r31)`). O build confere a
     instrução original antes de trocar;
  2. rodar apertando X a cada 4 s (`PAD_SCRIPT`), o que fecha o `SMLOGO.M2V` e o `OPENINGCREDITS.M2V`.

  Por volta de 1 min 40 s aparece o menu em português: "Novo Jogo, Carregar, Opções, Tesouros", com
  "X – Seleccionar". O fundo do menu ainda sai quase branco. Sem o patch, a abertura completa leva vários
  minutos, até a cena desenhada em tempo real de Gaia escalando o Olimpo.
- **Fundo do menu (29/10/2026).** O passe final de composição amostra uma LUT de color grading de 32×32
  (`u1[1:0x021AD900]`, uma textura 3D). O live draw só decodifica texturas 2D: no lugar dela entrava a
  textura branca (`SRV_WHITE`), e a imagem estourava. Com o patch "Disable Color Grading (Speedboost)" o
  fundo aparece: o rosto do Kratos, as lâminas e o fogo. **Corrigido no mesmo dia:** o live draw passou a
  decodificar texturas 3D lineares (`decode_guest_texture_3d`, SRV `TEXTURE3D`, unidades 3D declaradas
  `Texture3D` no shader via `vol_mask`, que também entra na chave do PSO e na do cache de shaders). Com isso o
  fundo aparece com a LUT verdadeira, sem o patch. O patch continua disponível como alternativa.
- **Patches de terceiros do RPCS3:**
  - `--patch-rpcs3 "<nome>"` (repetível) aplica patches PPU do `patch.yml` que o RPCS3 do usuário baixa
    (`native/tools/rpcs3_patches.py --patch-yml <rpcs3>\patches\patch.yml --listar` mostra os 9 do GOW3 1.00);
  - o build lê só o arquivo do usuário, e nenhum patch é copiado para o repositório;
  - cada aplicação é registrada no log do passo `elf`, com os bytes antes e depois.
- **Receita reproduzível do menu:**
  1. compilar com `--pular-videos` (o patch "Disable Color Grading" já não é necessário);
  2. rodar com `PAD_SCRIPT` apertando X a cada 4 s entre 15 e 75 s.

  O menu aparece com o fundo, e X leva até "Escolher Dificuldade". Com `cellSpursJoinTask2` implementado (o
  jogo junta as 5 tarefas de um Taskset2 que reinicia a cada quadro; o import faltava) e os toques espaçados
  de 15 s, a dificuldade é aceita e o jogo abre o `OPENINGINT.M2V`, a abertura do Novo Jogo. Atenção ao
  `PAD_SCRIPT`: cada toque dura 40 leituras do controle, uns 6 s a 7 quadros/s; toques mais próximos que isso
  viram um botão segurado, sem aperto novo. Numa execução de 9 min a abertura do Novo Jogo segue com a narração em
  português ("Uma vitória que acabou com a 'Grande Guerra'...", "Nascido das profundezas do submundo"); numa
  execução de 15 min ela termina (close do Kratos desenhado pelo motor), vem a tela de carregamento e o jogo
  abre o `PSDNINT.M2V`, a introdução do Poseidon que abre a primeira fase. Nesse ponto o ritmo cai para ~3
  quadros/s; o próximo alvo é o desempenho (os jobs Wws ainda rodam no interpretador SPU).
- **Plano para o desempenho (jobs Wws nativos).** O EBOOT traz 25 módulos de job SPU, ~2,3 MB de LS no
  total. Cada módulo começa com 4 instruções `ila` (a assinatura), seguidas de `entryOffset` e do tamanho na LS,
  com bss. Não há a marca `C0DEC0DE` que o `extract_jobmods.py` do LBP procura. Passos:
  1. extrair os módulos do EBOOT (tamanho real = até o próximo cabeçalho);
  2. achar o endereço de carga na LS que o PM `pm_wwsjob` usa para o código do job (ver as listas DMA e os pcs
     do microstep do interpretador);
  3. traduzi-los com o `tools/lift_jobmods.py`, um prefixo de símbolo por módulo;
  4. generalizar no `spu_channels.c` o reconhecimento do módulo residente pela assinatura `ila`, que hoje só
     vale para o PM do LBP (`image_id == 2`).

  **Feito (29/10/2026):** o `tools/lift_jobmods.py --engine-elf <EBOOT.ELF> --out <trabalho>\spu_jobs
  --symbol-prefix gow3` acha 5 módulos embutidos no EBOOT, entre eles os dois que o PM carrega em LS 0x4000
  (de 0x4B5C00 e 0x4EFA80), e os traduz sem perda (3 instruções sem suporte num deles). `gow3_build.py
  --spu-jobs <pasta>` os compila no executável; eles se registram como regiões verificadas pelo EA de origem.
  O jogo chega à abertura do Novo Jogo como antes, mas o ritmo não muda: o job do módulo de 0x4B5C00 salta
  para código depois do `code_end` calculado (0x1EC00), alcançado só por salto indireto, e roda dali no
  interpretador. Semear 0x1EC0C (`LBP_JOBMOD_EXTRA_FUNCS`) só levou o fim a 0x1EC28. Próximo passo: registrar
  no runtime todos os pcs em que o interpretador entra e passá-los como sementes ao `lift_jobmods.py`.

  Referência de como o Ascension resolveu: `libs/spu_hle/gowa_drawcmd` e `GOWA_WWS_EXEC`, no ps3kit
  (ver `native/docs/PS3KIT_COMPARACAO.md`). Versões: `gow3-menu-v1` (menu sem fundo),
  `gow3-menu-v2` (fundo com o patch de color grading) e `gow3-menu-v3` (fundo com a LUT 3D verdadeira).
- Diagnóstico novo do live draw:
  - `LD_DRAWLOG=<quadro>,<n>`: o alvo e as texturas de cada desenho;
  - `LD_DRAW_DUMP_FROM=<quadro>`;
  - `LD_BLIT_LOG=1`: as cópias NV3089 feitas na GPU;
  - `LD_BLIT_READBACK=1`: copia para a memória do jogo o que a GPU copiou para a memória principal;
  - `PS3_JANELA_FUNDO=1`: a janela abre minimizada e sem roubar o foco, para testes sem ninguém no PC.

  O live draw passou a decodificar texturas D8R8G8B8 (0x9E).
- Comparação com o ps3kit do Arnaldo: `native/docs/PS3KIT_COMPARACAO.md`.
- Controle sem ninguém no PC: `PAD_SCRIPT="<s>:<máscara>,..."` aperta botões em segundos dados (START 0x0008,
  CROSS 0x4000, CIRCLE 0x2000, DOWN 0x0040, UP 0x0010), e `PAD_FILE=<arquivo>` aperta o que for escrito no
  arquivo. Os dois são do `cellPad` do ps3recomp.

## Compilar sobre o ps3kit (ramo `gow3`)

O ps3kit (`arnaldolima1/ps3kit`, privado) tem um ramo `gow3`, tirado do `master`, e cinco ramos de correção
com PR para ele. Cada ramo traz uma correção que o ps3kit não tinha:

| Ramo | O que traz |
|---|---|
| `gow3-spurs-workload-flag` | workload flag, receptor e disparo no kernel |
| `gow3-wait-signal-take` | WAIT_SIGNAL consome o sinal ao vê-lo |
| `gow3-spu-workloads-code-end` | `--code-end` no `build_spu_workloads.py` |
| `gow3-spurs-taskset-find` | taskset de um (spurs, wid, task), para o LLE da LFQueue |
| `gow3-template-live-draw` | `RSX_LIVE_DRAW=1` no `main.cpp` do modelo |

Sobre o ps3kit não se aplica nenhum dos nossos `.patch`: o `ppu_lifter.py` dele já tem `--toc`, e as
correções vão nos ramos. Para testar tudo junto, junte os cinco ramos num ramo local (aqui,
`gow3-integracao`) e passe o checkout como `--ps3recomp`. O `gow3_build.py` reconhece o modelo do ps3kit: não
mexe no `main.cpp` se ele já escolhe o live draw, e define também `GCM_PARK_WAIT_MS`, o nome do ps3kit para a
espera do park.

```powershell
python <ps3kit>\tools\build_spu_workloads.py --input <trabalho>\EBOOT.ELF --lifted <trabalho>\spu --out <trabalho>\spu\spu_workloads.c --constructor --code-end spu_83b0bc054de1b6ecba6f7dfa763ea2f2bcf2535183c567607bedbeeeb037ed9a=0xAA80
python native\game\lift_pm.py <trabalho>\EBOOT.ELF --ps3recomp <ps3kit> --ea 0x49FF80 --size 12032 --fp 0x7AE3FE49074DF128 --name pm_wwsjob --out <trabalho>\spu_pm
python native\game\monta_spu_dir.py --programas <trabalho>\spu --pms <trabalho>\spu_pm --out <trabalho>\spu_dir
# libsre: lift_prx.py e ppu_lifter.py --raw do ps3kit, como na seção do LLE abaixo
python native\game\gow3_build.py --ps3recomp <ps3kit> --trabalho <trabalho> --spu-dir <trabalho>\spu_dir --lle-libsre <lle> --ffmpeg <ffmpeg> ...
```

**Resultado (29/10/2026):**
- as ferramentas do ps3kit traduzem tudo: os 8 programas SPU registrados (com `--code-end`), o PM e a
  libsre, e 11.482 funções PPU sem nenhuma instrução sem tradução;
- o executável compila (81 MB) e roda 120 s sem erros nem NIDs faltando, com o live draw ligado pelo modelo e
  a LFQueue na libsre real (os sinais chegam à tarefa Edge Zlib);
- **ainda não chega ao logo**. Os flips param aos ~17 s, o receptor do workload flag não é chamado e o
  `SMLOGO.M2V` é reaberto várias vezes. Há também um desvio do policy module Wws para LS 0x9D4 (o serviço
  "select workload" do kernel fica em 0x9D0), que na v0.18 não acontece. O ponto provável é a resposta
  nova do poll do ps3kit (`spu_branch_service`) ou o microstep do interpretador. Na v0.18 o mesmo jogo
  mostra o logo e a abertura, então a v0.18 continua sendo a base do dia a dia.
- **Com o backend D3D12 antigo (sem live draw) o quadro passava pela memória do PS3 e não aparecia:** Por quadro, o jogo:
  1. desenha no buffer de tela (local 0x0 / 0x384000 / 0x708000);
  2. copia-o com o NV3089 para a memória principal (0x70A80000), onde as tarefas MLAA filtram;
  3. compõe a tela a partir de uma textura em 0xC1194000.

  O backend D3D12 desenha na GPU do PC e não grava o resultado na memória do PS3, então essas cópias movem
  zeros. Falta ler os alvos de render de volta da GPU antes das cópias, e subir de novo as texturas que os
  SPUs reescrevem.
- Diagnóstico: `SPURS_PM_TRACE=1` (cada execução de policy module), `SPURS_FLAG_DBG=1` (mudanças do workload
  flag), `SPU_SIG_TRACE_TS=<taskset>` (cada despertar de tarefa), `SPU_ATOM_EA=<ea>` (atômicos SPU numa linha,
  com a thread), e no `gow3_diag.cpp` `GOW3_FIND=<valores>` (onde um u32 aparece na memória) e
  `GOW3_DUMP=<ea:len>`.
- Título: `gow3_libsre_lle.cpp` chama `cellGame_init_from_paramsfo` (antes o HLE respondia BLES00000).

## Ponto de retomada (atualizado a cada pausa)

Estado em 29/10/2026, 20h55: o Novo Jogo chega ao PSDNINT.M2V (fase do Poseidon) em 330 s, sem SPU parado.
Pasta de trabalho principal: `Projetos\GOW3_trabalho`.

**Feito em 29/10 à noite:**
- Os 24 módulos de job Wws do EBOOT são nativos: `lift_jobmods.py --engine-elf ... --base-zero` (19 deles têm
  base 0 no cabeçalho e rodam em LS 0x4000, confirmado pelo cabeçalho em 0x4000 no `SPU_INTERP_PCLOG`).
- Sementes por módulo: `native/tools/jobmod_seeds.py --trabalho <pasta> --manifesto <manifesto com --base-zero>
  pcs1.txt pcs2.txt` divide os pcs do interpretador pelo módulo residente e imprime os `--module-funcs`. Duas
  rodadas levaram de 504 para 407 pcs no interpretador; o que resta é quase todo do `jobmod_baf5d88ebb3b`:
  cópias de 3 rotinas curtas (EA 0x52B720..0x52B860, logo antes do módulo) postas pelo job em vários endereços
  de LS. Traduzir por endereço não resolve; ficou para depois (não é o gargalo, ver perfil).
- Código SPU com SIMD do host (`--spu-simd avx2`, padrão): fase de ~1,7 q/s para ~3 q/s (picos de 4,2).
- `GOW3_PROF=<início>,<segundos>` (perfil por amostragem do RIP). Resolver com o `.map` do build.
- Atenção: sem `--lle-libsre` o título vira BLES00000 e o jogo não passa da inicialização; o `gow3_build.py`
  agora usa `<trabalho>\firmware\libsre_lle` sozinho quando existe.

**Perfil da fase (AVX2, 260 a 310 s):** a thread principal do PPU fica ~81% fora do executável (esperando); uma
thread SPU fica ~80% ocupada (`jobmod_14561cbb02eb` func 0x10E20, `mfc_for`, `spu_coh_notify_write`); as
outras SPUs ficam quase paradas.

**Próxima ação exata:** descobrir o que a thread principal espera (GOW3_WATCHDOG na fase: LRs do PS3) e se os
jobs da fila ficam numa SPU só (contar por thread host os jobs/workloads despachados); se ficam, ver por que o
SPURS do HLE não espalha os jobs pelas outras SPUs.

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
