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

**Fase com imagem (29/10, 21h40):** os volumes 64x32 FP16 (formato 0xBA, linear, 3D) da fase não eram
decodificados e caíam no SRV branco, e a tela inteira ficava de uma cor só. Com o `decode_guest_texture_3d` em
R16G16B16A16_FLOAT a fase aparece (Kratos em combate, com o HUD), `decodefail=0`, e os flips subiram para ~14/s
no mesmo teste de 330 s. Versão preservada: tag `gow3-fase-v1` e `Projetos\versoes\gow3-fase-v1\rodar_fase.ps1`.

**Perfil da fase (AVX2, antes da correção dos volumes):** a thread principal do PPU fica ~81% esperando em
`func_0028DA14` (o buffer triplo que os jobs EDGE liberam); uma thread SPU fica ~80% ocupada no código do
`jobmod_14561cbb02eb` (o resto: `spu_coh_notify_write`, despacho indireto). Cada workload Wws tem
maxContention=1, então a fila de um job chain é serial, como no PS3.

**Controle na fase:** o teste A/B (mesma receita com e sem `PAD_STICK` de 295 a 325 s) não decide: as duas
execuções já divergem antes do comando (o jogo não é determinístico entre execuções), então os quadros não isolam
o efeito do analógico. O controle chega ao jogo (os menus respondem ao X do `PAD_SCRIPT`).

**30/10 à tarde:** perfil da fase com imagem igual ao anterior: a SPU da frente da fila fica no código de
`jobmod_14561cbb02eb` (função 0x10E20: leituras de LS, fm/fma e shufb em sequência, transformação de vértices).
O passo `rodar` liga `SPU_MFC_LOOKUP_CACHE=1` (tirou o `mfc_for` do perfil, sem regressão). O próximo ganho grande
de SPU pede mudar o tradutor para manter os registradores SPU em variáveis locais em vez de `ctx->gpr` na
memória (trabalho maior).

**Controle (31/10):** o Celso testou; a ~5 quadros/s não dá para jogar. O teste do controle fica para quando a
fase estiver mais rápida.

**02/11 (trabalho autônomo; commits só locais desde 01/11, à espera do envio de terça):**
- Registradores SPU em variáveis locais: `ps3recomp/tools/spu_reg_locals.py` (`spu_lifter.py --reg-locals` e
  `lift_jobmods.py --reg-locals`, desligado por padrão no ps3recomp, com `tools/test_spu_reg_locals.py`). O
  `gow3_build.py` aplica a reescrita às cópias dos módulos de job no projeto (`--spu-reg-locais`, padrão ligado). Só
  entram funções de até 600 linhas e 8 escapes. Ganho pequeno sozinho (a 0x10E20 passou de 7,8% para 6,6% das amostras).
- Armadilha: no clang-cl o `-Wall` do modelo vale `-Weverything`, e a análise dos avisos levava mais de 30 min
  por módulo. As fontes SPU agora compilam com `-w`; o build todo leva ~3 min.
- **Ponto flutuante aproximado** (`--spu-float aprox`, padrão; `SPU_FLOAT_APPROX` no `spu_helpers.h`): fa/fs/fm/fma/
  fms/fnms viram operações nativas do host, como o "approximate xfloat" padrão do RPCS3. Valores com expoente 255
  (máscaras 0xFFFFFFFF, faixa estendida) saturam em ±FLT_MAX, e zeros/denormais viram +0. Sem a saturação a tela
  da fase ficava amarela (NaN). Fase: média de **~4,6 para ~6,1-6,4 quadros/s** (picos de 15-18), imagem correta,
  sem "identical transfers", `decodefail=0`. Versão preservada: tag `gow3-fase-v2` e `Projetos\versoes\gow3-fase-v2`.
  `--spu-float exato` volta à emulação bit a bit.
- SPURS: a escolha do workload segue o peso do kernel (prioridade por SPU, `SPURS_PRIO_SELECT=0` desliga);
  `SPURS_PM_STATS=<s>` imprime por workload o tempo, as rodadas e as SPUs; `SPURS_IDLE_BACKOFF=0` piora (5,25 q/s).
  Retrato da fase: em 10 s os workloads Wws somam ~22 s de SPU (wids 8, 9 e 10 ~2,8 s cada nas SPUs 0-2; o wid 6
  ~4 s numa instância SPURS de uma SPU só; os wids 3 e 4 ~3 s). Não há SPU livre fácil de aproveitar: o ganho
  está no código traduzido.
