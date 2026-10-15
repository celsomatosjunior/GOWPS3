# Auditoria técnica: GOW3 PS3 PC

> **Atualização (versão 0.2.0):** o protótipo em Python que dependia de um RPCS3 instalado à parte foi substituído pelo aplicativo `GOW3_PS3_PC.exe` (C++/Win32), que leva o RPCS3 compilado dentro do pacote. As referências abaixo à pasta `launcher/` descrevem a versão 0.1.0. A integração com o RPCS3 (linha de comando, `RPCS3_CONFIG_DIR`, chaves de configuração) foi mantida, e agora é conferida por `tools/check_rpcs3_contract.py`.

**Data:** 15/10/2026
**Código analisado:**
- RPCS3, commit `4d5def5` (15/10/2026)
- gow3_pc (Felipe Prado), commit `015ffd8` (15/10/2026)

Tudo o que este documento afirma sobre os dois projetos foi conferido no código clonado. Os caminhos de arquivo citados existem nesses commits. O que não pôde ser testado nesta etapa está marcado como **não testado**.

---

## Resumo

1. **O modelo do gow3_pc não se repete no PS3.** O gow3_pc roda o código x86-64 do jogo de PS4 direto na CPU do PC. O God of War III de PS3 foi feito para o processador Cell: um PPU PowerPC big-endian e 6 SPUs com conjunto de instruções próprio. Por isso a tradução de instruções (recompilação PPU/SPU com LLVM) é **obrigatória e permanente**, como você já tinha previsto.
2. **O RPCS3 já tem quase tudo o que as fases 3 e 4 pedem.** Cache persistente de código PPU/SPU, cache de shaders em disco, compilação assíncrona, FSR 1, RCAS, escala de resolução, filtro anisotrópico, VSync, limite de FPS e overlay de desempenho já existem. O ganho realista do projeto está em **perfil e configuração dedicados, launcher, diagnóstico e patches específicos do jogo**, não em reescrever o emulador.
3. **Há um conflito jurídico que precisa de uma decisão sua antes da fase de fork.** O RPCS3 contém, no próprio código, chaves criptográficas usadas para decifrar o executável do jogo (`rpcs3/Crypto/key_vault.h`, `key_vault.cpp`, `unself.cpp`). Isso bate de frente com duas regras do projeto: "não incorporar chaves criptográficas" e "não contornar DRM". Um fork redistribuído do RPCS3 **inclui essas chaves**. O protótipo entregue agora evita o problema: ele **não inclui nem modifica o RPCS3**, apenas comanda o RPCS3 que o próprio usuário instalou. Veja a seção 4.
4. **A primeira tarefa já está implementada e testada.** O launcher está em `launcher/`, com 30 testes automatizados passando. Cinco desses testes conferem no código-fonte do RPCS3 cada chave de configuração, cada valor, cada opção de linha de comando e cada mensagem de log que o launcher usa.

---

## 1. Comparação das arquiteturas PS3 e PS4

| | PS4 (base do gow3_pc) | PS3 (este projeto) |
|---|---|---|
| CPU | 8 núcleos AMD Jaguar, **x86-64**, little-endian | **Cell**: 1 PPU PowerPC 64 bits (2 threads, VMX/AltiVec), **big-endian**, mais 8 SPUs, dos quais 6 ficam disponíveis para o jogo |
| Código do jogo no PC | Roda **direto** na CPU (`src/probe.c` carrega a imagem e pula para o código original) | Precisa ser **traduzido**: PPU→x86 (`PPUTranslator.cpp`, LLVM) e SPU→x86 (`SPULLVMRecompiler.cpp` ou `SPUASMJITRecompiler.cpp`) |
| Coprocessadores | Nenhum equivalente | SPUs com 256 KB de memória local cada, alimentados por DMA (MFC). Sincronizar isso com o PPU é o maior custo da emulação |
| GPU | AMD GCN, comandos PM4/GNM. O gow3_pc usa o núcleo de vídeo do shadPS4 para Vulkan (`gpu/shadps4`) | **RSX** (derivado da NVIDIA G70), comandos GCM/NV47. No RPCS3: `Emu/RSX`, com backends Vulkan e OpenGL |
| Memória | 8 GB GDDR5 unificada | 256 MB XDR (principal) + 256 MB GDDR3 (vídeo), espaços separados |
| Sistema | Bibliotecas do SO trocadas por um runtime próprio (`src/runtime_*.c`, cerca de 30 arquivos) | Kernel LV2 (`Emu/Cell/lv2`, cerca de 44 mil linhas) e módulos do sistema em HLE (`Emu/Cell/Modules`, cerca de 134 mil linhas) ou LLE (bibliotecas do firmware) |
| Executável | ELF x86-64 que o usuário extrai do próprio console | `EBOOT.BIN` em formato **SELF cifrado**. O RPCS3 decifra na hora de carregar (`Crypto/unself.cpp`) |
| Firmware | Não é necessário | **Necessário**: o RPCS3 recusa o boot sem `dev_flash/sys/external/liblv2.sprx` (`Emu/System.cpp`, `game_boot_result::firmware_missing`) |

