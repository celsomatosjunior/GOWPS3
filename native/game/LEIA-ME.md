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

**Patches do ps3recomp (base 4e8f3ca8, v0.18.0):** `ps3recomp-gow3.patch` (runtime, executor Wws, SPURS, GCM) e, para a
ponte do RSX do RPCS3, `ps3recomp-gpu-1.patch` (`gpu/rsx/Emu`) e `ps3recomp-gpu-2.patch` (o resto de `gpu/`; código do
ps3kit de Arnaldo Lima, **GPL-2.0**: um exe com a ponte fica sob GPL-2.0). Aplicar os três, nessa ordem, numa cópia
limpa (`git checkout 4e8f3ca8`, `git apply ...`), clonar as duas dependências da ponte (o patch só registra os
commits): `github.com/KhronosGroup/glslang` em `gpu/third_party/glslang`, commit f0bd0257c308, e
`github.com/asmjit/asmjit` em `gpu/third_party/asmjit`, commit 416f7356967c; compilar `gpu/` com MSVC
(veja `gpu/README.md`) e passar a pasta ao `gow3_build.py --rsx-rpcs3 <pasta>`.

**Renderizador:** com a ponte no build, **o RSX do RPCS3 é o padrão desde 13/11** (imagem completa, ~12-16 quadros
reais/s na luta). Para voltar ao renderizador anterior (live draw D3D12), rode com **`PS3_RSX=live`** (no
`GOW3Native.env` ou no ambiente; qualquer valor diferente de `rpcs3` serve). Um build sem `--rsx-rpcs3` usa sempre o
live draw. O executor Wws fica ligado nos dois (`GOW3_WWS_EXEC=0` o desliga). Validação da troca (13/11): sem variáveis, ponte
ativa, título da janela com o FPS dos flips reais (igual ao `[fps]` do log), janela sem foco com `PS3_JANELA_FUNDO`,
0 travadas em 12 inicializações de 55 s, executor com 0 divergências; `PS3_RSX=live` liga o live draw (testado).

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

**12/11/2026 noite: executor Wws próprio para as listas EDGE (ramo `wws-exec` aqui, `gow3-wws` no ps3recomp;
autorizado pelo Celso, desligado por padrão até validar).**
- **Medidas antes de começar:** índices nativos + coerência por vetor juntos contra a base (mesmo exe, 6+6 rodadas
  alternadas, `ab_amb.sh`): us/job(60s) 37,90 -> 37,63 (-0,7%; nenhuma rodada pareada pior), quadros reais
  9,34 -> 9,56 (ruído). Perfil da fase (`prof_wws.py`, thread do SPURS mais ocupada): job 67% do tempo ocupado
  (traduzido 59 + núcleos 8), gerenciador traduzido 5-9%, despacho 11-13%, memcpy 5,5-8%, DMA 4,5%, coerência
  3,5-5%, canais 2%. Com o tempo medido (41 us de ciclo por job, 28,5 dentro do job) o teto de tirar o gerenciador e
  o kernel é -30% por job; estimativa realista -13 a -19% (~11,5-12 q/s reais).
- **O gerenciador do GOW3 (pm_wwsjob, 12 KB em 0xA00; `SPU_WWSTRACE`/`SPU_WWSDUMP` do ps3recomp, leitor em
  `GOW3_trabalho\wws_exec\dump.py`):** cada execução do policy module roda UM job e volta ao kernel. Passos: GETLLAR
  da linha de estado (r4) em LS 0x80; GET de 0x80 bytes de entradas (lista em +0x3C, 8 bytes cada: `00900001 EA` =
  job com cabeçalho de 0x90) em 0xD00; PUTLLC com +0x70 (dois u16) +1 e a lane +0x74+2*spu = índice; GET do
  cabeçalho em 0xC00 (comandos de carga; parâmetros a partir de 0xC40); GETL de sinal (lista em 0x1540, elemento
  de tamanho 0 com stall-notify); GET do módulo 0x444600 (0xF000 bytes) em 0x4000, em 4 pedaços; GET da lista de
  22 entradas (0xB0) em 0x1EF50 e GETL dela em 0x13000; contexto em 0x1330 (spu, wid, 0, SPURS; `0x0008<<16|índice`,
  0, linha|3...; 0xC40 x4; serviços 0x16B0 0x2F38 0x1720 0x1778 0x1780 0x17A0 0x1A98 0x1AB8 0x1A38); `bisl $0,$5`
  em 0x32AC (r5 = cabeçalho do módulo D200/EB50/130/10, r3 = 0x1330, r1 = 0x3F990); retorno em 0x32B0; GETLLAR e
  PUTLLC da linha com a lane de volta a 0xFFFF; GETL de sinal (tag 5); sai com r3 = 0xB00.
- **A recópia do módulo a cada job é necessária:** em ~7% das execuções o job escreve na área do próprio módulo
  (0x4000-0x4BFF e 0x12600-0x12C00), e a recópia a restaura.
- **O que o job lê do estado do gerenciador** (reprodução com `SPU_JOBREPLAY_POISON`/`REGKEEP`): a pilha do
  gerenciador (0x3F9A0-0x3FE80) não; registradores além de r0/r1/r3, a LS baixa (0-0xA00) e o cabeçalho (0xC00)
  sim (refinando).
- **Executor feito (etapa 1, `gow3_wws_exec.c`, `GOW3_WWS_EXEC=1`; `_STATS=<s>`, `_DEBUG=<n>`):** as três listas.
  Regras tiradas das gravações (`GOW3_trabalho\wws_exec\gera_const.py`, que gera o `gow3_wws_const.h` LOCAL com o
  molde da região do gerenciador): LS na entrada do job e no fim idênticas ao gerenciador traduzido em 100% das
  execuções estáveis (listas 8, 9 e 10: 389, 400, 600); execuções nativas gravadas: 884/884 com a LS igual às
  regras e 591/591 com a mesma sequência de comandos MFC e canais. O job lê do gerenciador só r0/r1/r3/r4/r5/r8, LS
  0-0x80, 0x100-0x200, 0xC40+, 0xD00 e 0xDF0-0x1700 (reprodução com `SPU_JOBREPLAY_POISON`/`REGKEEP`). r4 e 0x13F0 =
  par de entradas >> 28 (0 quando a vizinha não foi publicada). Ganchos no ps3recomp: `g_spurs_pm_native` e
  `g_spu_stop_pc` (sem ele o retorno do job seguia direto para o fim traduzido do gerenciador -- a reprodução de jobs
  também faz isso: os "2 DMAs do gerenciador depois do job"). Um job que redefine a pilha volta pelo laço de cima do
  `spu_run_with_halt`: a volta roda numa segunda chamada. Primeira medida (1 rodada): us/job(60s) 33,0 x ~37,6,
  quadros reais 11,5 x ~9,5. **A/B alternado 6+6 (`ab_exec.sh 6`, mesmo exe, só a variável):** us/job(60s) base
  38,8/37,9/37,9/39,0/38,3/38,7 (média 38,4) x executor 32,8/31,2/31,9/33,5/31,8/33,0 (média 32,4) = **-15,8%**,
  executor na frente nos 6 pares (ruído ~+-0,7); q/s reais (mediana) base 10,0/9,9/9,7/9,2/9,1/9,1 x executor
  10,2/11,2/10,7/11,4/11,4/10,2 (médias 9,5 x 10,8). Por rodada de 330 s: ~7,3 milhões de execuções nativas,
  0 divergências; recusas ~140 mil "LS fora do molde" (~2%) e ~28 mil "entrada não é job" (tipos 2/3/4), que rodam
  o gerenciador traduzido. Estabilidade: **0 travadas em 25 inicializações** com `GOW3_WWS_EXEC=1` (boot.sh, todas até
  54 s). **Teste longo (960 s, `logs/rodar_exec1_longo.log`): rodou até o fim, 0 divergências, mas aos ~7 min (quadro
  16.475 do live draw) o [fps] pulou para 141 fixo e daí em diante TODAS as execuções foram recusadas "fora do molde"
  (~100 mil/min, 0 nativas).** Os testes longos anteriores sem executor (08/11 15 min, 30 min) passaram desse ponto
  sem isso. Investigação: `GOW3_WWS_EXEC_DEBUG_DESDE=<s>` (só mostra recusas depois de s segundos) e capturas
  `LD_FRAME_DUMP` em 10 min com e sem executor (`rodar_exec2_var/base.log`). **Resultado: é o jogo, não o executor
  -- sem comando, o Kratos morre e fica na tela "Estás morto" (o [fps] 141 é o menu); a base sem executor chega lá
  também (até antes, aos ~5-6 min).** Os testes longos antigos não morriam porque o jogo andava mais devagar. Na tela
  de morte as listas mudam (0xDF1/0x12C0 diferentes do molde) e tudo vai para o gerenciador traduzido, como deve.
  Teste longo válido: ~7 min de luta + tela de morte, sem travar, 0 divergências.
- **12/11 23h: LIGADO POR PADRÃO (autorizado pelo Celso).** `GOW3_WWS_EXEC=0` volta ao gerenciador traduzido; os
  estados não reconhecidos continuam indo sozinhos para ele. Conferência sem a variável (exe_exec3): 0 travadas em
  12 inicializações, executor ativo (~155 mil nativas nos 55 s, 0 divergências).
- **Integração ponte RSX + executor (ramo `integra-rsx-wws` nos dois repositórios, criado de `wws-exec`/`gow3-wws`,
  que já contêm `rsx-rpcs3`/`gow3-rsx`; os ramos antigos ficam como estão).** Com `PS3_RSX=rpcs3`, A/B alternado 4+4
  (`ab_integra.sh`, executor desligado x ligado): us/job(60s) 36,0/36,2/36,1/35,7 x 30,2/30,2/30,1/30,0 (**-16,4%**,
  4 de 4 pares); q/s reais (mediana) 9,8/9,6/11,2/13,6 x 12,6/12,3/12,2/12,0 (a cena varia mais com a ponte: no
  par 4 a base pegou uma cena leve, 2.325 jobs/quadro x 2.862). 6,5-7,4 milhões de nativas por rodada, 0
  divergências. **0 travadas em 30 inicializações** com ponte + executor (a ponte sozinha tinha 1 em 100).
  Live draw x ponte, os dois com o executor (`ab_rsx_exec.sh 3`): q/s reais 10,6/11,2/10,4 x 16,1/11,8/12,9 e
  us/job(60s) 33,0/32,6/31,3 x 29,1/30,7/29,5 -- a ponte na frente nos 3 pares (o live draw disputa CPU com as
  threads das SPUs). Teste prolongado ponte + executor (960 s, `rodar_integ_longo.log`): até o fim, 0 divergências,
  sem paradas nem timeouts do RSX; o Kratos morre aos ~5 min (daí em diante o fallback, como no live draw).
  Configuração mais rápida: ponte + executor, **os dois padrão desde 13/11** (`PS3_RSX=live` volta ao live draw); o build
  com ponte exige o ps3recomp no ramo `integra-rsx-wws` (ganchos `g_spurs_pm_native`/`g_spu_stop_pc`).