- Perfil (`GOW3_PROF` agora imprime até 4000 posições por thread): a SPU mais ocupada passa ~49% no jobmod_14561,
  ~18% no runtime (`spu_lifted_lookup`, `spu_indirect_branch`, `spu_coh_notify_write`, `spu_drain_call`). A thread
  principal do PPU e a do RSX ficam ~20% ocupadas.

- **Onde o quadro espera (02/11, manhã):** com `PS3_FTRACE=250:10:<arquivo>` e `ps3recomp/tools/ftrace_report.py`,
  a thread principal passa ~257 ms de cada quadro de ~326 ms em usleep dentro de `func_0028DA14`: espera o halfword
  em 0x649EC8 + 4*slot zerar, slot = (quadro+2) % 3. A PPU o põe em 1 ao enviar a lista (`func_0028E178`) e uma SPU
  o zera por operação atômica quando a lista termina. As três listas são os workloads **Wws_Job/EDGE0, EDGE1 e EDGE2**
  (wids 8, 9 e 10; nomes no log: `AddWorkloadWA ... name=`). Cada EDGE fica só ~28% ocupado, ou seja, as listas mais
  esperam do que calculam. Mudar o código SPU (shufb, `--merge-chunks` em `spu_jobs_mc`) não mexe nos quadros/s,
  e o A/B do `GCM_SEMA_SPIN` também não (~6,3 q/s nos dois). Workloads: 0 CollisL, 1 General, 2 SysMisc,
  3 ModelServer, 4 ModelServerPrep, 5 BatchJobList, 6 BrBDblBufWrkld, 7 RenderJobs, 11 RsxSync.
- Execuções às vezes entram, depois de ~280 s, num estado a ~115-140 q/s (outro estado do jogo, sem ninguém
  jogando); o `fps_fase2.py` da pasta de trabalho descarta trechos acima de 40 q/s.

- **A cadeia do quadro, medida (02/11, fim da manhã):**
  - `GCM_DRAIN_MS=1` (o `gow3_build.py` agora liga): a thread de apresentação olha a FIFO a cada 1 ms em vez de
    4 ms. Fase ~6,1 -> **~7,2 q/s** (A/B de três execuções). Versão `gow3-fase-v3` (tag e `Projetos\versoes`).
  - `GCM_DRAIN_STATS=10`: o andador do RSX está **sempre estacionado** num auto-JUMP, o buraco que o Edge
    reserva na FIFO e um job SPU preenche. Com `PS3_FTRACE` cada buraco vira um trecho "acquire wait" (a=get).
    Com `GCM_DRAIN_MS=0` um buraco dura ~86 us (mediana) e em 65% desse tempo uma lista EDGE está rodando.
  - O quadro é, portanto, (jobs EDGE por quadro) x (custo de cada rodada do policy module Wws). As listas EDGE
    do quadro N só começam depois que o RSX alcança o flip do quadro N-1 (ver o desenho por workload em
    `GOW3_trabalho\scratch\ft_wid.py <trace> <início ms> <duração ms> <ms por coluna>`).
  - Quem marca e libera o slot do quadro: `SPU_ATOMIC_WATCH=649EC8` (RenderJobs põe 1, EDGEn zera).
  - O que o EDGE lê sem parar: `SPU_GET_HIST=<wid>` (GETLLAR na própria lista e em 0x72FC2280, que uma SPU
    reescreve por atômica a cada ~0,3 ms: `GOW3_WATCH_EA` agora registra só a linha de 128 bytes, com o RIP).
  - Não ajudaram (medidos): `SPURS_PASS_US` (100 us: 5,5 q/s; 250: 3,7), `SPURS_IDLE_BACKOFF` 6/8 (igual),
    `GCM_SEMA_SPIN` (igual), `LD_FLUSH_STATS` mostra os flushes da GPU em ~4% do tempo.

