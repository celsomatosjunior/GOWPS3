# GOW3 PS3 PC

Aplicativo Windows independente para jogar **God of War III (PlayStation 3)** no PC. O pacote traz:

- `GOW3_PS3_PC.exe`: interface própria, com as abas HOME, GRAPHICS, PERFORMANCE, CONTROLS e ADVANCED;
- o emulador [RPCS3](https://github.com/RPCS3/rpcs3) compilado e embutido em `runtime\rpcs3`.

O usuário não instala o RPCS3 separado.

> **O pacote não traz nenhum arquivo do jogo, firmware ou arquivo da Sony.** Você precisa da sua
> própria cópia do jogo, copiada do seu PS3, e do PS3UPDAT.PUP baixado do site oficial da
> PlayStation. Este projeto não tem afiliação com a Sony Interactive Entertainment nem com o
> Santa Monica Studio.

**Estado: alfa.** Ainda não houve teste do jogo rodando por este aplicativo. Veja
[docs/RELATORIO_COMPILACAO_TESTES.md](docs/RELATORIO_COMPILACAO_TESTES.md).

## Como o pacote funciona

```
GOW3_PS3_PC\
├── GOW3_PS3_PC.exe          interface (C++/Win32, sem dependências além do Windows)
├── runtime\
│   ├── rpcs3\               RPCS3 sem modificações, compilado do commit em RPCS3_COMMIT.txt
│   └── runtime_manifest.txt SHA-256 de cada arquivo do runtime
├── user\                    criada no primeiro uso: configurações, firmware, saves, cache, logs
├── licenses\  LEIA-ME.txt  FONTE.txt  BUILD_INFO.txt
```

O `GOW3_PS3_PC.exe` inicia o `runtime\rpcs3\rpcs3.exe` com:

- `RPCS3_CONFIG_DIR=<pasta>\user\rpcs3\`, que mantém configuração, saves, cache de shaders, cache PPU/SPU e log dentro do pacote;
- `--no-gui --config <configuração gerada> <pasta do jogo>`.

A configuração gerada usa só opções que existem no RPCS3, e isso é conferido automaticamente por `tools/check_rpcs3_contract.py`.

## Compilar

Veja [docs/COMPILACAO.md](docs/COMPILACAO.md). Resumo:

- **GitHub Actions** (`.github/workflows/windows.yml`) gera `GOW3_PS3_PC_Windows_x64.zip`, o código-fonte correspondente e o relatório.
- **Localmente no Windows:** `cmake -S . -B build -G "Visual Studio 17 2022" -A x64` e depois `cmake --build build --config Release`. O RPCS3 é compilado à parte com os scripts do próprio RPCS3.

## Uso pela linha de comando

```
GOW3_PS3_PC.exe                       abre a janela
GOW3_PS3_PC.exe --play                inicia o jogo com as configurações salvas (atalhos, Steam)
GOW3_PS3_PC.exe --check               verifica pacote, jogo, firmware e computador
GOW3_PS3_PC.exe --selftest            autoteste do pacote (arquivos, DLLs, execução do RPCS3)
GOW3_PS3_PC.exe --install-firmware <PS3UPDAT.PUP>
GOW3_PS3_PC.exe --game <pasta do jogo>
```

## Licença

GPL-2.0-only, a mesma do RPCS3. Componentes de terceiros: [THIRD_PARTY.md](THIRD_PARTY.md).
Auditoria técnica e riscos jurídicos: [docs/AUDITORIA.md](docs/AUDITORIA.md).