**Consequência prática.** O gow3_pc consegue 144 FPS em média porque não traduz instruções. No PS3, o gargalo é a CPU: traduzir e sincronizar os SPUs. O God of War III é conhecido por usar muito os SPUs (por exemplo, o antisserrilhamento MLAA era feito neles). Por isso **não é prometido nenhum ganho de desempenho** antes de medir.

**O que dá para aproveitar do gow3_pc** (licença GPL-2.0-or-later, compatível com a GPL-2.0-only do RPCS3):
- as **ideias** do launcher: perfil separado, backup de saves, diagnóstico do log, detecção de Vulkan (`launcher/gow3_vulkan.py`), mensagens de erro claras;
- a **disciplina de validação**: patches só são aplicados ao executável com hash conferido.

O runtime (`src/`) e o núcleo shadPS4 **não servem** para o PS3.

---

## 2. Mapa dos componentes relevantes do RPCS3

As contagens de linhas incluem `.cpp`, `.h` e `.hpp` de cada pasta, com subpastas.

| # | Área | Onde fica | Classificação |
|---|---|---|---|
| 1 | **PPU**: intérprete, análise, recompilação | `Emu/Cell/PPUThread.cpp` (6,1 mil linhas), `PPUTranslator.cpp` (5,6 mil), `PPUInterpreter.cpp`, `PPUAnalyser.cpp`, `PPUModule.cpp` (carrega ELF/PRX e liga os módulos HLE) | **Obrigatório** |
| 1 | **SPU** | `SPUThread.cpp` (7,6 mil), `SPUCommonRecompiler.cpp` (10 mil), `SPULLVMRecompiler.cpp` (10,5 mil), `SPUASMJITRecompiler.cpp`, `SPUInterpreter.cpp`, `MFC.cpp`, `RawSPUThread.cpp` | **Obrigatório**. O ASMJIT e os intérpretes são candidatos a ficar só em compilações de depuração, **depois** de provar que o LLVM basta para o GOW3 |
| 2 | **LLVM** | submódulo `3rdparty/llvm`, `Utilities/JITLLVM.cpp`, `JITASM.cpp`, `JIT.h` | **Obrigatório** |
| 3 | **Sincronização do Cell** | reservas de memória (`Emu/Memory/vm_reservation.h`), `lv2/sys_spu.cpp`, `sys_event*.cpp`, `sys_lwmutex.cpp` e outros. Opções em `system_config.h`: `SPU Block Size`, `Preferred SPU Threads`, `Accurate SPU DMA`, `SPU loop detection`, `Max SPURS Threads` | **Obrigatório**. As opções podem ser ajustadas por perfil |
| 3 | **SPURS** (agendador de tarefas SPU usado pelos jogos) | `Emu/Cell/Modules/cellSpurs*.cpp` | **Obrigatório** |
| 4 | **RSX com Vulkan** | `Emu/RSX/RSXThread.cpp`, `RSXFIFO.cpp`, `Common/` (cache de texturas e superfícies), `Program/` (descompiladores de shader), `VK/` (33 mil linhas) | **Obrigatório** |
| 4 | RSX com OpenGL | `Emu/RSX/GL/` (18 mil linhas) | **Simplificável**: pode sair do build do produto, ficando só no RPCS3 original para comparação |
| 4 | Overlays nativos (inclui o overlay de desempenho) | `Emu/RSX/Overlays/` | **Reutilizar** |
| 5 | **Memória** | `Emu/Memory/vm.cpp` e `vm_*.h` (4 mil linhas) | **Obrigatório** |
| 6 | **Shaders** | `Emu/RSX/rsx_cache.h` (classe `shaders_cache`, grava em `<cache>/<serial>/shaders_cache/`). Modo assíncrono com intérprete: `Shader Mode` | **Reutilizar** |
| 6 | Cache de código PPU/SPU | PPU: pasta `ppu-<sha1>-<nome>/` (`PPUThread.cpp`). SPU: `spu-<bloco>-v1-tane.dat` (`SPUCommonRecompiler.cpp`) | **Reutilizar**. *O "cache persistente de código recompilado" da Fase 3 já existe* |
| 7 | **Áudio** | `Emu/Audio/` (Cubeb, FAudio, XAudio2), `cellAudio.cpp`, `cellAdec.cpp`, `cellAtrac*.cpp` | **Obrigatório**. Basta um backend no Windows (XAudio2 ou Cubeb) |
| 7 | **Controles** | `rpcs3/Input/`: XInput, DualSense, DS4, DS3, SDL, teclado, mouse, evdev, além de PS Move, Wiimote, skate e câmera | **Simplificável**: PS Move, Wiimote, skate, câmera e guitarras não são usados pelo GOW3 (**falta provar com log de chamadas**) |
| 8 | **Arquivos e saves** | `Emu/VFS.cpp`, `vfs_config.h`, `lv2/sys_fs.cpp`, `Modules/cellSaveData.cpp`. Saves em `dev_hdd0/home/00000001/savedata/` | **Obrigatório** |
| 9 | **Firmware e serviços** | Verificação do firmware em `Emu/System.cpp`. Leitura da versão em `util/sysinfo.cpp` (`dev_flash/vsh/etc/version.txt`). Instalação: opção `--installfw` | **Obrigatório**: o usuário instala o próprio PS3UPDAT.PUP, baixado do site da Sony |
| 9 | **Criptografia** | `rpcs3/Crypto/` (12 mil linhas): `key_vault`, `unself`, `unedat`, `unpkg` | **Conflito jurídico** (seção 4) |
| 9 | Rede/PSN | `Emu/NP/` (56 mil linhas), `lv2/sys_net*` | **Simplificável em parte.** O `sceNpTrophy` (troféus) e a inicialização do NP provavelmente são chamados pelo jogo e **precisam continuar**. O resto do RPCN e da rede pode ser desligado por configuração. *Remover código só depois de provar com log* |
| 10 | **Configuração por jogo** | `Emu/system_config.h` (todas as opções), `custom_configs/config_<serial>.yml`, patches em `Utilities/bin_patch.cpp` (`patch.yml`, `<serial>_patch.yml`) | **Reutilizar** |
| 10 | Específico do God of War III | **Não existe nenhum código específico do GOW3 no RPCS3** (busca por seriais e nome sem resultado). A wiki do RPCS3 recomenda `SPU Block Size: Safe`, `Renderer: Vulkan` e `Write Color Buffers: On`, e informa que o jogo **não é considerado "Playable"** | — |
| — | Interface Qt | `rpcs3/rpcs3qt/` (71 mil linhas) | **Simplificável no longo prazo.** No protótipo continua intacta |

