# God of War III no PC: recompilação nativa do PS3

**God of War III (PlayStation 3, BCES00510) traduzido do processador do PS3 para código nativo de PC
com Windows, sem emulador, sobre o [ps3recomp](https://github.com/sp00nznet/ps3recomp).**

Projeto de fã, idealizado e conduzido pelo **Dr. Celso Matos Junior**, desenvolvido com a ajuda do
Claude, a IA da Anthropic.

> [!WARNING]
> **Experimento em andamento: ainda não é uma versão para jogar.** O jogo inteiro é traduzido e compilado
> para um executável de PC, que roda a abertura, os menus e a fase do Poseidon com combate e imagem
> completa, a ~12,5-13 quadros por segundo (o RPCS3 faz ~22 na mesma cena). Salvar, carregar e a progressão
> além da primeira fase ainda não foram validados. Veja [Onde estamos](#onde-estamos).

> [!IMPORTANT]
> **Nenhum arquivo do jogo, firmware ou chave está neste repositório.** Você precisa da sua própria
> cópia do jogo, tirada do seu disco. O EBOOT cifrado é convertido pelo RPCS3 que você já tem
> instalado; este projeto não contém chaves e não contorna proteções. Sem ligação com a Sony
> Interactive Entertainment nem com o Santa Monica Studio. God of War é marca registrada da Sony
> Interactive Entertainment.

---

## Sumário

- [O que é](#o-que-é)
- [Onde estamos](#onde-estamos)
- [Como funciona](#como-funciona)
- [A história, passo a passo](#a-história-passo-a-passo)
- [Resultados no God of War III](#resultados-no-god-of-war-iii)
- [Como usar](#como-usar)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Regras que o projeto segue](#regras-que-o-projeto-segue)
- [Próximos passos](#próximos-passos)
- [Créditos](#créditos)
- [Licença](#licença)

---

## O que é

O PS3 usa um processador muito diferente do PC: o **Cell**, com um núcleo PowerPC (o PPU) e seis
núcleos auxiliares (os SPUs). Por isso o God of War III só roda no PC por emulação, com o
[RPCS3](https://rpcs3.net), que interpreta ou recompila o código do jogo enquanto ele roda.

A **recompilação estática** faz isso uma vez, antes: o código de máquina do jogo é traduzido para
C++, compilado para x86-64 e vira um executável de PC. É o mesmo caminho de projetos como
[God of War: Ascension para PC](https://github.com/arnaldolima1/gow-ascension-pc), Twisted Metal,
Killzone 3 e inFAMOUS 2, todos sobre o ps3recomp.

O repositório tem duas partes:

| Parte | O que é | Onde |
|---|---|---|
| **1. GOW3 PS3 PC** | Aplicativo Windows que roda o jogo sobre o RPCS3 embutido, com interface própria | ramo `gow3-ps3-pc`, [docs/GOW3_PS3_PC.md](docs/GOW3_PS3_PC.md) |
| **2. GOW3 Native** | A recompilação nativa: analisador, testes de tradução, captura de estados reais e o jogo inteiro traduzido e compilado | [`native/`](native/) |

---

## Onde estamos

Atualizado em 18/11/2026.

| Etapa | Situação |
|---|---|
| 1. Ferramentas compiladas | ✔ analisador, testes e orquestrador no CI do GitHub |
| 2. Executável analisado | ✔ 11.482 funções PPU, 184 importações do firmware, 8 programas SPU |
| 3. Código PPU recompilado | ✔ o jogo inteiro compila, sem instrução sem tradução |
| 4. Código SPU recompilado | ✔ os 8 programas embutidos e o *policy module* Wws_Job |
| 5. Runtime inicializado | ✔ |
| 6. Primeiro quadro renderizado | ✔ com o RSX do RPCS3 (ponte `gpu/`, Vulkan) |
| 7. Menu principal | ✔ |
| 8. Gameplay | ◐ a fase do Poseidon com combate, a ~12,5-13 quadros/s; 600 s em combate sem travar |
| 9. Salvamento e carregamento | ○ |
| 10. Jogo completo | ○ |

**Parada atual:** velocidade. O gargalo é a cadeia de jobs EDGE nas SPUs. O desync raro da FIFO do RSX
foi corrigido em 18/11. Estado, instalação, comandos e problemas
conhecidos em [native/game/LEIA-ME.md](native/game/LEIA-ME.md); o histórico em
[native/game/HISTORICO.md](native/game/HISTORICO.md).

---

## Como funciona

```
Sua cópia do jogo (EBOOT.BIN cifrado)
        │  RPCS3 do usuário: rpcs3 --no-gui --decrypt  (o projeto não tem chaves)
        ▼
EBOOT.ELF (PowerPC 64, 5,4 MB) ── SHA-256 conferido: BCES00510 01.00
        │
        ├──► GOW3_Native_Analyzer ── mapeia funções, importações, syscalls, SPUs
        │         │
        │         └─ teste diferencial: cada função traduzida (x86-64) contra o
        │            PowerPC original (Unicorn), com estados sintéticos e estados
        │            REAIS capturados do jogo rodando no RPCS3 (servidor GDB)
        │
        └──► GOW3 Native (native/game/gow3_build.py)
                  ppu_loader → ppu_lifter (11.060 funções em C++) → SPUs + PM Wws_Job
                  → projeto do ps3recomp (runtime, HLE do firmware, Direct3D 12)
                  → clang-cl → GOW3Native.exe → roda e diagnostica
```

### O analisador (`native/analyzer`)

Programa Windows (`GOW3_Native_Analyzer.exe`) que o usuário roda sobre a própria cópia do jogo:

1. **Identifica** o arquivo: formato, cifra, segmentos e SHA-256 da versão.
2. **Gera o EBOOT.ELF automaticamente** pelo RPCS3 do usuário, numa cópia. Guarda o resultado para
   não precisar converter de novo.
3. **Analisa** o código PPU: funções, importações do firmware (NIDs), syscalls, programas SPU,
   grafo de chamadas e funções candidatas.
4. **Recompila** as candidatas com o ps3recomp e o compilador incluído (zig/clang).
5. **Compara** cada função traduzida com o PowerPC original numa CPU de referência (Unicorn,
   derivada do QEMU) a partir dos **mesmos estados iniciais**: todos os registradores, CR, XER, CTR,
   LR e cada byte de memória escrito. Um **teste de mutação** (um erro proposital na tradução)
   prova que a comparação pega erros.
6. **Captura estados reais** (opcional): com o jogo rodando no RPCS3, conecta ao servidor GDB do
   RPCS3, põe um breakpoint na entrada de cada função testada e copia os registradores e as páginas
   de memória que a função usa. Esses estados reais também são comparados.
7. Gera **relatórios HTML e JSON** só com metadados (endereços, contagens), nunca bytes do jogo.

### O GOW3 Native (`native/game`)

`gow3_build.py` faz tudo no computador do usuário: traduz o EBOOT inteiro, monta o projeto do
ps3recomp (runtime, HLE do firmware, Direct3D 12), compila o `GOW3Native.exe` com clang-cl e o roda,
resumindo o log. Em volta dele há ferramentas próprias:

- `lift_pm.py`: recompila o *policy module* SPURS cru (Wws_Job), conferido pela impressão FNV-1a-64;
- `gow3_libsre_lle.cpp`: **LLE seletivo da libsre**. A fila LFQueue do SPURS é ligada à biblioteca
  real do firmware do usuário (que fica só no PC dele), e o resto continua no HLE do ps3recomp;
- `gow3_diag.cpp`: um "cão de guarda" que mostra onde cada thread do jogo está parada;
- `native/ps3recomp-gow3.patch`: correções no runtime (SPURS, tasksets, cellGcmSys).

---

## A história, passo a passo

### Parte 1: GOW3 PS3 PC, o aplicativo sobre o RPCS3 (15/10)

1. Auditoria técnica e protótipo do launcher.
2. `GOW3_PS3_PC.exe` em C++/Win32 com o RPCS3 embutido, compilado pelo GitHub Actions.
3. Instalação opcional do RPCS3 oficial e verificação de compatibilidade do `rpcs3.exe`.
4. Diagnóstico de travamentos e relatórios do CI publicados no ramo `ci-logs`.
5. Correções para o Windows: pasta de dados criada antes do RPCS3 e o Visual C++ pelo instalador
   oficial, como o RPCS3 exige.

### Parte 2: GOW3 Native, a recompilação

**6. Auditoria do ps3recomp e o primeiro teste diferencial (15/10).** Um corpus de funções próprias,
compiladas para PowerPC/Cell, executadas no QEMU (referência) e traduzidas pelo ps3recomp para
Windows x64: **97 de 97 casos idênticos**, no Linux e no Windows.

**7. O analisador, versões 0.1 e 0.2 (15/10).** Identificação, análise, recompilação de 40 funções e
comparação com o Unicorn. Problemas resolvidos no caminho:
- o modelo de CPU do Unicorn;
- o bit CA do XER;
- as conversões `fcti*`;
- o Control Flow Guard do PyInstaller;
- a pilha de 64 MB para o Unicorn;
- um arquivo C de 2,39 GB que o Clang recusava. Passou a 5,9 MB traduzindo só as funções escolhidas.

**8. Primeiro teste no God of War III (0.2.1).** 23 funções idênticas, 3 divergentes. As 3 eram um
**erro real do ps3recomp** (registrador CTR cortado em 32 bits), achado pelo analisador e corrigido
na versão seguinte do ps3recomp.

**9. ps3recomp v0.16 e pesquisa do ecossistema (20 e 21/10).** Leitura dos ports de Bloodborne,
The Last Guardian, Ascension, Naruto e outros
([native/docs/PESQUISA_ECOSSISTEMA.md](native/docs/PESQUISA_ECOSSISTEMA.md)).

**10. Analisador 0.4.x: EBOOT.ELF automático (21 a 27/10).**
- O EBOOT.ELF passou a ser gerado pelo RPCS3 do usuário, com a versão conferida por SHA-256.
- Os 44 patches do Ascension foram mesclados no ps3recomp.
- Proteção no CI contra dados do jogo.
- Teste no CI com o RPCS3 oficial.
- Duas armadilhas corrigidas:
  - o RPCS3 aberto pelo analisador herdava a DLL errada do Visual C++;
  - quando a conversão falhava, o RPCS3 ficava esperando alguém digitar uma KLIC.

**11. Analisador 0.5: memória de teste realista (27/10).** Quatro modos de memória (aleatória,
ponteiros, mista) e a área `.bss` preenchida. Funções que eram inconclusivas passaram a ser
comparadas.

**12. Analisador 0.6: estados reais do jogo (27 e 28/10).**
- **Captura pelo servidor GDB do RPCS3**, testada antes de ponta a ponta com o QEMU.
- **64 casos sintéticos** por função.
- **Endereços de 32 bits como no PS3.** Ponteiros estendidos com sinal (`0xFFFFFFFF_D0xxxxxx`)
  acessam `0xD0xxxxxx`, então endereços acima de 4 GB passaram a espelhar a página de 32 bits. Isso
  também evitou um erro que travava o servidor GDB do RPCS3.
- **A thread certa:** no Interpreter, o RPCS3 só atualiza o endereço atual das threads nos desvios.
  A thread que bateu no breakpoint agora vem do comando `qC`.
- **Resultado:** os primeiros estados reais do God of War III deram **idênticos ao PowerPC original**.

**13. ps3recomp v0.18 e o orquestrador do jogo inteiro (28/10, manhã).**
- A v0.17/v0.18 do ps3recomp incorporaram boa parte das correções vindas dos ports de God of War HD
  e Ascension.
- `native/game/gow3_build.py` traduz, compila e roda o jogo inteiro. Foi testado no CI do Windows
  com um programa de teste.

**14. O jogo inteiro no PC (28/10, tarde, em sessão local do Claude no computador do autor).**
- As 11.060 funções foram traduzidas e o `GOW3Native.exe` (117 MB) compilado com clang-cl em
  cerca de 5 minutos.
- Os 8 programas SPU e o *policy module* Wws_Job foram resolvidos.
- A inicialização passou por módulos, SPURS Big/Little, threads FIOS, pacotes PSARC, GCM e a janela
  D3D12.
- A LFQueue foi resolvida por LLE seletivo da libsre, e com isso:
  - o Edge Zlib descompactou os dados (1.510 blocos);
  - subiram as threads de áudio e os 12 workloads Wws_Job;
  - o jogo abriu o primeiro vídeo.
- Duas correções no cellGcmSys:
  - a tabela de offsets ficava desatualizada (`put = 0xFFFFFFFF`);
  - uma varredura de 4 GB travava a janela.
- O laço de quadros chegou a ~80 flips/s, ainda com a tela preta.
- O título BCES00510 passou a ser lido do PARAM.SFO.

**15. Tela de boot e o SPURS do motor da Santa Monica (28/10, noite).**
- A trava da tela de boot vinha do gabarito: o RPCS3 do autor tinha patches da comunidade ligados ("Skip
  intro", "Disable MLAA"). Sem eles, o RPCS3 também cria a `IntroLoaderThread`, e a comparação passou a
  ser feita sem patches.
- Com o título certo e um save do usuário, a tela de boot termina sozinha aos ~13 s, como no RPCS3.
- Entraram no SPURS as tarefas Task2 (as 5 tarefas MLAA) e o *workload flag*, com o receptor por troca
  atômica e o kernel escalando o receptor como o RPCS3.

**16. Primeira imagem, abertura e menu principal (29/10).**
- O quadro passou a fechar: RsxSync, MLAA e Edge completam a volta, e o jogo sai da espera do buffer
  triplo.
- O vídeo do logo é decodificado inteiro pelo FFmpeg (LGPL), com as AUs retidas no `cellVdec` quando a
  fila está cheia.
- O *live draw* passou a ser o desenho padrão: aparecem o logo da Santa Monica e a abertura da história
  com legendas em português.
- **PR do Arnaldo Lima:** o fim do código passou a vir das seções executáveis do ELF. Antes, ~7.800 trechos
  de dados eram lidos como funções; agora são 11.482 funções reais, executável de 58 MB e compilação de
  ~3,5 min.
- Comparação detalhada com o *ps3kit* ([native/docs/PS3KIT_COMPARACAO.md](native/docs/PS3KIT_COMPARACAO.md))
  e cinco ramos de correção enviados ao ps3kit, um por correção.
- Com o patch "Skip any videos with X" da comunidade do RPCS3 (autor: illusion), aplicado numa cópia local
  do EBOOT, e o X apertado por script, **o menu principal aparece em português**.

**17. Gameplay e velocidade (30/10 a 18/11).**
- O RSX do RPCS3 entrou como renderizador, pela ponte `gpu/` do *ps3kit* do Arnaldo Lima (GPL-2.0): menus e
  a fase do Poseidon com imagem completa.
- Executor próprio das listas de jobs Wws, tradutor de SPU com reprodução exata dos jobs EDGE e núcleos
  nativos medidos em A/B: de ~9,5 para ~12,5-13 quadros reais por segundo na fase.
- Travadas do RsxSync e do label 0x51 corrigidas (relatórios do RSX dentro do lock de linha). Desync raro da
  FIFO do RSX corrigido em 18/11: a SPU agora grava o salto-para-si de cada linha por último, como o DMA do
  console (0 desyncs em 40 cenas de 330 s, antes ~2 em 60; custo no ruído).
- Detalhes, medidas e o que deu errado em [native/game/HISTORICO.md](native/game/HISTORICO.md).

---

## Resultados no God of War III

Teste diferencial de 40 funções candidatas: código traduzido contra o PowerPC original.

| Versão | Casos | Idênticas | Divergentes | Inconclusivas |
|---|---|---|---|---|
| 0.2.1 | 640 | 23 | 3 (erro do CTR no ps3recomp antigo) | 14 |
| 0.4.1 | 640 | 26 | 0 | 14 |
| 0.5.0 | 640 | 28 | 0 | 12 |
| 0.6.x | 2.600 | 30 | 0 | 10 |

- **Zero divergências** desde a 0.4.1: em tudo o que pôde ser comparado, a tradução fez exatamente o
  que o PowerPC faz.
- **Estados reais do jogo:** as funções `00364AB8` e `0009FA9C` deram idênticas em 4 de 4 estados
  capturados do jogo rodando.
- "Inconclusiva" quer dizer que os dois lados falharam no mesmo ponto em todos os casos. Não é erro,
  mas também não prova nada.
- Estados sintéticos provam a tradução das funções testadas, não que o jogo funcione.

---

## Como usar

### Analisador (Windows)

1. Baixe o ZIP do `GOW3_Native_Analyzer` gerado pelo GitHub Actions (workflow *Native analyzer*).
2. Abra `GOW3_Native_Analyzer.exe`, escolha a pasta do jogo (a que contém `PS3_GAME`) e clique em
   **Analisar**. O RPCS3 é achado sozinho.
3. Para os estados reais:
   - no RPCS3, crie uma configuração própria para o jogo com o **PPU Decoder em Interpreter (static)**;
   - abra o jogo;
   - no analisador, clique em **Capturar estados reais e analisar…** e continue jogando.

Detalhes: [native/analyzer/LEIA-ME.txt](native/analyzer/LEIA-ME.txt).

### GOW3 Native (o jogo inteiro)

Pré-requisitos: Visual Studio 2022 Build Tools com clang-cl, CMake, Ninja, Python 3.12, Vulkan SDK e o
ps3recomp no commit de [native/PS3RECOMP_COMMIT.txt](native/PS3RECOMP_COMMIT.txt), com os três patches
`native/ps3recomp-gow3.patch`, `native/ps3recomp-gpu-1.patch` e `native/ps3recomp-gpu-2.patch` (eles já
contêm o `ps3recomp-elfv1.patch`; não o aplique à parte). O passo a passo completo, com a ponte do RSX,
está em [native/game/LEIA-ME.md](native/game/LEIA-ME.md#instalação).

```powershell
python native\game\gow3_build.py --jogo "<pasta do jogo>" --ps3recomp <ps3recomp> --trabalho <pasta de trabalho> --spu-dir <spu_dir> --lle-libsre <lle> --ffmpeg <ffmpeg> --rsx-rpcs3 <gpu-build> --pular-videos
```

Os passos dos SPUs, do *policy module* e da libsre estão em
[native/game/LEIA-ME.md](native/game/LEIA-ME.md).

---

## Estrutura do repositório

```
native/
  analyzer/        GOW3_Native_Analyzer (Python): análise, teste diferencial, captura GDB, relatórios
  game/            GOW3 Native: orquestrador do jogo inteiro, SPUs, LLE da libsre, diagnóstico
  ppu_diff/        corpus PowerPC + QEMU: teste diferencial do ps3recomp (97/97)
  tools/           ferramentas (guarda contra dados do jogo, PRX, mapas, rastreio)
  docs/            pesquisa do ecossistema, auditoria do ps3recomp, comparação com o ps3kit, origem dos componentes
  PS3RECOMP_COMMIT.txt, ps3recomp-elfv1.patch, ps3recomp-gow3.patch
app/, cmake/, packaging/, tools/, docs/   GOW3 PS3 PC (o aplicativo sobre o RPCS3)
.github/workflows/                         CI: analisador, recompilação, guarda de dados
```

---

## Regras que o projeto segue

- **Só a sua cópia.** Nenhum arquivo do jogo, firmware, chave ou código gerado a partir do jogo vai
  para o repositório. A guarda `native/tools/check_no_game_data.py` roda a cada envio e bloqueia
  EBOOT, SELF/ELF de PS3, PSARC, PKG, capturas e saídas da análise.
- **Sem contornar proteções.** O EBOOT cifrado é convertido pelo RPCS3 do próprio usuário. A
  libsre usada no LLE vem do firmware do usuário e fica só no computador dele.
- **Sem resultados inventados.** Compilar não é funcionar. "Idêntica" quer dizer "comparada e igual
  nos estados testados", e os relatórios sempre dizem o que não foi provado.
- **Testes públicos só com programas sintéticos.** A análise do jogo de verdade roda no
  computador do usuário.
- **Licenças respeitadas** e crédito a todo componente de terceiros.

---

## Próximos passos

1. **Velocidade:** a cadeia de jobs EDGE nas SPUs é o caminho crítico. Cada 1% a menos no job vira quase 1% a
   mais de quadros.
2. **Progressão real, salvar e carregar**, e a instalação validada fora do ambiente de desenvolvimento.
3. **Medida do RPCS3 na mesma cena**, com o estado da máquina registrado.

---

## Créditos

- **[ps3recomp](https://github.com/sp00nznet/ps3recomp)**, de sp00nznet e colaboradores (MIT): o
  recompilador, o runtime e as bibliotecas do sistema.
- **[God of War: Ascension para PC](https://github.com/arnaldolima1/gow-ascension-pc)**, de Arnaldo
  Lima e colaboradores (MIT): o modelo deste projeto e a principal referência técnica.
- **[RPCS3](https://github.com/RPCS3/rpcs3)** (GPL-2.0): o emulador usado como gabarito, conversor
  do EBOOT e servidor GDB para os estados reais. Também está embutido no aplicativo GOW3 PS3 PC.
- **[Unicorn Engine](https://www.unicorn-engine.org)** (GPL-2.0) e **[QEMU](https://www.qemu.org)**:
  as CPUs PowerPC de referência.
- **[Zig](https://ziglang.org)** (MIT): o compilador que vem dentro do analisador.
- **[God of War III Remastered for PC](https://github.com/FelipePrado0/gow3_pc)**, de Felipe Prado
  (GPL-2.0): inspiração para o launcher.
- Desenvolvido com a ajuda do **Claude** (Anthropic).

Componentes de terceiros do aplicativo: [THIRD_PARTY.md](THIRD_PARTY.md). Do analisador:
[native/analyzer/THIRD_PARTY.txt](native/analyzer/THIRD_PARTY.txt).

---

## Licença

**GPL-2.0-only**: veja [LICENSE](LICENSE). Vale para o código deste repositório, não para o jogo.
