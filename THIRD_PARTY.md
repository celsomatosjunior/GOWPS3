# Componentes de terceiros

| Componente | Onde fica no pacote | Licença | Observação |
|---|---|---|---|
| RPCS3 | `runtime/rpcs3/rpcs3.exe` | GPL-2.0-only | Compilado sem modificações; commit em `BUILD_INFO.txt` |
| Qt 6 | `runtime/rpcs3/Qt6*.dll`, `runtime/rpcs3/qt6/` | LGPL-3.0 | Ligação dinâmica; pode ser trocado pelo usuário. Fonte: https://download.qt.io/ |
| Microsoft Visual C++ Redistributable | `runtime/redist/vc_redist.x64.exe` | Licença de redistribuição do Visual Studio | Instalador oficial. O RPCS3 só aceita o Visual C++ instalado no Windows (`rpcs3/module_verifier.cpp`), por isso as DLLs não vão ao lado do `rpcs3.exe` |
| OpenCV | `runtime/rpcs3/opencv_world*.dll` | Apache-2.0 | Usado pelo RPCS3 |
| OpenAL Soft | `runtime/rpcs3/OpenAL32.dll` (se presente) | LGPL-2.0 | Usado pelo RPCS3 |
| LLVM (bibliotecas estáticas) | dentro do `rpcs3.exe` | Apache-2.0 com exceção LLVM | Recompiladores PPU/SPU |
| Demais bibliotecas do RPCS3 (FFmpeg, SDL, cubeb, yaml-cpp, zlib, zstd, libpng, wolfSSL, curl, etc.) | dentro do `rpcs3.exe` ou DLLs | várias | Os textos de licença copiados do código do RPCS3 ficam em `licenses/rpcs3-3rdparty/` |

O pacote **não** inclui: firmware do PS3, arquivos do jogo, chaves de licença digital
(`.rap`), nem o carregador Vulkan (`vulkan-1.dll`, que vem com o driver de vídeo).

**Atenção (já registrada na auditoria):** o código do RPCS3 contém chaves usadas para ler
executáveis de PS3 (`rpcs3/Crypto/key_vault.*`). Elas fazem parte do RPCS3 como ele é
distribuído publicamente. Ao redistribuir este pacote, avalie esse ponto com um advogado.