- **Perfil ponte + executor (13/11, `logs/prof_integ.log`, `prof_integ2.log` com chamadores):** as listas 8, 9 e
  10 rodam em paralelo, cada uma numa SPU (threads 62-77% ocupadas, o resto esperando trabalho no
  `spurs_pm_worker`); o PPU principal ~59% ocupado e ~39% em `sys_timer_usleep(30)` (lr 0x1E5978, sondagem do slot
  da lista; o runtime faz espera ativa com `SwitchToThread`, reação de ~30 us: não é atraso de timer). Na SPU mais
  ocupada: job 61% do ocupado, despacho 9% (`spu_indirect_branch` 2,7% + `spu_lifted_lookup` 1,9% do total), DMA 5%,
  coerência 4%, memcpy/memcmp ~6%; o gerenciador traduzido caiu para 1,9%. No PPU: código traduzido 46% do total e
  os helpers do VMX 7,3% (`vmx_vmaddfp` sozinho 5%): com o PPU mais no caminho crítico, o `--ppu-avx2` (neutro em
  06/11, quando a SPU dominava) medido de novo (`ab_exes.sh 4 avx2 exec3 avx2 PS3_RSX=rpcs3`): q/s reais
  12,0/11,9/12,7/11,4 x 12,7/12,1/12,0/12,4 (+2,5%, 3 de 4), us/job igual -- **neutro de novo, fica desligado**.
- **Outras listas Wws (13/11):** os wids 0-11 usam todos o mesmo gerenciador (image 278921217). Sem o executor, por
  10 s: wid 6 3,6 s (40 mil execuções, só na SPU 0), wid 7 2,2 s, wid 4 1,7 s (23 mil), wid 2 1,5 s, wid 5 1,0 s;
  wids 8-10 ~3,2 s cada (~90 mil execuções cada). A forma varia (despejos `wws_exec\w6.bin`/`w4.bin`, `forma.py`):
  o wid 6 tem 5 módulos de job (2 a 7 pedaços de 16 KB, 13-21 comandos antes do job, entrada 0x4080), o wid 4 três
  (entradas 0xC928/0x76E8/0xDD70, cauda maior). Estender o executor = interpretar o cabeçalho como o gerenciador e
  validar wid a wid (dias). Teto: ~6 us por execução economizados (o que o EDGE deu) -> ~0,46 s por 10 s no total
  (wid 6 ~0,24 s, wid 4 ~0,14 s), ~30% do que as listas EDGE deram e espalhado pelas SPUs: provavelmente abaixo do
  ruído dos quadros reais (~+-5%). Adiado; se for feito, começar pelo wid 6 (SPU 0, a mais carregada).
- Despacho (`spu_lifted_lookup` ~1,9%): já tem cache por thread (SPU_DISPATCH_CACHE); o resto é o caminho de acerto.
- **Módulo de 60 KB por job (analisado, não feito):** em 2.284 execuções (listas 8-10) a imagem em 0x444600 é sempre
  a mesma (fica no segmento de texto do EBOOT, só leitura) e o job escreve na área do módulo só em 0x126B0-0x12C80
  (dados). Com `SPU_OVL_INCREMENTAL=1` (padrão) cada GET já vira um memcmp e só a última parte é copiada: pular
  também o memcmp de 48 KB daria ~1-1,5% e exigiria provar que o job nunca escreve fora dos dados -- adiado.
- **13/11 tarde, onde está o tempo agora (ponte + executor):** wids 8+9+10 = 9,7 s de SPU a cada 10 s
  (`logs/prof_13b.log`): a cadeia EDGE continua o limite (quadro ~ jobs x us/job, ~30 us/job). Na thread que roda
  quase só EDGE, do ocupado: código dos jobs ~43%, núcleos nativos ~18% (`gow3_edge_skin_10e20` sozinho ~12%), despacho
  ~10%, memcpy/memcmp ~9% (2/3 dados de DMA, 1/3 o memcmp do módulo), coerência ~7% (`spu_lockline_lock` ~3,5%:
  trava global disputada por PPU e SPUs), DMA ~5%, canais ~3%, Wws ~2%. Funções de job: nenhuma acima de ~2,4% do
  ocupado (0x11310, 0x6130, 0x7D78: laços de descompressão de vértices) -- núcleo nativo novo renderia pouco.
  Por isso estender o executor a outras listas não muda o quadro (não estão no caminho crítico).
- **CPU por thread** (`scripts_locais\cpu_threads.ps1`, com `-ExecutionPolicy Bypass`): o processo usa ~9 núcleos;
  giram em espera ativa o `frame_clock` (100%, `GCM_DRAIN_MS=0`), o PPU (100%, `usleep(30)`), a `rsx::thread` do RPCS3
  (100%) e 5 threads "spu job" (~50% cada, sondando DMA em `mfc_do_transfer` e esperando sinal). A/B 3+3 com a ponte,
  `GCM_DRAIN_MS=4` (frame_clock dormindo): us/job 30,3/30,1/34,2 x 29,2/31,0/29,7, q/s reais 12,7/11,7/12,6 x
  12,2/12,3/11,0 -- **neutro**: os giros não atrasam o EDGE (sobram núcleos no 5950X). Padrão mantido.
- Tasks SPURS assíncronas (`SPU_ASYNC_PROF=<s>`, ps3recomp 55a2793e): ~60/s (imagem 402824896, 5 por lote), cada uma
  numa thread nova: ~325 us até começar, ~1,9 ms rodando. Fora do caminho crítico; um pool de threads daria < 1%.
- Título da janela com a ponte mostrava FPS 0 (ninguém contava os flips): corrigido no ps3recomp a1862ee3 (o flip do
  RSX do RPCS3 conta). Com `PS3_JANELA_FUNDO` a janela da ponte é empurrada para baixo nos primeiros 30 s (d113a8c).
- **Plano:** gancho nativo no `spu_run_policy_module` para os wids 8-10, que só toma uma execução cujo próximo item
  é um job tipo 1 de forma conhecida (o resto -- lista vazia, tipos 2/3/4, cabeçalho diferente -- roda o gerenciador
  traduzido); os mesmos comandos MFC pelo runtime (atômicas e coerência iguais), o estado que o job e os serviços
  leem, o job chamado direto, a liberação. Validação: as execuções gravadas (fora do jogo) e um modo sombra no jogo
  antes de ativar; depois A/B alternado e 20+ inicializações.

**12/11/2026: ascension-native do Arnaldo (acesso dado hoje) aplicado ao EDGE do GOW3.**
- **Descompressão de índices nativa (no padrão, ganchos locais):** o módulo 206 do GOW3 usa o mesmo formato de
  índices comprimidos do EDGE que o 218 do Ascension (decodificador em Python a partir do `indices.h` dele: índices
  = PUT do job nas gravações). A 0x106E0 do GOW3 é a 0xE4D0 de lá (contexto r3, fluxo r4; prólogo r80/r81/r0/r1 na
  pilha; contagem no u16 de +0x190; formato no nibble alto do byte 6; +0x50 = fluxo; a cauda 0xD620 grava o fim em
  +0x58), achada com uma sonda em todas as funções do módulo (qual recebe o endereço do fluxo). O gancho chama o
  `gowa_decode_indexes_ls` dele (`indices.c`, cópia com crédito em `GOW3_trabalho\edge_nativo\gow3_edge_idx*.h`).
  Reprodução (jobcap206s, 512 jobs): PUTs e registradores idênticos à base em todos; a LS só difere num byte de
  pilha que já oscila entre execuções da base (valor do decrementador). Velocidade: -2,3% us/job (3 rodadas
  alternadas, 32,5 -> 31,8). No jogo, 6+6 rodadas alternadas: us/job(60s) 38,0 -> 37,6 (-1%, dentro do ruído; o
  ganho esperado no jogo é ~1,6%). Quadros reais iguais no ruído. 0 travadas em 20 inicializações.
  `GOW3_EDGE_IDX=0` desliga.
- **Gerador de nativos dele (`gen_native_from_lift.py`): mais lento aqui.** Roda no nosso lift (adaptação em
  `edge_nativo\gera_nativos.py`: mesmos limites de float do build, LS pelo ponteiro guardado), saídas idênticas,
  mas 13 raízes quentes deram +20% a +40% us/job: o nosso build já põe os registradores em locais com vivacidade e
  funde os trechos; o código gerado grava ~100 registradores num vetor a cada desvio de cauda. Descartado.
- **Perfil da reprodução refeito com exe e .map do mesmo build** (o de antes usava um .map de outro build e
  atribuía 16% a um módulo que nem roda): o tempo do job 206 é plano, a maior função 8% (0x9A68, luzes).
- Não se aplicam direto: `vertices.c`/`lighting*.c` (regra de float deles: fator zero -> zero; a nossa limita a
  +-FLT_MAX), e o executor Wws paralelo (as listas EDGE do GOW3 saem uma por vez). Inventário em
  `GOW3_trabalho\ps3kit_integrado.md`.
- **Empacotador de vértices de 54 bytes (0x66F0 -> epílogo 0x5DE8): exato, mas neutro, fora do padrão.** O mesmo
  registro do `output_vertex_packer.c` do Ascension, com os tipos renumerados (1, 3, 4, 29, 30, 31, 32; lá 27-30
  no lugar de 29-32) e as mesmas constantes; a contagem é r4 - 1. Achado com uma sonda que grava LS e registradores
  na entrada do 0x66F0 e na chegada ao 0x5DE8 (6 casos, LS inteira igual à simulação em Python). Núcleo em
  `edge_nativo\gow3_edge_pack.h` (ganchos em `GOW3_trabalho\edge_pack`): 0 recusas, PUTs e registradores
  idênticos, mas a reprodução não muda (30,7-31,3 x 31,0-31,3 us/job no mesmo exe, `GOW3_EDGE_PACK=0/1`): o
  traduzido já faz 2 vértices por volta com operações vetoriais.
- **Coerência (ps3recomp, `spu_coherency.c`):** `SPU_COH_STATS=1` mostrou que cada aviso de escrita numa linha
  reservada (todo PUTLLC bem-sucedido, sob a trava global) percorre **52 contextos** SPU e custava ~1.180 ciclos;
  ~245 mil avisos/s no jogo. Agora o percurso usa um vetor de ponteiros que espelha a lista (reconstruído sob a
  mesma trava a cada mudança; mesma ordem, mesmo teste): ~920 -> ~745 ciclos por aviso. Partes que ficam:
  `ppu_resv_break_line` ~176, barreira ~104, vigílias ~72 ciclos. No jogo (3 rodadas alternadas, mesmo exe):
  us/job(60s) 38,0 (lista, `SPU_COH_LIST=1`) -> 37,5 (vetor), -1,3%, no ruído; quadros reais iguais.
- Reprodutor: `SPU_JOBREPLAY_LSFROM=<hex>` lista as faixas da LS que diferem a partir de um endereço (ps3recomp
  a14d01bb, ramo gow3-rsx).