**Como o launcher se integra sem mexer no RPCS3** (tudo conferido no código):
- `rpcs3 --no-gui [--fullscreen] --config <arquivo> <pasta do jogo>`. O `--config` carrega os padrões e aplica o arquivo por cima (`cfg_mode::config_override` em `Emu/System.cpp`), então o arquivo pode ser parcial.
- **Windows:** a variável de ambiente `RPCS3_CONFIG_DIR` muda a pasta de dados inteira (configuração, `dev_hdd0`, `dev_flash`, cache e log). Detalhe encontrado no código: o RPCS3 corta o valor na última barra (`Utilities/File.cpp`, `fs::get_config_dir`). Por isso **o valor precisa terminar com `\`**, senão a última pasta é descartada. O launcher trata isso, e há teste para esse caso.
- **Linux:** `XDG_CONFIG_HOME` e `XDG_CACHE_HOME`.
- Se existir uma pasta `portable/` ao lado do executável do RPCS3, ela vence essas variáveis. O launcher detecta isso e bloqueia o início, para não misturar saves.

---

## 3. Viabilidade do runtime especializado

| Objetivo | Viável? | Comentário |
|---|---|---|
| Launcher próprio, perfil e saves separados, diagnóstico | **Sim, feito** | Não precisa de fork |
| Configurações dedicadas ao GOW3 | **Sim, feito** | Usa só opções que já existem no RPCS3 |
| Resolução 720p a 4K, FSR 1, RCAS, filtro anisotrópico, VSync, limite de FPS | **Sim, feito** | Tudo isso é opção do RPCS3. Resolução interna = escala sobre 1280x720 (900p = 125%, 1080p = 150%, 1440p = 200%, 4K = 300%) |
| Fork "enxuto", só com o necessário para o GOW3 | Viável, **trabalho grande** | Exige o registro de quais módulos HLE e quais syscalls o jogo chama (ver Fase 1b). Remover sem essa prova é proibido pela metodologia |
| Ganhos de CPU além do RPCS3 | **Incerto** | O RPCS3 já é muito otimizado. O caminho realista é ajustar opções (bloco SPU, threads, loop detection) e testar patches específicos. Tudo precisa ser medido contra o RPCS3 original |
| 60 FPS estáveis | **Depende do hardware; não medido** | A wiki registra o jogo como não "Playable" |
| FPS acima de 60 | Só com patch do jogo | Os patches da comunidade ficam no `patch.yml`, baixado à parte. Não foi verificado se existe um para o GOW3. Risco de física e animação, como acontece no PS4 (o gow3_pc lista bloqueios de progresso a 120/240 FPS) |
| FSR 3/4, DLSS, XeSS | **Não, por enquanto** | O RPCS3 não tem vetores de movimento nem integração para isso. Não anunciar |
| Execução nativa do PowerPC | **Não** | Impossível no x86-64 (seção 1) |

---

## 4. Riscos

### Jurídicos

1. **Chaves dentro do RPCS3. Risco alto, exige decisão sua.** `rpcs3/Crypto/key_vault.h` e `key_vault.cpp` trazem chaves (por exemplo `RAP_KEY`, `NP_KLIC_KEY` e as tabelas `SELF_KEY` de vários níveis). O `unself.cpp` usa essas chaves para decifrar o `EBOOT.BIN`. Um fork que redistribua o RPCS3 inclui essas chaves, o que contraria as regras do projeto. Há três caminhos possíveis:
   - **(a)** O produto continua sendo **launcher + RPCS3 oficial instalado pelo usuário**. O projeto não redistribui chaves. É o caminho do protótipo atual.
   - **(b)** Fork **sem o módulo Crypto**, aceitando só `EBOOT.ELF` já decifrado pelo próprio usuário. O problema é que o usuário teria de decifrar com alguma ferramenta, e a mais comum é o próprio RPCS3, o que só desloca a questão.
   - **(c)** Fork com as chaves, como o RPCS3 faz hoje. Isso **viola a regra que você escreveu**.

   **Minha recomendação é (a)** enquanto um advogado não avaliar (b) ou (c) no Brasil. *Não sou advogado. Isto é uma análise técnica, não um parecer jurídico.*
2. **GPL-2.0-only.** Qualquer distribuição de binário derivado do RPCS3 precisa vir com o código-fonte correspondente, os avisos e o `LICENSE`. O launcher é GPL-2.0-only para ficar compatível.
3. **Marca e conteúdo.** Não usar logotipo, capa nem fonte do jogo no launcher. O nome "God of War" aparece só como descrição, com o aviso de que não há afiliação, já visível no cabeçalho da janela.
4. **Firmware.** O usuário baixa o PS3UPDAT.PUP do site da Sony. O projeto nunca o distribui.

### Técnicos

1. **Mudanças no RPCS3** podem renomear opções. Isso é mitigado pelo `tests/test_rpcs3_source.py`, que falha se alguma chave ou texto sumir.
2. **O `--config` substitui a configuração por jogo.** Quando o launcher é usado, um `custom_configs/config_BCUS98111.yml` feito à mão é ignorado. Isso é intencional (o launcher é a fonte da verdade), mas está documentado.
3. **Pasta `portable/`** anula o isolamento. É detectada e bloqueada.
4. **Imagens ISO e chaves de disco**: o RPCS3 pede a chave do disco para ISO (`disc_key_missing`). O protótipo aceita só a pasta do jogo copiada do PS3.
5. **eGPU via USB4** (RTX 4090M externa): a banda menor pode afetar a cópia de dados entre o RSX e a memória principal (`Write Color Buffers` lê da GPU). **Não testado**: exige medição no hardware real.
6. **Ryzen Z2 Extreme vs Core Ultra**: o RPCS3 tem caminhos AVX-512 nos SPUs. Pelo que se sabe, o Z2 Extreme (Zen 5) tem AVX-512 e os Core Ultra de consumo não têm. O launcher detecta isso em tempo real em vez de assumir. **Diferença de desempenho não medida.**

---

## 5. Estrutura de pastas proposta

```
gow3ps3pc/
├── LICENSE                 GPL-2.0 (texto integral)
├── CREDITS.md              RPCS3, gow3_pc, wiki do RPCS3
├── README.md
├── docs/
│   └── AUDITORIA.md        este documento
├── launcher/               FASE 2: protótipo (pronto)
│   ├── gow3ps3/
│   │   ├── psf.py          leitor do PARAM.SFO
│   │   ├── game.py         reconhecimento e integridade da pasta do jogo
│   │   ├── rpcs3.py        integração com o RPCS3 (CLI, ambiente, firmware)
│   │   ├── settings.py     configurações e geração do YAML do RPCS3
│   │   ├── sysinfo.py      detecção do computador
│   │   ├── diagnostics.py  leitura do RPCS3.log
│   │   ├── app.py          lógica (sem interface)
│   │   ├── gui.py          janela com as abas HOME/GRAPHICS/PERFORMANCE/CONTROLS/ADVANCED
│   │   └── __main__.py     python -m gow3ps3 [--check | --print-command | --play]
│   └── tests/
├── rpcs3/                  FUTURO: submódulo do fork (só depois da decisão da seção 4)
├── patches/                FUTURO: patches próprios do jogo, cada um com hash do EBOOT e validação
└── tools/
    └── trace/              FUTURO: coleta de módulos e syscalls usados pelo jogo (Fase 1b)