- **Código dos jobs mais rápido (02/11, tarde):** o perfil da SPU que roda as EDGE mostra 57% no código dos
  jobs (quase tudo `jobmod_14561`, a 0x10E20 sozinha ~10%) e ~15% no policy module e no runtime. Então:
  - float aproximado com caminho rápido: a operação direto nos operandos e só um resultado Inf/NaN vai ao
    caminho saturado (~8 instruções por fa/fm/fma em vez de 17-23): mediana 7,0 -> 7,3 q/s;
  - `SPU_LS_NODIAG` (padrão no `gow3_build.py`; `--spu-ls-diag` volta): sem o teste das sondas de LS em cada
    lqd/stqd: **mediana 8,6 q/s, média ~8,9**. Versão `gow3-fase-v4` (tag e `Projetos\versoes`);
  - `--spu-opt=-O3;-march=znver3`: sem efeito.

  - `GCM_DRAIN_MS=0` passou a ser o padrão (a thread de apresentação só cede a CPU): ~8,3 -> ~8,8 q/s.
    Versão `gow3-fase-v5`. Neutros: LS por ponteiro local (`SPU_LSR/SPU_LSW`), `--merge-chunks` (`spu_jobs_mc`),
    atalho do shufb sem seletores especiais, hash de texturas em quatro faixas.
  - Cada buraco do Edge: ~65% do tempo o job EDGE roda na SPU, ~35% o RSX processa os comandos até o próximo
    buraco (no RSX: `texture_content_hash`, decodificação de vértices na CPU `rsx_vertex_*`, `sink_end_impl`).

  - A thread de apresentação passava 64% em `win32u` (PeekMessage a cada volta do giro); agora as mensagens da
    janela saem no máximo a cada ~16 ms. Com isso a thread do RSX fica ~70% só cedendo a CPU, esperando os
    buracos do Edge: o caminho crítico é a SPU das listas EDGE (~73% ocupada; 57% no código dos jobs, ~7% no
    despacho indireto `spu_indirect_branch`/`spu_lifted_lookup`). Fase: **~8,8-9,2 q/s** (antes de hoje: ~4,6).
  - No laço da 0x10E20 (~990 instruções x86 por ~120 SPU) sobram: derramamento de registradores (~20%),
    testes de Inf/NaN do float aproximado (~6%), inversão de bytes da LS (~4%).
  - O estado de 115-140 q/s que algumas execuções alcançam depois de ~280 s deve ser a tela de morte: sem
    ninguém jogando, o Kratos apanha cercado e com pouca vida (quadros de `LD_FRAME_DUMP` no fim da fase).

**03/11 (terça; envio semanal feito aos dois repositórios às 8h50):**
- **Fase de pé:** a cena 3D saía de ponta-cabeça sob o HUD certo (notado pelo Celso). O live draw não passava ao
  shader a origem do `SET_SHADER_WINDOW` (fp_alpha.y/.z do `_rsx_wpos`), e os passos de tela cheia que montam a UV
  a partir do WPOS espelhavam a cena. Corrigido; versão `gow3-fase-v6` (tag e `Projetos\versoes\gow3-fase-v6`).
- Atalho no `spu_indirect_branch` para saltos de policy module dentro de código de job residente
  (`SPU_IB_RESIDENT_FAST=0` desliga): neutro a levemente positivo (~8,6 -> ~9,9 q/s em duas execuções, no ruído).
- Medidos e descartados como caminho crítico: hash de textura (`RSX_NO_TEX_REFRESH=1`: 8,8 q/s), a CPU por desenho
  do live draw (`LD_SPIN_US=10`, +23 ms por quadro no RSX: 9,0 q/s, igual) e o `Sleep(1)` das sondagens de DMA
  (`SPU_DMA_REPEAT_BACKOFF_MS` enorme: igual). **O caminho crítico é o lado das SPUs.**
- Perfil da SPU das EDGE (`prof_cat.py` no scratchpad da sessão, por categoria): 48% código dos jobs, 23% runtime
  (despacho ~7%, canais/DMA ~6%, coerência ~2%), 23% esperando (ntdll), 5,5% memcpy. O laço da 0x10E20 tem >50
  vetores vivos para 16 registradores AVX2: o derramamento é inevitável nesta CPU (sem AVX-512).
- O estado de ~115 q/s depois de ~280 s é a tela de morte ("Estás morto"), confirmado por `LD_FRAME_DUMP`.

- **Retorno direto do policy module (`SPURS_PM_STICKY=64`, padrão no `gow3_build.py`): ~9 -> ~12,3 q/s.** O
  `PS3_FTRACE` mostrou a SPU 0 (a das listas EDGE) com ~29 mil execuções de ~52 us em 3 s e intervalos de ~19 us
  entre elas (25% do tempo): cada execução devolvia a SPU à thread do kernel do SPURS, que a devolvia ao mesmo
  workload (duas acordadas de thread). Agora o worker repete o workload quando o kernel o escolheria (ver
  `spurs_pm_sticky_take` no `cellSpurs.c`). A SPU 0 passou a 90% ocupada. Versão `gow3-fase-v7`.
