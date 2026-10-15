# Relatório de compilação e testes: GOW3 PS3 PC 0.2.0

**Data:** 15/10/2026
**RPCS3 alvo:** commit `4d5def5880217135554ed434cd5055cceebe9cc2` (`RPCS3_COMMIT.txt`)

Este relatório separa o que **foi executado de fato** do que **ainda depende do runner Windows** e do que **depende do jogo**. Nada aqui afirma que God of War III funciona.

## 1. Resumo

| Item | Situação |
|---|---|
| Código do `GOW3_PS3_PC.exe` (C++20, Win32) | Escrito e compilado para Windows x64 (MinGW-w64), **sem nenhum aviso** com `-Wall -Wextra` |
| Testes do núcleo | 71 verificações passando no Linux; 75 passando no binário **Windows** (Wine), incluindo a leitura da tabela de importação do próprio `.exe` |
| Fluxo completo do aplicativo (autoteste, verificação, firmware, iniciar o jogo) | Executado no Wine com um **RPCS3 falso** que imita o contrato do real: passou |
| Interface | Aberta no Wine. As abas HOME, GRAPHICS, PERFORMANCE e ADVANCED foram capturadas, e o autoteste rodou pela interface |
| Contrato com o RPCS3 (chaves, valores, opções de linha de comando, `RPCS3_CONFIG_DIR`, mensagens de log) | Conferido no código-fonte do commit alvo. Um teste negativo confirma que o verificador detecta quebra |
| Empacotador | ZIP gerado com a estrutura final. Recusa firmware (`.PUP`) e pastas de dados (`dev_flash`), conforme testado |
| **Compilação com MSVC / Visual Studio 2022** | **Pendente**: precisa do runner Windows do GitHub Actions |
| **Compilação do RPCS3 e `GOW3_PS3_PC_Windows_x64.zip` real** | **Pendente**: mesmo motivo |
| **Execução no Windows real** | **Pendente**: o workflow faz o autoteste e um teste de abertura da janela numa máquina limpa |
| **God of War III rodando** | **Não testado**: exige o jogo, o firmware e uma GPU. Isso só pode ser feito no seu PC |

## 2. Por que o ZIP final ainda não saiu daqui

- Esta sessão roda em Linux, sem acesso de escrita a nenhum repositório GitHub (não há conta GitHub conectada). Por isso não foi possível disparar o runner Windows.
- O RPCS3 para Windows é compilado com MSVC, Qt para MSVC e bibliotecas LLVM pré-compiladas para MSVC. Isso não dá para reproduzir por compilação cruzada no Linux de forma confiável.
- Os sites de download do RPCS3 pronto estão bloqueados por este ambiente. Além disso, a decisão foi compilar a partir do código, para cumprir a GPL com o fonte exato.

**O que falta:** colocar este repositório no seu GitHub. O workflow `.github/workflows/windows.yml` então gera, sozinho e numa máquina Windows real:
- o `GOW3_PS3_PC_Windows_x64.zip`;
- o código-fonte correspondente;
- o relatório com o autoteste.

## 3. Comandos executados e resultados reais

### 3.1 Linux, testes do núcleo
```
$ cmake -S . -B build-linux -G Ninja && cmake --build build-linux
(0 avisos, 0 erros)
$ ./build-linux/core_tests
71 verificações, 0 falhas
```

### 3.2 Compilação cruzada para Windows x64 (MinGW-w64, GCC 13, `-static`)
```
$ cmake -S . -B build-mingw -G Ninja -DCMAKE_TOOLCHAIN_FILE=cmake/mingw-w64-x86_64.cmake && cmake --build build-mingw
(0 avisos, 0 erros)
build-mingw/GOW3_PS3_PC.exe  3.794.465 bytes, PE32+ x64
$ ctest   (executado via Wine 9.0)
100% tests passed, 0 tests failed out of 3
  core_tests        75 verificações, 0 falhas
  core_tests_pe     GOW3_PS3_PC.exe importa só DLLs do Windows:
                    ADVAPI32 COMCTL32 GDI32 KERNEL32 msvcrt ole32 SHELL32 USER32
  app_version       "GOW3 PS3 PC 0.2.0"
```
O binário oficial é feito com MSVC e runtime estático (`/MT`). Nele, a lista de DLLs sai no relatório do CI (`dumpbin /dependents`).