**11/11/2026 (noite, 2): contadores de quadros, validação do reprodutor de jobs e onde vai o tempo do EDGE.**
- **O que cada contador mede** (fase, roteiro de X dos A/B, 330 s):
  - `[fps] N (frames a..b over Ts)` do live draw: `g_ld_frames` sobe em cada `rsx_live_draw_present`. Ele roda duas
    vezes por flip do jogo: no método de flip da FIFO (`sink_flip`) e pelo relógio de quadros do main.cpp
    (`present_guest_frame` -> `gow3_rsx_present`, uma vez por flip pedido). Mede **apresentações, o dobro dos
    quadros**. Foi a base dos "~17-19 q/s" desde 04/11.
  - `[flip] N at T ms` (`gcm_flip_request`, cellGcmSys.c): um por flip pedido pelo jogo. `fps_real.py` usa este.
  - contador de quadros do próprio jogo: a palavra 0x649ED8 (+1 por volta do laço principal, func_0028DA14);
    medido com `PPU_WWATCH=0x00649ED8 PPU_WWATCH_MAX=0`: igual ao `[flip]` e metade do `[fps]` em todas as janelas.
  - `[fps]` com a ponte do RSX do RPCS3: os flips que o RSX dele fez (eventos FLIP), quadros reais.
  - RPCS3: "FPS" do título da janela (flips por segundo do RSX dele), lido pelo `rpcs3_medir.ps1` (mesmo roteiro de
    X, título lido a cada 5 s): 20,7-23,4 em 05/11 (8 leituras, 280-320 s); **refeito em 11/11 com o PC livre:
    `-Medir 120 -Janela 200`, 40 leituras, mediana 22,06, média 21,82, faixa 17,8-24,3** (uma leitura de 60, tela de
    morte, fora). As capturas aos 120 e 320 s mostram a tela de morte: com só X, o Kratos morre e reinicia pelo
    checkpoint, então a linha do tempo não é a mesma do nativo; as leituras ~22 são do combate. Nativo nas mesmas
    condições (A/Bs de 11/11): 9,2-10,8 quadros reais/s, ~2,3x abaixo.
  - Estimativa (não medida): se o RPCS3 tivesse os mesmos ~2.700 jobs EDGE por quadro e o EDGE fosse todo o quadro
    como aqui, os seus ~22 q/s dariam ~16 us por job. Não há medida direta do us/job do RPCS3.
- **Reprodutor de jobs (amostra representativa):** `SPU_JOBCAP=<pasta>,206,D200,512,3000000` com
  `SPU_JOBCAP_STRIDE=11` grava 1 job em 11 ao longo de ~2 quadros da fase (`GOW3_trabalho\jobcap206s`, 266 MB).
  Reprodução de 512 jobs, 30-200 repetições: 0 interrompidos; 477 com todos os DMAs iguais à gravação; a
  reprodução é determinística (duas execuções, as mesmas diferenças byte a byte). As diferenças que restam:
  (1) ~40 registradores voláteis e a LS baixa do gerenciador (0x00-0xC0), estado do gerenciador depois do fim do
  job; (2) 2 DMAs do gerenciador depois do fim do job (fora da gravação); (3) em ~35 jobs, 1-8 palavras de PUT
  diferentes (valores de ponto flutuante e palavras de comando do RSX no anel de saída) -- deterministas na
  reprodução, iguais com e sem os núcleos nativos: no jogo o job viu uma entrada diferente da gravada (a hipótese
  é atividade assíncrona do gerenciador durante o job: listas paradas e retomadas, interrupções); a gravação é do
  nosso próprio código, não do PS3. `SPU_JOBREPLAY_PUTDIFF=1` lista cada byte.
- **Onde vai o tempo** (`SPU_JOBTIME=206,D200`, no jogo, fase): ciclo entrada->entrada 41 us/job (~2 us da própria
  medida), **28,5 us dentro do job** (código, DMAs e canais; ~70%), ~12,5 us fora (gerenciador Wws, kernel do
  SPURS, passagens e espera da próxima lista). Reprodução da amostra: 32-33 us/job (média das medianas). Perfil da
  reprodução (tempo medido): código traduzido ~55%, skinning nativo ~12%, despacho (desvio indireto, busca,
  drenagem) ~11%, canais/MFC ~4%. No jogo, a thread mais ocupada do SPURS: código dos jobs 47%, espera no kernel
  22%, despacho ~7%, coerência/lock-line ~3%.

- **Fusão maior de trechos SPU** (`--fundir-linhas 1500 --fundir-trechos 12`, padrão 500/4): reprodução -3,3%
  (33,28 -> 32,20 us/job, duas rodadas alternadas, saídas idênticas à base); 4000/40 piora. No jogo (2 rodadas
  alternadas, 330 s): us/job(60s) 37,8/38,7 (base) x 37,8/37,9; quadros reais 9,70/9,27 x 9,21/9,21: dentro do
  ruído, sem ganho confirmado -- fica desligada.

- **GOW3_PIN=1** (gow3_diag.cpp; ideia do PS3_HOST_PIN do Arnaldo): PPU principal e as 6 threads do SPURS, cada
  uma num núcleo físico próprio. A/B 3 rodadas: us/job(60s) 38,2/37,7/38,5 (sem) x 37,9/37,3/38,6 (com), -0,5%,
  ruído; quadros reais iguais. Fica desligado.

- **Fora do job, por job EDGE (11/11 noite):** execução do policy module (pmstats) 39,4 us x 28,1 us dentro do job ->
  ~11 us do gerenciador Wws dentro da execução, ~1,3 us entre execuções (kernel do SPURS, com SPURS_PM_STICKY).
  Interrupções do gerenciador (`SPU_IRQTIME=1`): ~61 mil/s, 0,77 us cada, ~48 ms/s ao todo (~0,2 us por job EDGE).
  Leituras de canal (`SPU_POLLTRACE`): ~2,6 milhões/s (estado de tags 33%, atômico 27%, máquina 23%, decrementador
  10%). Nenhuma espera em canal >= 20 us dentro das execuções do EDGE (`PS3_FTRACE`). Desvios indiretos
  (`SPU_IB_HIST`): ~1,75 milhão/s, quase todos do gerenciador (0x3FEC0/0xA2C/0xA60 das interrupções, a tabela
  interna 0x1B4C/0x1B90/0x1C68, serviços chamados pelos jobs 0x1778/0x1B00/0x2F38). Perfil do jogo por instrução
  (thread do SPURS mais ocupada): nenhum ponto passa de ~1%; os maiores são a carga da entrada do cache de despacho
  (spu_lifted_lookup), o laço do spu_coh_notify_write por todos os contextos e o spu_lockline_lock; funções de job
  ~1% cada. Conclusão: o tempo é processamento espalhado; não há uma espera ou custo isolado grande.

- **SPU_IBL no gerenciador Wws** (`--spu-ibl` + `SPU_IBL=1`; tools/spu_ibl.py do ps3recomp, do SPU_IBL do Arnaldo):
  desvios indiretos de cauda e chamadas do gerenciador às próprias funções direto. A regra copiada recusava tudo
  com `irq_saved`, e o código quente do gerenciador roda dentro do tratador de interrupção: agora só o retorno da
  interrupção (pc == irq_resume_pc) fica de fora. Desvios pelo caminho genérico -31% (281 -> 193 milhões no mesmo
  tempo). No jogo, 3 rodadas: us/job(60s) 38,9/38,9/38,5 x 37,6/39,1/38,4 (-1,0%, ruído), quadros reais iguais.
  Fica desligado: o caminho genérico de desvio é barato.
- `-march=znver3` nas fontes SPU, na reprodução: 32,0/32,7 x 32,7/32,6 us/job, neutro (como em 08/11).
- Custo dos limites de float (`-DSPU_AX_TESTE_SEMAXI=1`, só medida): reprodução média 33,2 -> 25,7 us/job, mas
  mediana 24,8 -> 23,2 e só 350 de 512 jobs com as mesmas saídas: sem os limites os jobs pesados fazem outro
  trabalho (o "ganho" de 07/11 de novo). O custo real dos limites fica perto de ~6%.

- **Ponte do RSX do RPCS3, 30 min na fase** (`scripts_locaissx_longo.sh`, X a cada 15 s: o Kratos morre, volta pelo
  checkpoint e luta de novo): flips até 1.798 s, nenhuma falha de página fora do RSX, nenhum erro fatal, 697 janelas
  de 2 s com mediana de 9,93 quadros reais/s; capturas a cada 5 min com o combate e o HUD inteiros. Menu principal
  também confirmado (captura dos 30 s). A luta do Poseidon em si não é alcançável só com X (precisa jogar ou save).

- **Inicializações com a ponte (boot.sh, 55 s):** 1 travada em 20 (aos 13 s, na rajada de ~5 mil flips/s do
  carregamento); v21 nas mesmas condições: 0 em 20 (0 em 180 no total). Na travada, o RSX do RPCS3 registrou
  `nv406e::semaphore_acquire has timed out. semaphore_address=0x2E200510 value=0xE expected=0xF`: esperou >1 s
  (driver_recovery_timeout) o label 0x51, que um job SPU escreve com um PUT de 4 bytes por quadro (pc 0x59A0; o
  PPU só o zera, 0029A430) -- candidato: o workload Wws_Job/RsxSync (wid 11). Hipótese: o ritmo de flips sem
  limite (no live draw os flips andam a 60 Hz pelo relógio de quadros) expõe uma corrida que o console não vê.
  Teste (12/11, 120 inicializações alternadas em blocos de 10, mais as anteriores): sem limite 1 travada em 100,
  com `PS3_FRAME_LIMIT=60` 0 em 90. Diferença indistinguível do acaso (um único evento); a hipótese do ritmo de
  flips não se confirmou nem se descartou. O padrão segue sem limite (o limitador fica como opção, não muda os
  quadros reais da fase, ~10 q/s). Taxa da ponte ~1%, contra 0 em 180 na v21: se voltar, investigar o RsxSync
  (wid 11) e quem deveria escrever 0xF no label 0x51 (`GCM_RSX_EVDBG`, `SPU_JOBCAP` no img do pc 0x59A0).

**11/11/2026 (noite): ponte do RSX do RPCS3 e correção da métrica de quadros.**
- **Métrica:** o `[fps]` do live draw conta 2 por quadro do jogo (`rsx_live_draw_present` roda no flip da FIFO e
  de novo pelo relógio de quadros). O contador de quadros do próprio jogo (0x649ED8, +1 por volta do laço
  principal) e o contador de flips do GCM (`[flip]`) dão exatamente a metade: os "~19 q/s" da v21 são ~10
  quadros reais por segundo. O RPCS3 (título da janela, que conta flips) faz ~21-23 na mesma luta. A/B entre
  builds do live draw continuam válidos (o fator é o mesmo); para quadros reais, `GOW3_trabalhops_real.py`.
- **Ponte do RSX do RPCS3** (ramo `rsx-rpcs3` aqui, `gow3-rsx` no ps3recomp; código do ps3kit de Arnaldo Lima,
  GPL-2.0): `gow3_build.py --rsx-rpcs3 <pasta do build de gpu/>` e rodar com `PS3_RSX=rpcs3`. Sem a variável o
  exe é o de sempre (live draw). Marcos: compila, o RSX inicia (Vulkan), primeiro quadro, abertura e fase com
  imagem completa (Kratos em combate, HUD, tela de morte). Correções que precisou: `vm_commit` aceita a memória
  já mapeada do RPCS3 (do ps3kit; sem ela o malloc da libc gravava em 0xFFF18FFC), a ponte aloca as pilhas de
  callback em 0xDF000000, a janela é a do backend nulo sem apresentar, restaurada do minimizado (a swapchain do
  Vulkan não monta sem área).
- Com a ponte: ~10 quadros reais/s, como a v21. O PPU espera o slot do anel de 3 quadros (0x649EC0) que a lista
  EDGE zera por PUTLLC; o RSX fica ~81% ocioso (`RSX_FIFO_TIMELOG`). Os jobs EDGE por quadro e o us/job são os
  mesmos nos dois renderizadores: o limite continua sendo a cadeia EDGE nos SPUs.

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