- O policy module Wws reenvia o código do job a cada job (`SPU_OVL_STATS=10`: ~80 mil GETs e ~1,2 GB/s, ~20 mil
  verificações de ~58 KB). `SPU_OVL_INCREMENTAL=1` compara só o trecho reenviado: corta as verificações a ~1/3,
  mas a fase não muda; ficou desligado.
- Perfil da SPU 0 com o retorno direto: 65% código dos jobs, 21% runtime, 9% ntdll, 5% memcpy.

- **Estabilidade (15 min, 03/11):** X a cada 20 s depois de 240 s (ataca na fase, e na tela de morte escolhe
  "Reiniciar a partir do último ponto de verificação"): a fase recarregou duas vezes (PSDNINT.M2V aberto 3 vezes),
  nenhum erro, nenhuma SPU parada; memória estável (~1,1 GB em uso, privada 2,2-2,9 GB, sem crescer), 55-58
  threads; 10-13 q/s na fase. O áudio sai pelo WASAPI em tempo real (`AUDIO_RATE=1`: 187,5 blocos/s, sem
  perdas; `AUDIO_PEAK=1`: picos de até 0,4).
- `SPURS_PM_STICKY=1024` em vez de 64: igual (11,9-13,7 q/s, no ruído).

- **Float aproximado sem chamada fria (03/11, tarde): ~12,0 -> ~13,4-14,9 q/s de mediana** (médias 13,9 e 16,6 em
  duas execuções; antes 12,8). O caminho saturado de cada fa/fm/fma era uma função fora de linha (`noinline, cold`),
  e no Win64 um u128 vai por ponteiro: cada operação de float num laço era um ponto de chamada, e os vetores vivos
  através dela só podiam ficar em xmm6-15. Agora o caminho saturado fica em linha num bloco frio
  (`SPU__AX_SATFN` no `spu_helpers.h`; `-DSPU_AX_SAT_CALL=1` volta à chamada). Resultados idênticos bit a bit
  (2 milhões de operações aleatórias com expoente 255, máscaras e denormais). As leituras de LS já eram
  `vmovdqu` + `vpshufb` (conferido no assembly). Versão `gow3-fase-v8` (tag e `Projetos\versoes\gow3-fase-v8`).
- `GOW3_PROF` agora desenrola a pilha das amostras fora do exe e imprime `chamador 0x...` (quem no exe levou a
  thread ao ntdll). Na SPU das EDGE: ~21% esperando trabalho no `spurs_pm_worker` e ~7% no `Sleep`/
  `SwitchToThread` do `mfc_submit` (sondagem por DMA repetido de uma palavra que outro agente escreve). A SPU 0
  deixou de estar saturada: o resto do quadro (PPU, RSX, outras listas) volta a pesar.

- **Estimativas nativas (03/11, fim da tarde):** com `SPU_FLOAT_APPROX`, `frest`/`frsqest` viram 1/x e 1/sqrt|x| do
  host e o `fi` devolve a estimativa, como no "approximate xfloat" do RPCS3 (a tabela exata custava ~35 instruções e o
  `fi` ~20; `-DSPU_EST_EXACT` volta à tabela). O `shufb` perdeu duas instruções (índice e máscara do "vem de b" sem
  and/cmpeq). A/B de duas execuções cada, com `edge_ms.py` (pasta de trabalho: ms de SPU das listas EDGE por
  quadro, do `SPURS_PM_STATS=10`): **~72 ms (nativas) contra ~74,5 ms (exatas)**, mediana 13,4-13,7 contra
  11,9-12,9 q/s. Imagem conferida por `LD_FRAME_DUMP`.
- `SPU_OVL_INCREMENTAL=1` agora funciona e é padrão no `rodar`: o reenvio do código com o cabeçalho do módulo
  registrava o slot de novo como pendente e desfazia a verificação incremental; agora um reenvio idêntico do
  mesmo módulo no mesmo lugar mantém o slot verificado. Verificações completas: ~7 mil -> ~700 por segundo.
- **Retrato da fase agora:** as listas EDGE (wids 8-10) somam ~9,75 s de SPU a cada 10 s, ou seja uma SPU inteira,
  e o quadro é ~1000 / (ms das EDGE por quadro). O jogo registra cada lista com maxContention=1 e nunca muda
  (como no PS3): não dá para dividir uma lista entre SPUs. As SPUs 1-4 ficam quase paradas.
