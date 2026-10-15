# Compilação do GOW3 PS3 PC para Windows x64

## Caminho oficial: GitHub Actions

O workflow `.github/workflows/windows.yml` roda sozinho a cada push para `main`/`master` e também pode ser disparado à mão em **Actions → Windows build → Run workflow**.

| Job | Máquina | O que faz |
|---|---|---|
| `app` | `windows-2022` (Visual Studio 2022) | CMake + MSVC compilam o `GOW3_PS3_PC.exe` e os testes do núcleo; roda `ctest`; registra as DLLs importadas (`dumpbin /dependents`) |
| `rpcs3` | `windows-2025-vs2026` (a mesma imagem do CI oficial do RPCS3) | Baixa o RPCS3 no commit de `RPCS3_COMMIT.txt` e lê as versões de Qt, LLVM e Vulkan SDK do próprio CI do RPCS3 (`tools/rpcs3_ci_env.py`). Compila com `msbuild` e os scripts `.ci/*` do RPCS3. Depois copia o runtime do Visual C++, confere o contrato (`tools/check_rpcs3_contract.py`), monta o ZIP (`tools/package.py`), roda o autoteste e gera o código-fonte correspondente |
| `clean_test` | `windows-2022` limpa | Baixa o ZIP, extrai, roda `GOW3_PS3_PC.exe --selftest`, abre a janela por 15 s e fecha |
| `release` | só em tags `v*` | Publica uma *pre-release* com o ZIP, o código-fonte e o relatório |

**Artefatos** de cada execução, que ficam na página da execução em Actions:
- `GOW3_PS3_PC_Windows_x64`: contém o `GOW3_PS3_PC_Windows_x64.zip`;
- `GOW3_PS3_PC_source`: código-fonte do aplicativo e do RPCS3 no commit usado, com submódulos;
- `BUILD_REPORT`: relatório da compilação e saída do autoteste;
- `selftest_clean_machine`: autoteste na máquina limpa.

**Tempo.** A primeira compilação do RPCS3 leva algumas horas. As seguintes usam o ccache e ficam bem mais rápidas.

**Por que duas versões do Visual Studio?** O `GOW3_PS3_PC.exe` é compilado com o Visual Studio 2022, como foi pedido. O RPCS3 é compilado exatamente como os mantenedores dele compilam (imagem `windows-2025-vs2026`), porque as bibliotecas LLVM pré-compiladas que o RPCS3 baixa são feitas para essa cadeia de ferramentas. Os dois executáveis não compartilham runtime de C++: o `GOW3_PS3_PC.exe` usa o runtime estático (`/MT`), e o RPCS3 leva as DLLs do Visual C++ ao lado dele.

**Atualizar o RPCS3:** troque o hash em `RPCS3_COMMIT.txt`. As versões das dependências acompanham o hash automaticamente. Se o RPCS3 tiver mudado alguma opção usada pelo aplicativo, o passo "Conferir contrato com o RPCS3" falha e diz qual.

## Compilação local no Windows

Requisitos: Visual Studio 2022 com "Desenvolvimento para desktop com C++", CMake 3.21+ e Python 3.

```bat
cmake -S . -B build -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release
ctest --test-dir build -C Release --output-on-failure
```

Para o pacote completo é preciso o RPCS3 compilado. Siga o `BUILDING.md` do RPCS3 no commit de `RPCS3_COMMIT.txt` e depois rode:

```bat
python tools\package.py --app build\Release\GOW3_PS3_PC.exe --rpcs3-bin <rpcs3>\bin --out dist
dist\GOW3_PS3_PC\GOW3_PS3_PC.exe --selftest
```

## Testes locais sem Windows (desenvolvimento)

```sh
cmake -S . -B build-linux -G Ninja && cmake --build build-linux && ./build-linux/core_tests
cmake -S . -B build-mingw -G Ninja -DCMAKE_TOOLCHAIN_FILE=cmake/mingw-w64-x86_64.cmake && cmake --build build-mingw
```

Em `tools/fake_rpcs3/` há um RPCS3 **falso** que reproduz o contrato de linha de comando e de pastas. Ele serve só para testar o aplicativo no Wine. **Esse teste não substitui o teste no Windows com o RPCS3 real.**