- Teto 1024 medido: us/job(60s) 45,8/47,3/47,0, medianas 14,9-16,1 q/s (o ganho de cache do teto maior se mantém).
- **Versão `gow3-fase-v12` (04/11, 5h20; tag e `Projetos\versoes\gow3-fase-v12\rodar_fase.ps1`):** tudo da noite,
  com `SPURS_PM_STICKY=1024`, `SPU_OVL_INCREMENTAL=1` e `SPU_FTZ=1` (a afinidade saiu às 7h, ver abaixo). Teste de 15 min (X a cada
  20 s): quadros até o fim, nenhuma SPU derrubada, a fase recarregou 3 vezes depois de mortes, memória plana (~1,1 GB
  em uso, privada 2,1-2,7 GB), **mediana 15,05 q/s** (a v10 dava 13,1 no mesmo teste); us/job 46,7.
- No dia 03->04/11: ~54,8 -> ~46,7 µs por job EDGE (-15%); fase de ~12 para ~15 q/s.

- **Correção da causa do travamento (04/11, 7h):** a culpada era **a afinidade (`SPURS_PM_AFFINITY=1`)**, não o teto.
  Inicializações de 55 s com `SPURS_PM_STATS=10` (que muda o tempo e expõe a corrida): 2 travadas em 12 com
  afinidade, 0 em 12 sem. No total, 6 travamentos em 34 execuções com afinidade e 0 em 22 sem; o teste com teto de
  100000 que travou 1 em 12 também estava com afinidade. Fixar cada thread de SPU num processador lógico só deixava
  alguma sem CPU e as listas Wws paravam. Afinidade fora do padrão (continua opcional, não usar); teto 1024 mantido
  por precaução (mesmo desempenho). Roteiro da `gow3-fase-v12` corrigido (sem afinidade).

- **Teste final da v12 sem afinidade (04/11, 7h20, 15 min, sem `SPURS_PM_STATS`):** quadros até o fim, nenhuma SPU
  derrubada, a fase recarregou 4 vezes depois de mortes, **mediana 15,6 q/s** (média 16,0). A cópia da v12 recebeu
  este exe.

- **Laços que voltam ao começo da própria função (04/11, manhã):** o tradutor começa uma função nova no cabeçalho de
  um laço que também é entrada de função, e o salto de volta virava `SPU_DIRECT` para ela mesma: o clang o
  transformava num laço, mas cada volta gravava e recarregava todos os registradores pelo `ctx->gpr` (na 0x6C10,
  ~200 acessos ao contexto e ~300 à pilha por volta, sem nenhum desvio no corpo). O perfil mostrava 18% de
  derramamento e 18% de movimentações no código dos jobs. Agora o `spu_reg_locals.py` põe o rótulo da entrada e
  troca esse salto (e os saltos para a entrada de um trecho fundido, que o `spu_inline_fallthrough.py` agora rotula)
  por `if (SPU_DIRECT_LOCAL_OK(ctx, PC)) goto loc_PC;` antes da gravação: as mesmas verificações do `SPU_DIRECT`
  (interrupção pendente, dica de reinício da pilha), senão grava e segue como antes. 170 saltos no módulo quente,
  27 funções que voltam a si mesmas. **us/job(60s) 44,0/42,6/43,8 (contra ~46,7), medianas 16,7/15,9/18,05 q/s.**
  Imagem conferida por `LD_FRAME_DUMP`; testes do `test_spu_reg_locals.py` (com o clang no PATH, os de interrupção
  também rodam).
- **Cadeias de float sem o limite no meio (04/11, manhã):** com os laços nos locais, a função mais quente ficou presa à
  latência das cadeias de fma, e cada elo pagava o max/min do `SPU_AX_CLAMP`. O `spu_float_inputs.py`
  (`unclamp_chains`, padrão; `--sem-cadeias` desliga) segue o grafo da função (rótulos, gotos) e usa
  `spu_fma_u`/`spu_fm_u`/... (sem limite) num resultado que, em todo caminho até ser regravado, só é lido como
  operando de outra operação de float, que limita o próprio resultado. Diferença possível só quando um intermediário
  estoura para ±Inf/NaN no host, e mesmo assim a cadeia sai em ±FLT_MAX. 648 das 2327 operações do módulo quente.
  **us/job(60s) 43,6/41,9/41,5 (contra ~43,5), medianas 16,5/17,7/18,9 q/s**; imagem conferida; 10 inicializações sem
  travar (também 10 com os laços locais). Versão **`gow3-fase-v13`** (tag e `Projetos\versoes\gow3-fase-v13`).
- Perfil depois das duas mudanças: o código dos jobs tem ~22% derramamento na pilha (laços com ~80 vetores vivos
  para 16 registradores), ~14% movimentações; o runtime ~19% (`spu_indirect_branch`, `spu_lifted_lookup`,
  `spu_coh_notify_write`).
- Medidos de novo sobre a v13 e descartados: `-DSPU_EST_HOSTEST=1` (rcpps/rsqrtps no lugar da divisão; a 0x9040
  tem ~16% das amostras em vdivps/vsqrtps) 42,2/42,5/41,8, neutro; nenhum resultado de float limitado (só os
  operandos `SPU_AXI`) 44,6/44,8/44,7, **pior** (como o "sem desvio": Inf/NaN espalhados custam mais trabalho).
  Uma análise de definições pelo grafo inteiro não tiraria nenhum `SPU_AXI` além dos do trecho reto (0 de 3905).
- Testar `ctx->irq_saved` antes de chamar `spu_irq_regs_maybe_restore` no despacho indireto: 42,2/42,4/43,3, neutro
  (revertido).
- `SPURS_PM_STICKY=8192` (em vez de 1024): 43,0/42,8/42,4, neutro; fica 1024.
- **Teste de 15 min da v13 (04/11, 11h40; X a cada 20 s depois de 240 s):** quadros até o fim (899 s), nenhuma SPU
  derrubada, a fase abriu 6 vezes (recargas depois de mortes), memória plana (~1,1 GB em uso, privada 2,0-2,7 GB,
  55-66 threads), mediana 15,85 q/s (a v12 deu 15,6 no mesmo teste; o teste mistura telas de morte e recargas, o
  us/job é a métrica do código).
- No `spu_lifted_lookup`, ~47% das amostras são a carga da entrada do cache de despacho por thread (falta de cache:
  a cadeia EDGE muda de thread a cada 1024 repetições e o código dos jobs ocupa o L1/L2).