- Por dentro da SPU das EDGE: ~63% código dos jobs (espalhado: a 0x10E20 ~9%, dezenas de funções de 1-3%), ~22%
  runtime (`spu_indirect_branch` ~5%, `spu_coh_notify_write` ~3%, `spu_lifted_lookup_full` ~2%, `spu_drain_call`
  ~2%), ~7% memcpy (o reenvio do código, ~1,5 GB/s) e ~7% ntdll (sondagem por DMA repetido, `Sleep`/
  `SwitchToThread` do `mfc_submit`).

- **Sondagens (`SPU_DMA_POLL_STATS=1`, tempo de parede por thread e por workload com o contador de desempenho):** as
  listas EDGE (wids 8-10) não sondam nada; quem espera por DMA repetido são General, ModelServer, MSPrep e
  RenderJobs nas outras SPUs (semáforos que o RSX libera em 0x7010E4xx/0x7012E5xx, via `gcm_3d_method`; o PPU os
  reinicia com 0xFFFFFFFF). A SPU das EDGE só calcula.
- Assembly do laço da 0x10E20: cada fa/fm/fma termina num teste e desvio (o caminho saturado), o que faz de cada
  operação de float um bloco básico. `-mllvm -pre-RA-sched=list-burr` tira só ~5% dos derramamentos. A CPU
  (Ryzen 9 5950X, Zen 3) não tem AVX-512. O custo das fronteiras entre funções (`ctx->gpr`) é ~5-8%.
- Testado e descartado: float aproximado **sem desvio** (o resultado saturado direto, NaN -> 0, sem refazer a
  operação com os operandos saturados). O laço executa quase as mesmas instruções (~900), mas as EDGE subiram para
  **~85 ms por quadro** (antes ~72; 11-12 q/s) em duas execuções. Código removido.

- **A cadeia EDGE é serial por natureza:** no rastreio de 3 s há sempre exatamente uma lista EDGE ativa (2952 ms
  de 3000) e duas nunca se sobrepõem; a lista do quadro seguinte só começa quando a anterior termina.
- **Medir velocidade por µs por job, não por fps:** o `edge_ms.py` agora imprime ms por quadro, jobs por quadro e
  µs por job. As execuções variam entre ~1150 e ~1500 jobs EDGE por quadro conforme a cena da luta (por isso o fps
  oscila entre 13 e 16 q/s na mesma versão); o µs por job (~50-56) é o que mede o código.
- **Retorno direto sem a trava da instância:** o `spurs_pm_worker` repete o workload sem pegar `si->lock`, que a
  thread do kernel segura durante passadas inteiras (o perfil mostrava a SPU das EDGE ~8% no ntdll, chamada pelo
  `spurs_pm_worker`). µs por job: ~54,8 -> ~52,9 (quatro execuções contra duas).
- Afinidade (script `rodar_af.ps1` do scratchpad): só o CCD 0 (0xFFFF) não ajuda (52,8/56,3 µs por job); um
  processador lógico por núcleo (0x55555555) dá ~51,7, perto do ruído.
- `GOW3_PROF` agora guarda os handles das threads e roda com prioridade alta: ~400 amostras/s por thread (eram ~15).

- **PGO do código SPU** (`gow3_build.py --spu-pgo gerar`, rodar com `GOW3_PGO=230,290` e
  `LLVM_PROFILE_FILE=<trabalho>\pgo\spu-%p.profraw`, `llvm-profdata merge -o <trabalho>\pgo\spu.profdata`, depois
  `--spu-pgo <trabalho>\pgo\spu.profdata`): 52,1 e 50,3 µs por job contra ~52,9, no máximo ~3%. Fica opcional (o
  perfil envelhece a cada mudança do tradutor, e o .profdata fica só na pasta de trabalho).
- `spu_drain_call` em linha no caso comum (o chamado voltou ao endereço de retorno sem salto pendente): neutro
  (51,5/54,0 µs por job), mantido por ser simples.

