# Relatório de compilação — GOW3 PS3 PC

```
GOW3 PS3 PC — informações da compilação
Data (UTC): 2026-10-15 17:34
GOW3 PS3 PC: commit 7afa93fd818ec2b3d2abc693911ac850517ab578 (celsomatosjunior/GOWPS3)
RPCS3: commit 4d5def5880217135554ed434cd5055cceebe9cc2 (https://github.com/RPCS3/rpcs3), sem modificações
RPCS3 compilado com: MSVC / Visual Studio 18.10.3, Qt 6.12.0, LLVM 22.1.8, Vulkan SDK 1.4.341.1
GOW3_PS3_PC.exe compilado com: CMake + Visual Studio 2022 (job 'app')
Execução: https://github.com/celsomatosjunior/GOWPS3/actions/runs/38776095780
Teste com God of War III: NÃO REALIZADO nesta compilação (sem jogo nem GPU no servidor).
```

## GOW3_PS3_PC.exe (dumpbin /dependents)
```

Dump of file build\Release\GOW3_PS3_PC.exe

File Type: EXECUTABLE IMAGE

  Image has the following dependencies:

    COMCTL32.dll
    SHELL32.dll
    ole32.dll
    ADVAPI32.dll
    USER32.dll
    GDI32.dll
    KERNEL32.dll

  Summary

        4000 .data
        1000 .fptable
        5000 .pdata
       20000 .rdata
        1000 .reloc
        4000 .rsrc
       71000 .text
cmake version 3.31.6

CMake suite maintained and supported by Kitware (kitware.com/cmake).
17.14.41 (September 2026)
```

## Pacote
```
total 59500
drwxr-xr-x 1 runneradmin 197121        0 Oct 15 17:34 .
drwxr-xr-x 1 runneradmin 197121        0 Oct 15 17:37 ..
drwxr-xr-x 1 runneradmin 197121        0 Oct 15 17:36 GOW3_PS3_PC
-rw-r--r-- 1 runneradmin 197121 60916994 Oct 15 17:34 GOW3_PS3_PC_Windows_x64.zip
GOW3_PS3_PC
GOW3_PS3_PC/BUILD_INFO.txt
GOW3_PS3_PC/FONTE.txt
GOW3_PS3_PC/GOW3_PS3_PC.exe
GOW3_PS3_PC/LEIA-ME.txt
GOW3_PS3_PC/licenses
GOW3_PS3_PC/licenses/GPL-2.0_GOW3_PS3_PC_e_RPCS3.txt
GOW3_PS3_PC/licenses/THIRD_PARTY.md
GOW3_PS3_PC/licenses/qt
GOW3_PS3_PC/licenses/qt/GPL-3.0.txt
GOW3_PS3_PC/licenses/qt/LEIA-ME.txt
GOW3_PS3_PC/licenses/qt/LGPL-3.0.txt
GOW3_PS3_PC/licenses/rpcs3-3rdparty
GOW3_PS3_PC/licenses/rpcs3-3rdparty/3rdparty
GOW3_PS3_PC/runtime
GOW3_PS3_PC/runtime/rpcs3
GOW3_PS3_PC/runtime/rpcs3/GuiConfigs
GOW3_PS3_PC/runtime/rpcs3/Icons
GOW3_PS3_PC/runtime/rpcs3/Qt6Concurrent.dll
GOW3_PS3_PC/runtime/rpcs3/Qt6Core.dll
GOW3_PS3_PC/runtime/rpcs3/Qt6Gui.dll
GOW3_PS3_PC/runtime/rpcs3/Qt6Multimedia.dll
GOW3_PS3_PC/runtime/rpcs3/Qt6MultimediaWidgets.dll
GOW3_PS3_PC/runtime/rpcs3/Qt6Network.dll
GOW3_PS3_PC/runtime/rpcs3/Qt6Svg.dll
GOW3_PS3_PC/runtime/rpcs3/Qt6SvgWidgets.dll
GOW3_PS3_PC/runtime/rpcs3/Qt6Widgets.dll
GOW3_PS3_PC/runtime/rpcs3/avcodec-63.dll
GOW3_PS3_PC/runtime/rpcs3/avformat-63.dll
GOW3_PS3_PC/runtime/rpcs3/avutil-61.dll
GOW3_PS3_PC/runtime/rpcs3/concrt140.dll
GOW3_PS3_PC/runtime/rpcs3/config
GOW3_PS3_PC/runtime/rpcs3/fonts
GOW3_PS3_PC/runtime/rpcs3/msvcp140.dll
GOW3_PS3_PC/runtime/rpcs3/msvcp140_1.dll
GOW3_PS3_PC/runtime/rpcs3/msvcp140_2.dll
GOW3_PS3_PC/runtime/rpcs3/msvcp140_atomic_wait.dll
GOW3_PS3_PC/runtime/rpcs3/msvcp140_codecvt_ids.dll
GOW3_PS3_PC/runtime/rpcs3/opencv_world4140.dll
GOW3_PS3_PC/runtime/rpcs3/qt6
GOW3_PS3_PC/runtime/rpcs3/rpcs3.exe
GOW3_PS3_PC/runtime/rpcs3/swresample-7.dll
GOW3_PS3_PC/runtime/rpcs3/swscale-10.dll
GOW3_PS3_PC/runtime/rpcs3/test
GOW3_PS3_PC/runtime/rpcs3/vccorlib140.dll
GOW3_PS3_PC/runtime/rpcs3/vcruntime140.dll
GOW3_PS3_PC/runtime/rpcs3/vcruntime140_1.dll
GOW3_PS3_PC/runtime/rpcs3/vcruntime140_threads.dll
GOW3_PS3_PC/runtime/runtime_manifest.txt
```

## Autoteste na máquina de compilação
```
GOW3 PS3 PC 0.2.0 - autoteste do pacote
Pasta do aplicativo: D:\a\GOWPS3\GOWPS3\dist\GOW3_PS3_PC
Pasta de dados: D:\a\GOWPS3\GOWPS3\dist\GOW3_PS3_PC\user

== 1. Componentes do RPCS3 (tamanho e SHA-256) ==
[OK   ] Componentes do RPCS3 conferidos: 252 arquivos (com SHA-256)

== 2. Dependências (DLLs) ==
[OK   ] 39 executáveis/DLLs analisados, 301 importações resolvidas

== 3. Dados do usuário ==
[OK   ] Pasta de dados gravável
[OK   ] Configuração do RPCS3 gerada: D:\a\GOWPS3\GOWPS3\dist\GOW3_PS3_PC\user\gow3_rpcs3_config.yml

== 3b. Compatibilidade do RPCS3 instalado ==
[OK   ] Todas as 46 opções usadas pelo aplicativo existem neste rpcs3.exe

== 4. Execução do RPCS3 embutido ==
[ERRO ] rpcs3.exe --version não terminou em 120 s: 1 processo(s) ainda abertos
    janela "RPCS3: Fatal Error"

== 5. Computador (informativo) ==
[OK   ] Windows 11 (build 26100)
[OK   ] AMD EPYC 9V45 96-Core Processor, 4 threads
[OK   ] CPU com AVX-512 (o RPCS3 usa essas instruções nos SPUs).
[OK   ] 16.0 GB de RAM
[ERRO ] Vulkan: o driver recusou criar uma instância Vulkan (erro -9). Instale ou atualize o driver de vídeo.

RESULTADO: REPROVADO
Observação: este autoteste não executa God of War III; ele confirma que o pacote está completo e que o RPCS3 embutido inicia.
```
