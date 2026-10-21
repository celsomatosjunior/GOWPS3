# Pesquisa do ecossistema de recompilação (outubro de 2026)

Levantamento feito antes da etapa seguinte do GOW3 PS3 Native: projetos públicos que
recompilam jogos de PS3 (ou ports nativos parecidos), o que cada um resolveu e o que dá para
aproveitar. Os repositórios foram clonados e lidos; os vídeos indicados pelo usuário só puderam
ser lidos pelo título e descrição.

Não foi encontrado nenhum outro projeto público de recompilação do God of War III de **PS3**.
O `gow3_pc` / **SpartanPort** é da versão **PS4** (Remastered): o código x86-64 roda direto,
técnica que não se aplica ao PowerPC/Cell do PS3.

## Projetos de PS3 sobre o ps3recomp

| Projeto | Jogo | Situação declarada | O que interessa para nós |
|---|---|---|---|
| [arnaldolima1/gow-ascension-pc](https://github.com/arnaldolima1/gow-ascension-pc) | God of War: Ascension (BCES01741) | Primeiro nível, ~9 fps, Windows | **Mesmo estúdio e mesma família de motor do GOW3.** 44 patches no ps3recomp (SPURS2 com 32 workloads, Edge Zlib no host, espera de GCM/semaforos, módulos de job Wws), ajustes do runtime documentados em `host/ascension_defaults.cpp`, relift separado PPU / SPU / jobmods / fragmentos, testes diferenciais de módulo SPU. O gargalo deles é o código SPU. |
| [sethlikepie/Gow2HD-Windows](https://github.com/sethlikepie/Gow2HD-Windows) | God of War II HD (NPUA80491) | Lançado (v0.1.0), Windows, D3D12 | **Modelo de entrega:** `Gow2HD-Windows.exe` (Win32, sem dependências) baixa ferramentas fixadas por SHA-256 (Python embutível, llvm-mingw, FFmpeg), roda `build.py` no PC do usuário com etapas incrementais ("stamps"), protocolo `PROGRESS <0-100>` / `ERROR`, hashes da versão exata do jogo, `check_no_game_data.py` como trava de commit, mudanças no código gerado como scripts idempotentes (`lift_patches/`), todas as opções como variáveis de ambiente com padrão. |
| [andrebrumdev/gow2-recomp](https://github.com/andrebrumdev/gow2-recomp) | God of War II HD | Jogável no macOS (Metal) | `functions.json` curado (69 mil funções, ~650 arquivos C++), `verify_lift`/linha de base de hashes do lift, **RPCS3 como oráculo** pelo servidor GDB (cliente RSP em `tools/rpcs3_probe/`), guia `RPCS3_AS_REFERENCE.md`, regra "confirmar no RPCS3 o endereço real do store antes de culpar HLE". |
| [JonathanDC64/DemonsSoulsRecomp](https://github.com/JonathanDC64/DemonsSoulsRecomp) | Demon's Souls (BLUS30443) | Primeiro nível jogável, Windows/D3D12 | Fork próprio do ps3recomp; usa o RPCS3 do usuário para decifrar; `libsre.prx` do firmware do usuário para SPURS. |
| [feanor-noldorin/ico-recomp](https://github.com/feanor-noldorin/ico-recomp) | ICO (BCUS98259) | Jogável (alpha), Windows | Instalador único: decifra **com o RPCS3 do usuário** (`rpcs3.exe --no-gui --decrypt`), confere SHA-256 do `.self` e do `.elf`, perfil do jogo em JSON (`ico_profile.json`). |
| [dawoodtogoo2020-code/folklore-native-port](https://github.com/dawoodtogoo2020-code/folklore-native-port) | Folklore | Menus e gameplay em builds privados | "Owner Build Kit"; 26 saídas de aceitação PPU e 27 SPU reproduzidas; separação rigorosa entre "teste de CPU passou" e "jogo funciona". |
| [canersaka/Yakuza-Dead-Souls-EX](https://github.com/canersaka/Yakuza-Dead-Souls-EX) | Yakuza: Dead Souls | Gameplay, D3D12, ~20 fps em cenas pesadas | SPURS nativo, driver gcm/RSX nativo, sem firmware. |
| [n0madic/Soulcalibur2HD-recomp](https://github.com/n0madic/Soulcalibur2HD-recomp) | Soulcalibur II HD | Funciona (Metal / Vulkan) | Compila no PC do usuário com clang ou **zig baixado com SHA-256 fixado**; `-march=native` porque o x86-64 genérico ficou lento demais. |
| [gnome41/dbz-budokai-hd](https://github.com/gnome41/dbz-budokai-hd) | DBZ Budokai HD | Em andamento | Interpretador SPU, Edge geometry. |
| [sp00nznet/tornado](https://github.com/sp00nznet/tornado), [simpsonsarcade-ps3](https://github.com/sp00nznet/simpsonsarcade-ps3) | Tornado Outbreak, Simpsons Arcade | Em jogo / jogável | Ports de referência do próprio autor do ps3recomp, no Windows. |

Outros citados no ps3recomp: inFAMOUS 1/2, Killzone 2/3, Twisted Metal, LittleBigPlanet, Ben 10.

## Outros ports nativos (técnicas transferíveis)

- **Bloodborne** ([deadinside28/bloodborne_pc](https://github.com/deadinside28/bloodborne_pc)) e
  **The Last Guardian** ([HayatoG/tlg_pc](https://github.com/HayatoG/tlg_pc)): PS4, código x86 roda
  direto. Aproveitável: runtime pequeno só com o que o jogo chama, versão exata do executável,
  ganchos para FPS e proporção de tela, launcher com mods, CI que publica pacotes.
- **Hell's Gate** ([florinp93/hells-gate-recomp](https://github.com/florinp93/hells-gate-recomp)):
  Dante's Inferno (Xbox 360, PowerPC) pelo ReXGlue, jogável do início ao fim; renderizador próprio
  em vez de emular a GPU; instalador e atualizador.
- **Naruto: Rise of a Ninja** (Xbox 360): versão amarrada ao hash do executável.
- **God of War II (PS2)** ([cxldsakeb/GoW2-nativo-PS2](https://github.com/cxldsakeb/GoW2-nativo-PS2)):
  PS2Recomp; documentação por fases com bloqueios resolvidos.
- Catálogos: [recomp.fyi](https://recomp.fyi) (tabela com todos os projetos, inclusive PS3).

## Recursos do RPCS3 confirmados no código (commit 4d5def5, o mesmo do pacote RPCS3 do projeto)

- `rpcs3 --no-gui --decrypt <arquivo>` (`rpcs3/rpcs3.cpp`): gera o ELF a partir do SELF com o
  RPCS3 e o firmware do próprio usuário.
- Servidor GDB (`rpcs3/Emu/GDB.cpp`, opção `Misc: GDB Server: 127.0.0.1:2345`): pontos de parada,
  leitura de registradores e memória. Permite capturar o **estado real** do jogo na entrada de uma
  função e o estado na saída, e usar isso como caso de teste da função recompilada.

## Decisões que esta pesquisa sugere

1. **Motor:** ps3recomp v0.16.0 (já adotado). Estudar os 44 patches do Ascension antes de
   escrever runtime próprio para SPURS, Edge Zlib e GCM: é o mesmo motor de jogo.
2. **Teste com estado real:** acrescentar ao analisador um modo "oráculo RPCS3" pelo servidor GDB,
   para as funções hoje "inconclusivas" (precisam de estruturas reais do jogo).
3. **Recompilação completa:** lista de funções curada e geração em muitos arquivos (como o GoW2),
   com linha de base de hashes do resultado.
4. **Entrega:** o modelo do Gow2HD-Windows (launcher que compila no PC do usuário, ferramentas com
   SHA-256 fixado, etapas incrementais, hashes da versão BCES00510) é o alvo para quando houver
   um jogo para rodar.
5. **Decifragem:** o projeto não decifra nada. Opção a decidir pelo usuário: o analisador chamar o
   RPCS3 **do usuário** (`--decrypt`), como o ICO faz, em vez do passo manual.