### 3.3 Pacote com RPCS3 falso, executado no Wine
O RPCS3 falso (`tools/fake_rpcs3`) reproduz o que foi conferido no código real:
- corta `RPCS3_CONFIG_DIR` na última barra;
- grava o log em `<config>/log/RPCS3.log`;
- responde a `--headless --version` e `--headless --installfw`;
- importa uma DLL (para testar a checagem de dependências).

```
$ GOW3_PS3_PC.exe --selftest                    -> APROVADO (código 0)
    componentes com SHA-256 OK, DLLs resolvidas, rpcs3.exe executou,
    log gravado em user\rpcs3\log (isolamento por RPCS3_CONFIG_DIR funcionando)
$ GOW3_PS3_PC.exe --game "<pasta de teste>" --check   -> código 2: "Firmware do PS3 não instalado"
$ GOW3_PS3_PC.exe --install-firmware PS3UPDAT.PUP     -> "Firmware instalado: 4.92" (código 0)
$ GOW3_PS3_PC.exe --play
    rpcs3.exe recebeu: --no-gui --fullscreen --config <user\gow3_rpcs3_config.yml> <pasta do jogo com espaços>
    o RPCS3 falso devolveu erro de firmware; o aplicativo mostrou:
    "O firmware instalado é mais antigo do que o jogo pede."
```

Testes negativos:
- Sem a DLL do runtime, o autoteste é **REPROVADO** com três apontamentos: componente ausente, `DLL ausente: Qt6FakeCore.dll (usada por rpcs3.exe)` e `rpcs3.exe terminou com código 0xC0000135`.
- Com a pasta `runtime\rpcs3\portable`, a verificação acusa o erro de isolamento.
- O empacotador recusa `PS3UPDAT.PUP` e `dev_flash/`.

A "pasta de teste" é gerada por `tools/make_fake_game.py`. Ela tem só um PARAM.SFO criado aqui e um EBOOT.BIN de 64 bytes, **sem nenhum conteúdo do jogo**.

### 3.4 Contrato com o RPCS3
```
$ python tools/check_rpcs3_contract.py <rpcs3@4d5def5> default_config.yml
Contrato com o RPCS3 conferido: chaves, valores, opções de linha de comando, pasta de dados e mensagens de log.
(teste negativo: trocar "Safe" por "Segura" -> "valor inexistente para SPU Block Size", código 1)
```

### 3.5 Workflow
`actionlint` (validador oficial de workflows do GitHub Actions) não encontrou erro em `.github/workflows/windows.yml`.

## 4. O que o runner Windows vai verificar

1. **Job `app`:** compila com Visual Studio 2022 e roda `ctest` (com o teste da tabela de importação do `.exe` feito com MSVC).
2. **Job `rpcs3`:**
   - compila o RPCS3 com os scripts oficiais;
   - copia o runtime do Visual C++ para dentro do pacote;
   - confere o contrato e monta o ZIP;
   - roda `--selftest`, que executa o **rpcs3.exe real** (`--headless --version`) e confirma que o log foi gravado em `user\rpcs3\log`.
3. **Job `clean_test`:** numa máquina Windows nova, extrai o ZIP, roda o autoteste e abre a janela por 15 segundos.
   - O autoteste falha se alguma DLL só existir fora do pacote. É o caso, por exemplo, de um runtime do Visual C++ instalado no sistema em vez de copiado.

**Limitação do servidor:** as máquinas do GitHub não têm GPU. Se não houver `vulkan-1.dll`, a execução do rpcs3.exe é pulada e o relatório diz isso explicitamente. No job `rpcs3` o workflow tenta usar a `vulkan-1.dll` do Vulkan SDK instalado para a compilação.

## 5. Próximo teste, no seu PC (a única forma de validar o jogo)

1. Baixe o ZIP do artefato e extraia em `C:\Jogos\GOW3_PS3_PC`.
2. Rode ADVANCED → **Autoteste do pacote**. Deve aparecer "APROVADO", agora com a sua GPU listada.
3. Instale o firmware, escolha o jogo e clique em **JOGAR**.
4. Envie `user\logs\selftest.txt`, `user\logs\GOW3_PS3_PC.log` e `user\rpcs3\log\RPCS3.log`. Com eles, este relatório registra o primeiro resultado real com o jogo.