```

---

## 6. Plano por etapas

Cada etapa termina compilável e com testes passando. Nenhum número de desempenho será publicado sem medição.

| Etapa | Entrega | Validação |
|---|---|---|
| **2.0** (feita) | Launcher externo, sem fork | 30 testes automatizados, captura de tela da interface |
| **2.1** | Empacotar para Windows (PyInstaller) e **primeiro teste real** com o RPCS3 oficial, seu firmware e seu disco | Jogo abre pelo launcher; saves aparecem na pasta do perfil; o log mostra "Applied config override" |
| **1b** | **Rastreamento**: rodar o GOW3 no RPCS3 com o log das chamadas HLE/LV2 e montar a lista real de módulos e syscalls usados | A lista vira a "prova de não uso" exigida antes de qualquer remoção |
| **2.2** | Decisão jurídica da seção 4 e, se for o caso, fork do RPCS3 como submódulo, **sem mudar nada**, com CI compilando no Windows | O binário do fork se comporta igual ao oficial (mesmo log, mesmo FPS em cena fixa) |
| **3.x** | Perfis de CPU: matriz de testes com `SPU Block Size`, `Preferred SPU Threads`, `SPU loop detection` e `Max SPURS Threads` em cenas fixas | Tabela de FPS e frametime contra o RPCS3 original, com o hardware identificado |
| **4.x** | Monitor de VRAM e diagnóstico de travadas de compilação lendo o log e o overlay | Comparação com o overlay do próprio RPCS3 |
| **6.x** | Testes no Z2 Extreme, no Core Ultra e na eGPU | Relatório com números reais |
| **5.x** | Interface interna com Dear ImGui, se viável. Hoje o RPCS3 usa overlays próprios, não ImGui | Protótipo isolado |

---

## 7. Primeira tarefa de implementação (concluída nesta entrega)

**Problema.** Não havia forma de iniciar o God of War III com configuração, saves e cache próprios sem mexer na instalação do RPCS3 do usuário.

**Arquivos.** Todos em `launcher/` (nenhum arquivo do RPCS3 foi tocado).

**Solução.** Um launcher em Python que:
- lê o `PARAM.SFO`;
- reconhece os 9 seriais do jogo;
- confere `EBOOT.BIN` (cabeçalho SELF/ELF), arquivos vazios e a versão de firmware exigida;
- cria um perfil isolado do RPCS3;
- gera um YAML parcial de configuração;
- inicia `rpcs3 --no-gui --config …`.

Escolhi tkinter, que já vem com o Python do Windows, como o launcher do gow3_pc.

**Riscos.** Mudanças nas opções do RPCS3, cobertas pelo teste de código-fonte, e a pasta `portable/`, que é bloqueada.

**Validação feita (resultados reais):**

```
$ RPCS3_SRC=<clone do rpcs3> python -m unittest discover -s tests
Ran 30 tests in 0.217s
OK
```

- Testes de ponta a ponta com um **RPCS3 falso**, que registra os argumentos e o ambiente recebidos. Eles conferem o comando exato, o isolamento por variável de ambiente, o bloqueio sem firmware e a instalação de firmware.
- Teste contra o código real do RPCS3: todas as chaves, valores, faixas, opções de linha de comando e mensagens de log usadas existem no commit `4d5def5`.
- A interface foi aberta numa tela virtual (Xvfb) e as abas foram capturadas em imagem.

**O que NÃO foi testado** (por falta, neste ambiente, de Windows, do binário oficial do RPCS3, do firmware e do jogo):
- o boot real do jogo;
- a instalação real de firmware;
- a execução no Windows.

Essa é a etapa 2.1.
