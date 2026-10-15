# GOW3 PS3 PC

Launcher independente para jogar **God of War III (PlayStation 3)** no PC usando o emulador
[RPCS3](https://github.com/RPCS3/rpcs3), com configurações dedicadas, perfil e saves separados
e diagnóstico em português.

> **Nenhum arquivo do jogo, firmware ou chave criptográfica está incluído.** Você precisa da sua
> própria cópia do jogo (pasta copiada do seu PS3), do firmware PS3UPDAT.PUP baixado do site oficial
> da PlayStation e do RPCS3 oficial instalado. Projeto sem afiliação com a Sony Interactive
> Entertainment ou com o Santa Monica Studio. God of War é marca da Sony Interactive Entertainment.

Estado: **protótipo 0.1.0 (alfa)**. O boot real do jogo ainda não foi testado; veja
[docs/AUDITORIA.md](docs/AUDITORIA.md).

## Como usar (Windows)

1. Instale o Python 3.10 ou mais novo (python.org, marque "Add to PATH").
2. Baixe o RPCS3 oficial e extraia numa pasta. **Não** crie a pasta `portable` dentro dela.
3. Na pasta `launcher` deste projeto: `python -m gow3ps3`
4. Na aba **HOME**, escolha o `rpcs3.exe` e a pasta do jogo (a que contém `PS3_GAME`).
5. Clique em **Instalar firmware…** e escolha o seu `PS3UPDAT.PUP`.
6. Clique em **JOGAR**.

Atalhos de linha de comando: `python -m gow3ps3 --check`, `--print-command` e `--play`.

## Onde ficam os dados

Tudo fica em `%LOCALAPPDATA%\GOW3PS3PC\` e não mistura com a sua instalação normal do RPCS3:

| O quê | Onde |
|---|---|
| Configurações do launcher | `launcher.json` |
| Perfil do RPCS3 (firmware, saves, cache, log) | `rpcs3_profile\` |
| Salvamentos | `rpcs3_profile\dev_hdd0\home\00000001\savedata\` |
| Log | `rpcs3_profile\log\RPCS3.log` |

## Testes

```
cd launcher
python -m unittest discover -s tests
# opcional: confere tudo contra o código-fonte do RPCS3
RPCS3_SRC=/caminho/do/clone/rpcs3 python -m unittest discover -s tests
```

## Licença

GPL-2.0-only, a mesma do RPCS3. Veja [LICENSE](LICENSE) e [CREDITS.md](CREDITS.md).