- **O exe abre sozinho (`GOW3Native.env`, 04/11, 13h):** o `GOW3Native.exe` lê, antes de tudo, o arquivo
  `GOW3Native.env` ao lado dele (uma variável `NOME=valor` por linha, `#` comenta; o que já estiver no ambiente vence)
  e `GOW3_PASTA=<pasta>` vira a pasta atual (a do save). Testado aberto direto de `C:\`: leu as 13 variáveis e chegou à
  fase. Serve para o Steam: o Steam Input só traduz o controle (o Switch 2 Pro do Celso, **só por USB**) para o
  processo que ele mesmo abre. No Steam: *Jogos -> Adicionar um jogo não Steam*, escolher o `GOW3Native.exe` da
  `Projetos\versoes\gow3-fase-v14` e pôr nas opções de inicialização o caminho do `EBOOT.pular_videos.ELF` da mesma
  pasta, entre aspas. Versão **`gow3-fase-v14`** (mesmo código SPU da v13).
- Contagem de entradas por função (PGO, `--spu-pgo gerar`, 60 s da fase): ~6 milhões de entradas de função traduzida por
  segundo na cadeia EDGE (~160 ns de trabalho por entrada). As folhas chamadas por `brsl` direto são só ~2% das
  entradas. Salvar/restaurar xmm6-15 e push/pop (convenção do Win64) são ~4,5% das amostras do código dos jobs:
  candidato a `sysv_abi` nas funções traduzidas (todos os ponteiros de função SPU teriam de mudar).

- **Comparação com o RPCS3 (04/11, tarde).** Meta do projeto: 60 q/s, como o RPCS3 do Celso.
  - Os patches que ele liga para o 1.00 (Disable MLAA, Disable Layered Fog, Disable Color Grading, além dos vídeos),
    com `--patch-rpcs3` (agora com `--elf <trabalho>\EBOOT.ELF`, porque o `--jogo` sozinho pede o `unicorn` do
    analisador; o build completo com a tradução do PPU leva ~4 min): us/job(60s) 40,9/41,7/41,8, medianas
    19,45/16,8/18,0 q/s, os mesmos ~1300-1400 jobs EDGE por quadro. Quase neutros: não são eles que dão os 60 q/s do RPCS3.
    O build voltou sem patches.
  - RPCS3 1 (`rpcs3_medir.ps1` do scratchpad: aperta J, o Cross do teclado dele, nos tempos do `PAD_SCRIPT`, e mede o
    título da janela e o tempo de CPU por thread): 38-45 q/s entre 260 e 300 s (cena não confirmada; a captura falhou),
    seis threads a 82-85% de um núcleo (SPUs, com espera ativa) e uma a 99%. Se for a mesma luta, a cadeia EDGE dele
    leva ~22-26 ms por quadro contra os nossos ~55: ~2x por job. Repetir com captura quando o PC estiver livre (o
    script toma o foco da janela).

- **Comparação com o port do Ascension (04/11, noite).** O port `otavix010/gow-ascension-pc` (MIT; clone de
  referência fora dos repositórios) tem 14 laços do job EDGE do Ascension em código nativo. O job EDGE do GOW3
  (`jobmod_14561`, EBOOT 0x444600) é o mesmo job (Ascension 0x6FB300), de outra versão: um alinhamento instrução a
  instrução dos dois módulos casa 61% e leva os laços deles aos nossos endereços (skinning E550/EC08 -> 0x10760/
  0x10E20, a nossa função mais quente; transformação F538 -> 0x11740; projeção D250 -> 0xF428; descarte de triângulos
  D640 -> 0xF898; normais A880 -> 0xC0C0; BBC8 -> 0xDD50, idêntica). Os registradores mudam de uma versão para a
  outra, então os núcleos têm de ser reescritos para o nosso código. No Ascension as três listas EDGE rodam em
  paralelo em 4 SPUs; no GOW3 a lista do quadro seguinte depende do flip do anterior (serial de verdade).
- **Ganchos nativos** (`gow3_build.py --spu-ganchos <pasta>`): `<pasta>/ganchos.json` lista
  `{modulo, funcao, cabecalho, chamada}`; o build inclui o cabeçalho na fonte do módulo e põe a chamada como primeira
  linha da função traduzida (antes dos rótulos, uma vez por entrada), antes da fusão e dos registradores locais.
  Os cabeçalhos são reescritas de código do jogo e ficam só na pasta de trabalho (`<trabalho>\edge_nativo`), com um
  modo sombra que roda também o corpo do laço traduzido (extraído do código gerado por `gera_ref.py` da mesma pasta)
  e compara LS e registradores.

- **RPCS3 na mesma luta (05/11, madrugada; `rpcs3_medir.ps1` com capturas no começo e no fim da janela):** Kratos
  cercado pelos esqueletos no início da fase do Poseidon, com a configuração e os patches do Celso: **20,7-23,4 q/s**
  entre 280 e 320 s (duas threads a ~99% de um núcleo, três a ~91%, três a ~54%). O nativo faz ~17-19 q/s nessa
  luta: **~85% do RPCS3**. Os 38-45 q/s da primeira medida eram de outro trecho; os 60 q/s do RPCS3 são de cenas
  mais leves.
- **Núcleo nativo do skinning** (`<trabalho>\edge_nativo\gow3_edge_skin.h`, gancho no topo do laço 0x10E20; o
  build usa `<trabalho>\edge_nativo` sozinho quando existe, `--sem-ganchos` desliga; `GOW3_EDGE_NATIVO=0` desliga
  na execução): pares 0..n-2 em AVX2 (A e B no mesmo registrador), mesmas operações e limites do traduzido, o par 0
  pelos registradores vivos. Modo sombra: **0 diferenças em mais de 4,19 milhões** de execuções (antes de copiar o
  limite da 3a conta da linha r37 do vértice B, 3 diferenças em lixo perto de -FLT_MAX). Ganho medido pequeno:
  us/job(60s) 41,4/41,2/41,5 ligado contra 43,2/40,4/42,3 desligado (~1,4%).

- **Mais dois núcleos nativos (05/11):** a 0xDD50 (normaliza vetores no lugar; função folha inteira, gancho na
  entrada que volta com `SPU_RET`; 0 diferenças em mais de 2,09 milhões no modo sombra) e a iluminação 0x9040 (8
  vértices por vez contra as luzes da lista, atenuação suave, em SoA com 8 vértices por registrador AVX2; limites
  depois de toda conta; 0 diferenças em mais de 262 mil execuções). A referência do modo sombra para uma função
  inteira sai do `gera_ref_fn.py` da pasta local. **Os três juntos: us/job(60s) 39,4/40,4/39,5 contra 42,4/41,8/42,0
  desligados (-5,5%), medianas 18,3/17,55/18,6 contra 16,4/15,7/16,1 q/s (+13%).** 10 inicializações sem travar com os
  ganchos. Uma execução no modo sombra (cópias de 768 KB a cada chamada) travou na abertura do mesmo jeito que a
  afinidade travava: a corrida antiga aparece quando o tempo das threads muda. Versão **`gow3-fase-v15`**
  (`Projetos\versoes\gow3-fase-v15`, com cópia dos núcleos em `edge_nativo`).

- Atalho no núcleo do skinning (as máscaras de shufb que só permutam palavras viram vpermilps; o último par segue o
  caminho genérico): 0 diferenças no modo sombra, us/job(60s) 40,1/39,7/40,2 (neutro, fica). **Teste de 15 min da v15
  (05/11, 11h):** quadros até o fim (899 s), nenhuma SPU derrubada, a fase abriu 3 vezes, memória plana (~1,1 GB em
  uso, privada 2,0-2,6 GB), **mediana 17,8 q/s** (a v13 deu 15,85 no mesmo teste). A cópia da v15 recebeu este exe.
- Olhados e deixados para depois: a 0x9F90 (segundo laço da 0x9A68) já é SoA (4 luzes por vetor, luz hemisférica com
  12 acumuladores); a 0x6C10 empacota os vértices com dezenas de máscaras e rotações calculadas; o módulo 912f são
  testes de caixas cheios de desvios.

- **Quarto núcleo: as normais 0xC168** (produto vetorial de dois fluxos, troca de componentes pela máscara de LS
  0x12680, normalização com passo de Newton; 8 vetores por volta em SoA; a chamada salta para a 0xC520, que põe
  r3 = r45 e faz o epílogo). Primeira sombra: 137 mil diferenças de sinal no zero em vetores de enchimento (L = 0):
  o traduzido não limita y*y em 6 das 8 cadeias (y = FLT_MAX, y*y = Inf, L*y*y = NaN -> -FLT_MAX), e o núcleo
  limitava tudo. Copiado o padrão (limite só nos vetores 5 e 6, sem limite nos dois intermediários fm_u/fa_u):
  0 diferenças em mais de 524 mil. **Os quatro: us/job(60s) 40,6/40,2/39,5 contra 42,9/43,1/42,5 desligados
  (-6,4%).** 10 inicializações sem travar. Versão **`gow3-fase-v16`** (`Projetos\versoes\gow3-fase-v16`). Lição: copiar o padrão de limites do código gerado vale mesmo onde parece só lixo.

**05/11 à tarde: ideias do Arnaldo (repositório público arnaldolima1/gow-ascension-pc, MIT, e o plano dele no
ps3kit) e do port otavix010, cada uma em A/B no GOW3** (notas em `F:\Quadrado do Claude\referencias\
ascension_publico_notas.md`; nada de código do ps3kit copiado):
- `spu_float_inputs.mark_body_flow` (ps3recomp, nosso): um operando de float fica sem `SPU_AXI` também depois de
  rótulos e cópias (`ori/shlqbyi/rotqbyi` por 0) quando todo caminho o traz de outra operação de float (fluxo
  para a frente, interseção). -4,4% de SPU_AXI no job EDGE; us/job(60s) 38,6 contra 39,4. Padrão no build
  (`--sem-fluxo-float` desliga).
- `SPU_LS_VEC` (spu_context.h, ideia do PR #637 do upstream): quadword de LS num load/store de 16 bytes + pshufb.
  Neutro (38,4); fica.
- `GOW3_PPU_PRIO` (gow3_diag.cpp, padrão 1): a thread principal do PPU acima do normal. Mediana 18,0 -> 18,9 q/s,
  EDGE 54,4 -> 51,7 ms/quadro. Padrão.
- `GOW3_TIMER_RES=1` (NtSetTimerResolution máximo, sem power throttling): neutro; desligado (no Ascension piorou).
- `SPURS_IDLE_BACKOFF=0` (padrão do Ascension): **o GOW3 trava no carregamento** (3 de 3). Não usar.
- Não se aplicam: um worker de SPU a menos (este PC tem 32 CPUs lógicas); interrupções do gerenciador Wws dentro
  dos jobs (no Ascension custam tanto quanto o código dos jobs; aqui pm_wwsjob 2,5% + irq 0,4% da SPU).
- `preserve_none` entre funções traduzidas (2b.10 do otavix010): o clang 19 aceita no Windows, mas os
  `musttail` para o runtime (`spu_indirect_branch_mt`) e para ponteiros do registro exigem a mesma convenção;
  ficou de fora.
- A 0x9A68 é o começo do laço 9A68 -> A110 -> 9A68 (saída em 0xA270 -> 0xD620): um núcleo exato precisa
  substituir o laço inteiro e reproduzir os registradores na saída. Fica para depois.
- PPU no caminho crítico (perfil prof22: a SPU do EDGE 20,8% parada à espera da próxima lista; a thread principal
  56,7% em `sys_timer_usleep(30)`). Três opções de build do PPU, medidas intercaladas (3 rodadas, base/pgo/avx2/
  pgoavx2 alternados, `ab_inter.sh` local): `--ppu-avx2` (VMX_FAST_FP em `ppu_vmx.h`: vaddfp/vsubfp/vmaddfp/
  vnmsubfp com SSE/FMA, mesmos bits em 4 milhões de casos), `--ppu-pgo <profdata>` e as duas juntas. **Nenhuma
  ganhou fora do ruído**: nas execuções com a luta inteira medida (<=3 janelas "fora") a mediana fica em 17-20 q/s
  para todas, us/job(60s) 38,5-39,7. A mediana sobe junto com o número de janelas "fora" (o jogo nem sempre chega
  à luta no mesmo ponto), então só comparar execuções com fora baixo. As opções ficam no build, desligadas.
- `--ppu-restrict` (`__restrict` no ctx do PPU): o jogo fica preso antes da fase. Não usar.
- Onde o PPU espera na luta (`PS3_POLLTOP=20`): ~10,5 s de cada 20 s em `func_0028DA14` (lr 0x2622EC), o slot
  0x649EC8 que a lista EDGE zera ao terminar (o mesmo de 02/11). Ou seja, a espera do PPU é a cadeia EDGE.
- **v18 (`gow3-fase-v18`): menos CPU na thread do RSX** (ps3recomp, sem mudar os bytes):
  - o live draw busca os vértices com `rsx_vertex_fetch_many` (já testado como igual ao `fetch_one`): de 14,2% para
    4,3% da thread do RSX (prof23);
  - `rsx_vertex_remap_build` com tabela direta quando as referências têm um só base_index e faixa estreita (mesma
    ordem e mapa do hash; `libs/video/tests/test_vertex_remap.c`, 20 mil listas, 0 falhas): de 6% para 3% (prof24);
  - a thread do RSX fica ~44% parada (antes ~33%); o fps da fase não muda (o RSX não está no caminho crítico).
  - 10 inicializações: 1 travada aos 12 s com a assinatura antiga (`identical transfers` img 278921217 pc 0x2554 em
    4 SPUs, como st1e5_11 e stats_aff1_10 em 04/11); mais 10: 0. É um impasse raro do policy module, a investigar.
- `GCM_FLIP_NOW=1` (main.cpp do modelo: conclui o flip logo após a drenagem, sem esperar o tick de 16 ms): A/B
  intercalado 3x3, base 19,6/20,2/17,5 contra 17,5/17,6/18,6. Sem ganho: o tick não está no caminho crítico.
  O fps segue jobs EDGE por quadro x us/job (1270-1480 jobs conforme a cena); desligado.
- Linha do tempo (`PS3_FTRACE=170:3:...`, `scratch\ft_wid.py`): as listas EDGE rodam uma atrás da outra sem
  buraco entre quadros (EDGE1 -> EDGE2 -> EDGE0) e a cadeia fica 94% ocupada (buracos entre jobs ~6%). Os ~21%
  de ntdll da thread de SPU no perfil são de outros workloads que dividem a thread (ModelServer, MSPrep e
  RenderJobs sondam por DMA ~5 s a cada 10 s, `SPU_DMA_POLL_STATS=1`); as EDGE quase não sondam.
- `SPURS_MAXCONT_WID=8:2,9:2,10:2` (cellSpurs.c, novo, desligado): uma lista EDGE em duas SPUs. Mediana 9,5 q/s,
  "jobs" por quadro 1350 -> 4741: o policy module Wws não divide a lista. Confirmado: só o us/job conta.
- `--fundir-trechos 6 --fundir-linhas 700`: a 0xA110 entra na função da 0x9A68 e o laço externo inteiro fica em
  locais (`goto loc_00009A68`, 10 acessos ao ctx). us/job(60s) 38,6/39,0/39,4: neutro (o custo está nos laços de
  dentro, 0x9C48/0x9F90). Padrão continua 4/500.
- Travada rara da abertura: novo `[spurs-dump]` (cellSpurs.c `spurs_debug_dump`, chamado pelo vigia de DMA do
  `spu_dma.h` quando um job repete a mesma transferência por 5 s; até 3 por execução): lanes e workloads. Em 30
  inicializações com ele, 0 travadas (agora 1 em 50). O dump que saiu (sem trava) mostra as 5 lanes no PM Wws
  sondando as mesmas EAs da trava (0x70A6E100, 0x7150D800, 0x70A74480, 0x70A68200) e nenhum workload sem lane
  pronto: não é falta de lane. Na trava quem não entrega trabalho está fora das SPUs (PPU/RSX): próximo passo é
  pegar uma com `PS3_POLLTOP=5` junto (onde o PPU está).
  - Pegamos uma (poll50_19, 23 s): o PPU principal em `func_0028DA14` (lr 0x2622EC, à espera da lista EDGE zerar o
    slot do quadro) e as 5 lanes no PM Wws (wids 1, 7, 8, 3, 4) relendo suas listas, nenhum workload pronto sem
    lane. Impasse "PPU espera o fim da lista / a lista espera o PPU". O vigia agora também imprime o wid (LS
    0x1DC), o LSA e os 128 bytes da linha relida, para a próxima.
- **v19 (`gow3-fase-v19`): `-pre-RA-sched=list-burr` nas fontes SPU** (padrão do `--spu-opt`). Instruções nos jobs
  (`scratchpad\spillcnt.py`, 8 funções quentes): 32,5% acessos à pilha -> 30,6%. A/B intercalado 3x3: us/job
  39,6/38,9/37,2 contra 39,9/38,8/38,8, medianas 17,85/19,0/19,65 contra 16,2/18,8/17,1 (~2%). 50 inicializações:
  0 travadas. Sem efeito: `-enable-misched=false` (pior), `-regalloc=pbqp` (41,5% de pilha), `-misched=ilpmin`
  (31,0%), `-enable-ipra`, `-exhaustive-register-search` (iguais). O derramamento é estrutural: 16 registradores
  AVX2 no Ryzen 9 5950X (sem AVX-512), 25% das amostras dos jobs na pilha e 12% em cópias de registrador.
- **v20 (`gow3-fase-v20`): `--spu-vivos seguro` (padrão)**: o `spu_reg_locals.py` gravava de volta em `ctx->gpr`
  todo local escrito em cada saída, o que mantinha vivos temporários de laço até o teste de saída. A passagem nova
  (ps3recomp `tools/spu_live_flush.py`, testes em `tools/test_spu_live_flush.py`) faz vivacidade de trás para frente
  sobre o módulo inteiro e só grava os registradores vivos no destino (`SPU_DIRECT` para função do módulo: o que está
  vivo na entrada dela; retorno: tudo). Instruções nas 8 funções quentes: 15.160 -> 13.872, acessos à pilha
  4.632 -> 4.193. A/B intercalado 3x3 (06/11): us/job(60s) 37,9/39,1/39,8 (v19) contra 38,1/37,5/38,1 (~-2,5%);
  medianas misturadas (cenas com mais jobs por quadro nas execuções da v20).
  - O modo `abi` (num retorno só r0-r3 e r80-r127 vivos) corta mais (pilha 3.617), mas **trava a abertura sempre**,
    com a mesma assinatura da travada rara (img 278921217 pc 0x2554, 5 lanes relendo 0x70A6E100 etc.): algum
    retorno do PM Wws/EDGE usa registrador volátil como saída. Pista para a travada rara: ela pode ser um valor de
    registrador perdido nesse caminho, não uma corrida do agendador.
  - 50 inicializações da v20: 0 travadas. `--spu-vivos abi-jobs` ("abi" só nos módulos de job) também trava (6/6);
    bissecção por módulo (`GOW3_VIVOS_ABI_MODS`, `scripts_locais\bissec_*.sh`): só o job baf5d88 trava, mas a análise
    mostra chamadas que leem registradores voláteis (r4-r79) depois do retorno em todos os módulos (código à mão
    do EDGE devolve resultados fora da ABI): o "abi" fixo é inseguro mesmo onde abre. `abi-auto` (por função: tudo
    vivo nos retornos de quem tem chamador que lê volátil, `spu_live_flush.abi_returns`) corta quase nada a mais
    (pilha 4.193 -> 4.127) e ainda trava (retorno das entradas do job ao PM). Fica o "seguro"; os outros modos só
    para estudo.
  - Perfil da v20 (`logs\rodar_06nov_prof25.log`, mapa `logs\vivseguro.map`, us/job(60s) 37,3): plano, o maior é
    0x6C10 com 4,5%; depois 0x9A68 4,2%, 912f:0x52A4 3,3%, 0xFA78 3,3%, 0xF428 3,3%, 912f:0x4C48 2,5%, 0x7D78 2,3%.
    Módulos: 14561 44,6%, 2be92eb 27,6% (espalhado), 912f 14,9%. Cada núcleo nativo novo rende 1-2%.
  - Núcleo do laço de luzes 0x9C48 (local: `edge_nativo\gow3_edge_luzpt.h`, AVX com os dois grupos de 4 vértices,
    faz as voltas menos a última e deixa a última ao traduzido): exato no modo sombra (2,1 milhões, 0 diferenças), mas
    neutro no A/B (us/job 38,2 contra 38,3): a maioria das chamadas tem 2-3 luzes (n=1..4) e o gancho grava e relê
    ~80 registradores locais na entrada. Fora do ganchos.json. Lição: núcleo só vale para laços longos ou com o
    gancho fora do caminho dos registradores locais.
- `spu_shufb` (ps3recomp `spu_helpers.h`): os seletores especiais (0xC0-0xDF -> 0xFF, 0xE0-0xFF -> 0x80) saem
  de um `pshufb` numa tabela de 16 bytes indexada pelo nibble alto (4 instruções e 2 constantes no lugar de 7 e 3;
  `SPU_SHUFB_SPECIAL_CMP` volta à forma antiga). `tests/test_spu_shufb.c`: 200 mil casos iguais, SSE4.1 e AVX2.
  `shufb` é a operação mais frequente nas funções quentes (167 nas seis maiores; ~12 instruções x86 cada com
  máscara variável). A/B 06/11: us/job(60s) 37,6/37,3/37,6 contra 37,6/37,2 (v20): neutro; fica (exato e menor).
  - Na mesma série, uma travada rara na v20 (`rodar_06nov_sl_vivseguro_2`): mesma assinatura (img 278921217 pc
    0x2554, wids 5 e 7 em lsa 0x00D00), e a linha de 128 bytes relida está **toda em zero**: o PM espera a lista
    que o PPU ainda não escreveu. Sem `PS3_POLLTOP` nessa execução, não se sabe onde o PPU estava.
- **`dcbz` do PPU coerente** (ps3recomp `tools/ppu_lifter.py`): era traduzido como `memset(vm_base+ea, 0, 128)`,
  por fora do `VM_WRITE_COH`. Numa linha que uma SPU reservou (GETLLAR), não tomava a trava de linha nem avisava a
  SPU (evento LR), e um PUTLLC em andamento podia gravar sua cópia velha por cima: uma escrita perdida, compatível com
  a lista toda em zero da travada rara. Agora são 16 `vm_write64(ea + k, 0)` (caminho rápido em linha sem reserva).
  O jogo tem 4 (`ppu_recomp_073.cpp`, 0x2E9290/0x2E98A0/0x2E98E0). 100 inicializações de 55 s: **0 travadas** (antes
  ~1 em 50-70; 100 limpas por acaso teriam ~19% de chance). Não prova, mas fica no padrão.
- **Limites do float aproximado (07/11): o custo aparente era falso.** Builds de estudo (`spu_helpers.h`,
  `-DSPU_AX_TESTE_SEMCLAMP/SEMAXI/SEMRES=1` via `--spu-opt=`): sem nenhum limite ou sem os das entradas (`SPU_AXI`)
  o us/job(60s) cai de ~37 para ~31,7 e a mediana sobe a ~23 q/s, **mas a fase fica amarela** (NaN; quadro 9600 em
  `quadros_semaxi`): o EDGE usa float sobre máscaras inteiras (0xFFFFFFFF, resultados de comparação; p.ex. `fnms`
  na 0xFA78) e, sem o limite, joga fora trabalho de verdade. Sem os limites dos resultados: pior (39,7).
  - `-DSPU_AX_TESTE_CONTA=1` (conta os operandos que o limite muda, por linha; `spu__axi_hit` em spu_coherency.c):
    ~21 milhões em 192 pontos numa execução (EDGE 0x14561 linha da 0xFA78 com as 4 faixas, 6 milhões). Esses
    builds travam a abertura sempre aos ~13 s, com a assinatura da travada rara (também com o dcbz corrigido):
    a travada é uma corrida que certas mudanças de tempo tornam determinística.
  - `spu_float_inputs.py`: `and`/`andc` com um operando na faixa e constantes `il/ilh/ilhu/fsmbi` sem expoente
    255 passam a contar como "na faixa" (exato): limites do EDGE 3.802 -> 3.473; A/B neutro (37,6/37,9 contra
    38,4); fica no padrão. `--float-ls` (estudo, desligado): leituras da LS e movimentos de palavras
    (`shufb/selb/rot*`) marcados `SPU_AXL` (assumidos na faixa; `-DSPU_AXL_NOCLAMP=1` tira o limite): 1.560 a
    menos e nenhum ganho (37,7/37,9). Conclusão: os limites não são o gargalo.
- **Travada rara: a cadeia, com um build que trava sempre (07/11).** Os builds com `-DSPU_AX_TESTE_CONTA=1`
  travam a abertura aos ~13 s em toda execução (ferramentas novas: `PS3_PEEK=<ea>[,...]` imprime 16 bytes de cada
  endereço no relatório do `PS3_POLLTOP` e no `[spurs-dump]`, sem mexer no tempo como os vigias de leitura/escrita).
  1. As SPUs do PM Wws relêem a linha da lista do workload Wws_Job/ModelServerPrep (dados em 0x70A74400), toda em
     zero: quem a preenche é a thread principal do PPU (0x2E91FC chamada de 0x2EA494; vigia `PPU_WWATCH`). Reler
     5 s também acontece em aberturas normais: sozinho não é a trava.
  2. A thread principal (tid 1) fica no laço 0x1E5264 (`usleep(1000)` enquanto o byte 0x588E51 != 0; o `lr` 0x1E53B0
     do POLLTOP é velho). Esse byte é o "ocupado" de um pedido de carga (`/INTRO/...`), que a thread de carga (tid 11)
     zera em 0x1E65C8 ao terminar (~12,8 s numa abertura normal).
  3. A tid 11 fica na sondagem de 30 us da 0x1E5894: espera o GET do RSX (`[0x20002004]`, registrador de controle)
     ser **igual** ao fim do pedaço de comandos que ela escreveu (dois buffers alternados, `r31` 0xD005DDB8/DDC8,
     alvo = PUT). O GET fica sempre 0x10 antes do PUT, parado no fim do pedaço: `0x00040064 0x10` (SEMAPHORE_OFFSET)
     `0x00040068 0` (SEMAPHORE_ACQUIRE do label 0x10 == 0).
  4. Mas o label 0x10 (0x20000010) já vale 0, e com `GCM_SEMA_ACQUIRE_MS=100` o acquire nunca desiste: o andador
     do FIFO não está bloqueado no semáforo por tempo. Falta saber por que ele para 16 bytes antes do PUT (park,
     buraco do Edge ou outra regra do `gcm_rsx_process_fifo_unlocked`).
  5. `GCM_STOPWHY=1` (cellGcmSys.c, novo): toda passada para com `why=flip` -- a regra "um flip por passada" deixa o
     OFFSET/ACQUIRE depois do flip para a passada seguinte. Isso acontece igual no build normal (a thread de carga
     também sonda ali a abertura inteira, 420 mil voltas), então não é o que distingue a trava.
  6. `GCM_FLIP_SYNC_TAIL=1` (novo, desligado): depois do flip, consome os métodos de sincronização (0x64/0x68/0x6C/
     0x50/NOP) e para no primeiro de desenho. O GET passa a chegar ao PUT, mas ao PUT do pedaço seguinte, e a trava
     continua (3 de 3): a thread de carga espera o GET **igual** a uma posição já ultrapassada. Hipótese para a
     próxima: no RSX real o GET aponta para depois do ACQUIRE enquanto ele espera (o comando já foi buscado), e o
     protocolo da carga é "o RSX parou no meu marcador -> eu libero o label"; aqui um ACQUIRE bloqueado publica o
     GET no próprio comando. Mas o label 0x10 estava em 0 nas espiadas: falta pegar quem grava esse label.
  7. Build padrão atual (v20 + dcbz coerente + limites exatos de and/constantes): **50 inicializações, 0 travadas**
     (somadas às 100 do dcbz: 0 em 150; antes ~1 em 50-70). A trava ainda existe nos builds com tempo alterado.
  8. `GCM_SYNC_LINGER_MS=<ms>` (novo, desligado; com `GCM_FLIP_SYNC_TAIL=1`): o GET fica parado N ms no fim da
     cauda de sincronização depois do flip. Com 2 ms o build de teste ainda trava (3 de 3). **Correção do passo 3**:
     a 0x1E5894 é chamada de dentro da própria 0x1E65C8 (retornos 0x1E6794 e 0x1E68D8), antes do `stb 0` que zera
     o "ocupado" de 0x588E51 (perto de 0x1E69AC): a sondagem do GET **é** o bloqueio na trava; no build normal ela
     também gira muito e acaba acertando a igualdade. Hipótese para a próxima rodada: o jogo grava os pedaços dos
     dois fluxos (r31 0xD005DDB8/DDC8) antes de esperar o primeiro, e o GET já passou do alvo quando a espera
     começa; no RSX real algo o segura ali (o ACQUIRE do label 0x10 com outro valor inicial do label, ou o GET
     publicado depois do ACQUIRE enquanto ele espera). Testar: label 0x10 inicial != 0 e quem o libera.
  9. **O ciclo (08/11)**, com `GCM_FLIP_SYNC_TAIL=1`, `GCM_STOPWHY=1` e a impressão da espera: uma só thread (a de
     carga) grava os pedaços e espera; o alvo é sempre o PUT atual, e o GET fica no fim do pedaço anterior. No fim
     de cada pedaço há um JUMP para o seguinte (0x25802B00), mas o andador está noutro lugar: no anel principal
     (IO 0x1BCxxx, PUT 0xA4E800), `why=parked` em JUMPs para si mesmo, um após o outro -- os buracos do Edge que
     um job de SPU remenda depois de escrever a geometria. Ciclo provável: RSX espera o buraco (SPU) -> o job
     (Wws ModelServerPrep) espera a lista da thread principal -> a thread principal espera o "ocupado" da carga
     -> a carga espera o GET chegar ao pedaço dela, que está atrás dos buracos. No hardware a ordem do tempo
     evita isso; aqui um atraso da SPU (os builds de teste mudam o tempo do job 732253) basta. Próximo passo:
     qual job deveria remendar o buraco em 0x1BCxxx e por que ele ainda não rodou (lista vazia ou job atrasado).
  10. `GCM_PARK_GRACE_MS=2000` (o padrão do `rodar` é 1 h) também trava (3 de 3): o buraco não é o elo fixo, o
     andador sai dele. Contradição a resolver: o GET que a thread de carga lê (0x20002004) fica no fim do pedaço
     anterior (0x058xxxxx) enquanto o andador (`STOPWHY`) está no anel principal (0x1BCxxx, PUT 0xA4E800). Parece
     haver dois fluxos de comando (o anel principal e os pedaços da carga, cada um com seu PUT) dividindo um
     registrador de controle no nosso HLE. Próximo passo: `GCM_PUTLOG` com a função que grava o PUT (anel
     principal x carga) e como o libgcm do jogo troca de contexto (`cellGcmSetCurrentBuffer`/contexto próprio).
  11. (08/11) A sequência do PUT na abertura: só a thread de carga, dois pedaços alternados, cada um
     `FLIP` + `SEMAPHORE_OFFSET 0x10` + `ACQUIRE 0` -- a espera de flip do driver do libgcm. `GCM_FLIP_LABEL=1`
     (cellGcmSys.c, novo, desligado): ao executar o flip do FIFO arma o label X do OFFSET/ACQUIRE seguinte com um
     valor != V, solta no próximo vblank (`cellGcmTickVBlank`) e, enquanto o ACQUIRE espera, publica o GET já
     depois dele. Funciona como mecanismo (a carga passa da sondagem do GET e o andador anda um pedaço por
     vblank), mas o build de teste **ainda trava** (3 de 3), agora com a carga noutro ponto (0x1E69AC / buffer
     cheio 0x2AB778 -> 0x2A4BA8). `FC_WATCH=1` (main.cpp do modelo, novo): o laço do `frame_clock` não fica preso.
     O modelo agora liga o amostrador (`PS3_SAMPLE=<ms>`, `PS3_SAMPLE_DRAIN=1`). Sem um depurador com pilha, esta
     linha custa muito; a travada não aparece no build padrão (0 em 150).
- **v21 (`gow3-fase-v21`, 08/11): v20 + `dcbz` coerente + limites exatos de and/constantes.** A/B contra o build
  do dia 7: us/job(60s) 37,2/36,3 contra 38,4/39,3 (ruído). 0 travadas em 160 inicializações somadas. Teste de
  15 min na fase (`logs\rodar_08nov_15min.log`): sem queda, mediana 19,0 q/s, us/job(60s) 37,6, `identical=0`.
  Cópia em `Projetos\versoes\gow3-fase-v21` (exe trocado sobre a v20).
  Mais 50 inicializações da v21: 0 travadas (0 em 210 desde o dcbz). No build de teste que trava sempre,
  `GCM_FLIP_LABEL=1 GCM_FLIP_SYNC_TAIL=1 GCM_SYNC_LINGER_MS=2` juntos: ainda trava (3 de 3).
  Nas fontes SPU da v21, `-mtune=znver3` e `-O3` (com o list-burr): neutros (us/job(60s) 38,1/37,7 e 37,8/38,0 contra 38,2/37,8).
  `GCM_FLIP_LABEL=1` no build normal da v21 (`scripts_locais/ab_env.sh`): us/job(60s) 36,3/37,3 contra 37,9/37,7,
  0 travadas em 20 inicializações, mas numa rodada a fase começou tarde (20 janelas "fora"): a espera de vblank
  em cada flip pode atrasar a abertura. Fica desligado; candidato a padrão se uma série maior não mostrar atraso.
  Mais 3 rodadas: 38,1/38,2/37,6 contra 36,7/37,5/37,9, "fora" 0/3/0 (sem atraso): neutro. Continua desligado
  (não há prova de que evite a travada no build normal).
  Teste de 30 min da v21 na fase (`logs\rodar_08nov_30min.log`): sem queda (quadros até 1.799 s), mediana
  19,9 q/s, us/job(60s) 37,0, `identical=0`.
  Mais 100 inicializações da v21: 0 travadas (0 em 310 desde o dcbz; antes ~1 em 50-70).
  Teste de 60 min da v21 (`logs\rodar_08nov_60min.log`): sem queda (quadros até 3.599 s), mediana 19,2 q/s,
  us/job(60s) 38,1, `identical=0`.
- **09/11 (dois experimentos neutros, nada mudou no build padrão):**
  - **Ruído do A/B:** A/A da v21 (o mesmo exe dos dois lados, 3 rodadas): 38,3/37,0/37,0 contra 37,7/37,6/37,6.
    Sem viés de ordem, mas ~±0,7 us/job por execução: diferença menor que ~1 us/job entre médias de 3 é ruído.
    Para um efeito pequeno, repetir com a ordem invertida (`GOW3_X=0 bash ab_env.sh N pre exe "GOW3_X=1"`).
  - Cache dos trechos `lqd/stqd` do micro-interpretador (`spu_smc_microstep`, os stubs de salvar/restaurar
    registradores que a interrupção do WWS gera em 0x3FEC0; é a parte quente do `spu_indirect_branch` no perfil):
    decodificar uma vez por thread e repetir enquanto as palavras da LS forem iguais. Sem ganho (38,7/38,7/38,4
    contra 36,7/36,6/38,2, só na ordem direta); código desfeito. O laço é ~1% da thread.
  - Núcleo nativo da **0xFA78** (descarte de triângulos; local: `edge_nativo\gow3_edge_tri.h`, referência
    `ref_fa78.inc` de `gera_ref_fa78.py`, sonda `gow3_edge_tri_sonda.h`). O laço trata 4 triângulos por volta em
    pipeline de 3 estágios + 2 voltas de aquecimento: índices (no lugar: a saída r35 é o próprio buffer r11),
    12 vértices, arestas, produto vetorial 2D, face (sinal por r53), área zero, códigos z (or/and) e w (ceqh),
    máscara por `gb`, compactação por tabela e 3 quadwords mesclados no ponteiro, com desvio para a área de
    sobra r63 (0x3F630) quando passa do fim (r61 = fim-0x11/fim-0x21; acontece no fim de quase toda chamada).
    Depois do laço só r43 é lido (0xFD78 e 0xD620 leem r43, r81, r1, r0, r3, r4). O núcleo calcula as máscaras
    sem o pipeline, grava só os bytes mantidos e refaz exatamente a janela de enchimento de trás para frente
    (gravações desviadas deixam o enchimento de gravações anteriores). Modo sombra: 262 mil chamadas, 0 diferenças.
    A/B nas duas ordens: genérico (as mesmas operações SPU) ~2% **pior**; com as máscaras conhecidas (SoA com
    transposta, verificadas a cada chamada) 37,05 contra 37,28 (4 execuções cada): neutro. As chamadas são curtas
    (muitas com 1 grupo) e o custo fixo come o ganho, como na 0x9C48. Fora do ganchos.json.
    Perfil com o núcleo (`logs\rodar_09nov_prof_tri2.log`, mapa `logs\tri2.map`): 1,4% da thread contra 1,5% da
    função traduzida, sem ponto quente (clamps, compares, extrações espalhados). As duas versões parecem presas às
    mesmas 12 leituras de vértices espalhados por grupo, não às contas.

**Próxima ação exata (05/11):** o fps depende do tempo de SPU das listas EDGE por quadro (`edge_ms.py`,
`us/job(60s)`); o RPCS3 faz ~22 q/s na mesma luta e o nativo ~18 (v15). Caminho que está rendendo: núcleos nativos
do job EDGE (`<trabalho>\edge_nativo`, ganchos.json, sempre com o modo sombra `GOW3_EDGE_SOMBRA=1` até 0 diferenças,
depois A/B `GOW3_EDGE_NATIVO=0`). Perfil da v15 (`logs\rodar_05nov_prof21.log` com `logs\prof21.map`): 0x9A68 6,9%
(dois laços de luz, 0x9C48/0x9F90, ~130 contas por volta), 0x6C10 4,9% (empacotamento dos vértices: muitas máscaras,
difícil), 0xFA78 3,7% (descarte de triângulos, D640 no port), 0xF428 3,3% (projeção com códigos de recorte, pipeline
de 2 voltas; D250 no port, outra versão), o próprio núcleo do skinning 3,5% (atalho de permutação das máscaras em
teste), módulo 912f ~14% (testes de caixas, cheio de desvios). Os laços do port do Ascension se acham pelo
`alinha_edge.py` (cópias dos scripts de medição em `<trabalho>\scripts_locais`: ab.sh, boot.sh, prof_*.py, rpcs3_medir.ps1...). O teste do controle (Switch 2 Pro pelo Steam,
v14+) fica para o Celso.

**11/11: código do Arnaldo e gravação/reprodução de jobs (em andamento).**
- Revisados: ps3kit `ascension-perf` (130 commits novos até 10/11, quase todos no motor Vulkan próprio dele), o
  README novo do gow-ascension-pc dele (três módulos de geometria do EDGE inteiros em código nativo, conferidos
  contra jobs gravados do jogo) e o otavix010. Desde 11/11 o código do ps3kit pode ser copiado (permissão do
  Arnaldo, via Celso), mas fica só local até ele permitir publicar: arquivos `runtime/spu/*_ps3kit.c`, que o
  `gow3_build.py` põe direto no exe quando existem e que não entram no `ps3recomp-gow3.patch`.
- `SPU_IB_HIST=1` (spu_channels.c): desvios indiretos por (imagem, destino). Na fase ~2 milhões/s, quase todos do
  gerenciador Wws (imagem 1: 0x3FEC0, 0xA2C/0xA60, 0x1Bxx-0x2Fxx), não dos módulos de job: o atalho local de
  desvios indiretos do Ascension (`SPU_IBL`) não renderia aqui. Na thread do EDGE o código dos jobs é ~49%, o
  despacho ~5% (com cache).
- Gravação de jobs `SPU_JOBCAP=<dir>,<imagem>,<entrada>[,max[,pular]]` (`runtime/spu/spu_jobcap.c`, formato GJC1)
  e reprodução `SPU_JOBREPLAY=<dir>[,reps[,primeiro[,quantos]]]` (`spu_jobreplay.c`, chamada pelo main.cpp do
  modelo antes do jogo). Achados: no despacho o `image_id` é composto (406522816) e o `resident_ovl` é 0, então o
  job é reconhecido pela função de entrada (`spu_lookup(0xD200, 206)` para o EDGE `jobmod_14561`); os jobs entram
  pelo atalho `SPU_IB_RESIDENT_FAST` e voltam ao gerenciador por desvio indireto ao endereço de retorno. 64 jobs
  gravados na fase (só 0-2 GETs cada: as entradas já estão na LS). A reprodução **ainda não é válida** (o job
  não faz nenhum DMA e para cedo); em correção com o preparo do ps3kit (policy_mode, retorno pela drenagem).
  - Fim do job: no despacho para `pc == retorno` no mesmo contexto (o job volta por desvio indireto). Estado
    inicial de eventos/interrupções/tags/listas (tag 8) copiado do ps3kit, só local (`spu_jobcap_state_ps3kit.c`).
  - Reprodução com `policy_mode=1`, `status=RUNNING`, retorno original e entrada como o `bisl` do gerenciador
    (`host_depth++`, chamada, `spu_drain_call(retorno)`), como no ps3kit: o job passa a fazer DMAs e o primeiro
    bate com a gravação, mas depois diverge (GET de EA 0x6B00/0x3410; no 3º job sonda o EA 0 na rotina de DMA do
    EDGE em 0x81A0, para a LS 0x3F5A0, sem fim). Comparação DMA a DMA: `[jobreplay]   dma: record N, replay M,
    same K, first: ...`. Hipótese a testar: o decrementador (no ps3kit ele conta leituras na reprodução, para
    duas execuções concordarem) ou o tratador de interrupção do gerenciador disparando com o estado gravado.
  - Envio de 10/11 feito em 11/11 (origin 646f835, novo 39f0167), pelo Celso no terminal (o push automático foi
    bloqueado pelo modo automático do Claude Code).
  - **Reprodução válida nos DMAs (11/11, 13h):** faltavam (1) as transferências atômicas na gravação (o EDGE
    reserva a saída num anel com GETLLAR/PUTLLC; agora gravadas como GET/PUT, como no ps3kit), (2) o decrementador
    (gravado e restaurado) e (3) o código do job como residente: sem `SPU_JOBREPLAY_CODE=444600:4000:D97C` (a região
    verificada do módulo 206) o código ia pelo micro-passo de SMC e pelo interpretador, 300-3.900 us por job. Com
    isso, 12 jobs da fase: **todos os DMAs gravados se repetem na mesma ordem e com os mesmos dados** (PUTs com 0
    bytes diferentes em 11, 8 bytes num), 14-77 us por job (mediana ~19 us; no jogo a média é ~37 us). Resta: 2
    DMAs a mais no fim (do gerenciador, depois do fechamento da gravação), ~750 bytes na LS baixa do gerenciador,
    registradores voláteis e 4-5 entradas curtas no interpretador por job (0x8768, 0xE5A4, 0x5458, 0xA68).
  - **Variabilidade e cobertura (11/11, 14h):** as entradas (GETs gravados) são restauradas antes de cada
    repetição (os PUTs de uma execução, no alocador do anel de saída, mudavam a seguinte e a levavam a esperar um
    label do RSX para sempre) e um job com mais que 2x+16 DMAs da gravação é interrompido (`STALL`). Os 64 jobs
    gravados, 50 repetições, duas execuções: 0 STALL; todos os DMAs iguais à gravação em 55 de 64 (9 com alguns
    bytes de PUT diferentes, a investigar); média 39,6 us por job (o us/job do jogo é ~37); soma das medianas
    2.538 contra 2.527 us (0,4%), diferença por job mediana 1,3%, p90 4,1%. Uso:
    `SPU_JOBREPLAY=<pasta>,50,0,64 SPU_JOBREPLAY_CODE=444600:4000:D97C` (exe com `build_var.sh jobcap`).
  - **`--spu-pn` medido pela reprodução (11/11):** `tools/spu_cc_pn.py` (a partir do `spu_cc_interno.py` do
    otavix010, MIT, e do `SPU_LIFT_PN` do Arnaldo): corpos preserve_none + invólucros; no módulo 206, 1.930 corpos.
    Resultado idêntico ao da base (DMAs e PUTs) em todos os jobs comparados. Tempo, ordem alternada (pn, base, pn,
    base; 64 jobs, 30 repetições): pn/base 0,995 e 0,993 (~0,6%); a primeira medida em ordem fixa dava 0,948 --
    viés de ordem (a primeira execução sai mais lenta): na reprodução também vale alternar. Neutro; fica desligado.

**11/11 (tarde): ponte do RSX do RPCS3 (do ps3kit), em andamento.** O Arnaldo autorizou usar e publicar todo o
código dele (créditos e licenças preservados; a ponte é GPL-2.0, como o RPCS3). Ramos: ps3recomp `gow3-v21`
(501ea679, retrato local da v21 sobre a v0.18.0 4e8f3ca8) e `gow3-rsx` (a ponte); GOWPS3 `rsx-rpcs3`. Com o
ps3recomp em ramo, o patch passa a ser exportado contra a base: `git -C ps3recomp diff 4e8f3ca8`.
- `gpu/` copiada do ps3kit 2e972569 (RSX do RPCS3 1b336f41f recortado, shim, bridge/ps3rsx.h, ps3rsx.cmake),
  submódulos glslang f0bd0257 e asmjit 416f7356. Compila com MSVC + Ninja + Vulkan SDK (instalação pelo winget
  `KhronosGroup.VulkanSDK` precisa da aprovação do UAC pelo Celso). Seleção em tempo de execução: `PS3_RSX=rpcs3`;
  o live draw continua o padrão. No ps3kit a ligação com o runtime fica no main do port (boot_main.cpp).
- Plano do porte (do ps3kit 2e972569 para o nosso ps3recomp, ramo gow3-rsx):
  1. `libs/video/cellGcmSys.c/.h`: o "RSX externo" -- `CellGcmRsxHooks`/`cellGcm_set_rsx_hooks`, `s_rsx` (~31
     pontos: labels em `GCM_RSX_REPORTS` e controle em `CELL_GCM_RSX_CONTEXT+0x40` com a ponte, iomap/iounmap,
     partida no cellGcmInit, o andador de FIFO do runtime desligado, flips por `cellGcm_rsx_event`, buffers de
     exibição, relatórios por `gcm_rsx_report_ea`, `g_spu_put_hook = spu_put_hold_check`); cópia do arquivo dele em
     `scratchpad\ps3kit_cellGcmSys.c`; comparar trecho a trecho com o nosso (o nosso tem os ajustes do GOW3).
  2. `templates/project/main.cpp`: o `ps3rsx_select` do `boot_main.cpp` dele (memória do RPCS3 antes do ELF,
     tratador de falhas `ps3rsx_handle_fault`, `ps3rsx_start` com os callbacks e a janela).
  3. CMake do projeto: `include(gpu/ps3rsx.cmake)` + `ps3rsx_link(GOW3Native <gpu-build> SOURCES main.cpp ...)`
     por uma opção do gow3_build (`--rsx-rpcs3 <pasta do build de gpu/>`).
  4. Compilar gpu/ (MSVC x64, `ninja ps3rsx_flip_smoke`) depois do Vulkan SDK; então os marcos.
  - Feito (11/11, 15h20; ps3recomp `gow3-rsx` affda8fe): passo 1 completo -- `CellGcmRsxHooks` no cellGcmSys.h;
    no cellGcmSys.c `s_rsx`, labels/controle no contexto do RSX, `gcm_rsx_report_ea`, iomap/iounmap, partida no
    cellGcmInit, `g_spu_put_hook` nulo com RSX externo, tick de flip desligado, `cellGcm_rsx_event` (o flip também
    iguala `s_flip_tick_seq`, que o nosso pump exige), andador de FIFO desligado, reciclagem do anel pelo get do RSX,
    buffers de exibição, flip direto e flip na FIFO pelo método 0xE920, 7 funções de relatório. Build normal
    (sem a ponte) compila. glslang/asmjit como submódulos (falta o `.gitmodules`).
  - Passo 2 (a fazer): `GOWPS3/native/game/gow3_rsx_rpcs3.cpp` adaptado do `boot_main.cpp` do ps3kit
    (`ps3rsx_select`: VEH com `ps3rsx_handle_fault`, `vm_base = ps3rsx_init_memory()` NO LUGAR do `alloc_guest_vm()`
    do main.cpp, RSX_LIVE_DRAW=0, `cellGcm_set_rsx_hooks(&hooks)`; `rpcs3_rsx_start`: janela do
    `rsx_null_backend_get_hwnd()` (a mesma do live draw), `ps3rsx_params` com renderer Vulkan, context_addr,
    local_size, `on_event = cellGcm_rsx_event`; flip por `ps3rsx_flip`). Ganchos do runtime dele que o nosso não
    tem e ficam de fora no começo: `g_rsx_hold_kick`, `g_spu_dma_put_copy_hook` (PUTs de SPU com as travas da
    FIFO do RSX), `g_vm_protected_page_hook` (DMA de SPU em página protegida: o VEH cobre). O gow3_build, com
    `--rsx-rpcs3 <build de gpu/>`, põe o arquivo no exe, troca `alloc_guest_vm()` por `ps3rsx_select()` no main.cpp
    gerado e liga por `ps3rsx_link`.

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