- **O código dos jobs é limitado pela latência das cadeias de fma** (classificador de instruções amostradas,
  `insn_cls.py` do scratchpad: ~20% derramamento na pilha, ~17% desvios, ~15% testes de saturação do float, só ~2%
  as próprias operações de float). Por isso o float "sem desvio" piorou (64 µs por job: mais instruções
  dependentes depois de cada operação), e tirar do caminho crítico o zeramento de denormais/-0 ajudou:
  **`SPU_AX_NOFLUSH=1` (padrão do build no aproximado) com `SPU_FTZ=1` (padrão do `rodar`: FTZ/DAZ nas threads
  de SPU)**: 50,1/50,6/52,8 µs por job (média 51,2, contra ~52,9), imagem conferida. Única diferença para o SPU:
  um resultado zero pode sair -0.
- Ruído: o µs por job varia ±1,5 entre execuções (o tipo de job também muda com a cena); para efeitos de poucos
  por cento, três execuções por variante.

- **Banco de testes do laço quente** (scratchpad `bench\`, só local: código traduzido do jogo): a 0x10E20 isolada
  sobre dados sintéticos, mesmas opções do build, ±0,5% entre medições. 57 ns por iteração no esquema de teste e
  desvio; **26,9 ns sem nenhum tratamento** de Inf/NaN; 29,6 ns só limitando a saída (maxps/minps); 44 ns na
  versão "sem desvio" antiga. Com poucas iterações por chamada (o caso do jogo) a entrada e a saída da função
  (~75 cargas e ~60 gravações de `ctx->gpr`, ~70 ns) dominam.
- **O caminho saturado dispara ~700 mil vezes por segundo no jogo** (`-DSPU_AX_STATS=1`): a semântica dele importa.
  Por isso o NaN -> 0 deixou os jobs mais lentos (mais trabalho por job).
- **`SPU_AX_CLAMP=1`** (padrão do build com registradores locais): sem teste e desvio; a saída de fa/fs/fm/fma/fms/
  fnms é limitada a ±FLT_MAX e um operando só é limitado onde `ps3recomp/tools/spu_float_inputs.py` o marcou com
  `SPU_AXI()` (não veio de outra dessas operações no mesmo trecho reto). Mesma semântica do caminho saturado,
  menos um NaN positivo como operando (vira -FLT_MAX). Laço do banco: 57 -> 36 ns por iteração; no jogo 51,8 µs
  por job (neutro sozinho: o custo por chamada domina).
- **Fusão do trecho seguinte** (`ps3recomp/tools/spu_inline_fallthrough.py`, padrão; `--sem-fundir` desliga): uma
  função que termina num `SPU_DIRECT` para o trecho logo depois dela (preâmbulo -> laço) recebe o corpo dele, até 4
  trechos e 500 linhas; 2099 fusões no módulo quente, 910 funções com registradores locais (eram 860). Exe de 70
  para 93 MB. 51,2/50,3/51,0 µs por job (média 50,8).
- A SPU das EDGE fica ~7% bloqueada em `ZwWaitForAlertByThreadId` entre execuções (o `ntdll_cat.py` do scratchpad
  resolve as amostras do ntdll pela exportação); é a devolução ao kernel a cada 64 repetições. Isso não entra no µs
  por job; pelo `SPURS_PM_STATS` a cadeia EDGE ocupa ~97,5% do tempo de parede.

- **Canais de parâmetro do MFC em linha** (`SPU_INLINE_WRCH=1`, padrão do build nas fontes SPU): LSA/EAH/EAL/Size/
  TagID/WrTagMask gravados direto no contexto, sem o despachante `spu_wrch`. 49,6/49,4/50,5 µs por job (média 49,8,
  contra 50,8). No dia: ~54,8 -> ~49,8 µs por job (-9%).
- `GOW3_PROF` imprime todas as posições (ordenadas), não só as 4000 primeiras.

- `shufb` sem desvio para os seletores especiais (os dois pshufb já zeram os bytes com o bit 7; 110/111 viram um
  OR): o perfil mostrava 8% da função mais quente no caminho especial. Banco: 6-12% mais rápido com controles que
  têm bytes especiais; jogo 50,9/50,4/49,9 µs por job (no ruído). `test_spu_shufb.c` ok.

- Fusão mais funda (`--fundir-trechos 8 --fundir-linhas 1200`): 50,6/50,2/48,5 µs por job, igual à padrão (4/500), com
  exe de 103 MB. Fica a padrão.
- **Patamar:** ~50 µs por job EDGE. O que resta é estrutural: a entrada/saída de cada função traduzida (cargas e
  gravações de `ctx->gpr`, ~40% das amostras do código dos jobs entre derramamentos e movimentações), o despacho
  indireto (~6%) e o resto do runtime por job (~15%).

- **Estabilidade (04/11, 0h55, build da v10):** 15 min com X a cada 20 s depois de 240 s: nenhuma falha, memória
  plana (~1,1 GB em uso, privada ~2,5 GB, 55-59 threads), fase a 10,6-16 q/s em ciclos de 20 s (a luta), média 13,7;
  o Kratos durou até o fim. Versão **`gow3-fase-v10`** (tag e `Projetos\versoes\gow3-fase-v10\rodar_fase.ps1`).
- Candidato menor: o micro-interpretador dos trechos de salvar/restaurar registradores que o tratador de
  interrupção do Wws gera na LS (`spu_smc_microstep`, ~3% da SPU das EDGE dentro do `spu_indirect_branch`):
  guardar o trecho já decodificado enquanto os bytes não mudam.

- **Métrica melhor:** `edge_ms.py` agora imprime também `us/job(60s)`, a média dos blocos de ~10-70 s depois de a fase
  abrir; entre execuções da mesma versão ela varia ~±0,5 (o µs por job de toda a fase, ~±1,5).
- **Retorno direto sem limite** (`SPURS_PM_STICKY=100000`, padrão do `rodar`; era 64): a cada devolução ao kernel a
  cadeia EDGE podia ir para outra thread/núcleo, com a LS e o código frios no cache. us/job(60s) 48,2/47,9/48,0 contra
  ~49,2-50,2. Versão **`gow3-fase-v11`** (mesmo exe da v10, roteiro com o novo valor).
- Testado e revertido: guardar decodificados os trechos de salvar/restaurar do tratador de interrupção
  (`spu_smc_microstep`): us/job(60s) 48,5-49,7, sem ganho.

- **Threads de SPU fixas em núcleos** (`SPURS_PM_AFFINITY=1`, padrão do `rodar`; um processador lógico por núcleo
  físico, do segundo núcleo em diante): us/job(60s) 47,6/47,1/47,8 (contra ~48,0), medianas 14,7-15,5 q/s.

- **Reenvio idêntico do código sem cópia** (`spu_overlay_get_unchanged`, com `SPU_OVL_INCREMENTAL=1`): um GET que
  traz para um módulo verificado os mesmos bytes que já estão na LS não copia nem refaz a verificação (uma
  comparação em vez de cópia + comparação). Descartado antes pela métrica ruidosa; com a de 60 s: 47,2/46,7/46,8
  (contra ~47,5).

- **Travamento na abertura (04/11, madrugada):** 3 de ~18 execuções pararam de apresentar quadros aos 13-36 s (vídeos de
  abertura; a decodificação para, as tarefas do taskset dormem em WAIT_SIGNAL e o vigia de DMA repetido derruba as
  listas Wws, `halting the SPU` no pc 0x2554). Causa: **o retorno direto sem teto (`SPURS_PM_STICKY=100000`)**. Ele
  seguia sempre que havia alguma SPU livre, mas a prioridade é por SPU (um workload que só roda naquela SPU ficava sem
  vez) e o kernel também sonda de tempos em tempos as listas sem chute. Corrigido: a checagem do
  `spurs_pm_sticky_take` exige que cada outro workload chutado que pode rodar aqui possa rodar numa SPU livre, e o
  teto voltou a 1024 (~50 ms). Bissecção com inicializações de 55 s (`boot.sh` do scratchpad): 0 travadas em 10 com
  a configuração atual, com `SPURS_PM_AFFINITY=0`, com `SPURS_PM_STICKY=64` e com `SPU_OVL_INCREMENTAL=0`. O
  roteiro da `gow3-fase-v11` foi corrigido para 1024.
- Também testados nesta madrugada (us/job(60s), três execuções): `SPU_EST_HOSTEST=1` 46,5/45,8 (neutro);
  `list-burr` 47,7/46,8/47,0 (neutro); fusão 8/1200 47,2/47,3 (neutro).

**Próxima ação exata:** o fps depende só do tempo de SPU das listas EDGE por quadro (`edge_ms.py`, use o
`us/job(60s)`). Candidatos:
(1) a entrada/saída das funções curtas dos jobs (cada uma carrega e grava dezenas de registradores do
`ctx->gpr`); (3) as chamadas indiretas (`bisl`) dos jobs, que passam por `spu_indirect_branch` + `spu_drain_call`.

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
