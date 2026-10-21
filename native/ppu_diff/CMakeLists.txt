# SPDX-License-Identifier: GPL-2.0-only
# Compila o código PowerPC recompilado (lifted/ppu_recomp.c) para o host: Linux ou Windows x64.
# Uso: cmake -S <pacote> -B build -G Ninja -DCMAKE_C_COMPILER=clang-cl -DCMAKE_CXX_COMPILER=clang-cl
cmake_minimum_required(VERSION 3.20)
project(ppu_diff LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
# O lifter emite C++ (extern "C"), por isso ppu_recomp.c é compilado como C++.
set_source_files_properties(lifted/ppu_recomp.c PROPERTIES LANGUAGE CXX)
add_executable(ppu_diff_lifted lifted/ppu_recomp.c driver.cpp guest_runtime.cpp)
target_include_directories(ppu_diff_lifted PRIVATE lifted ${CMAKE_CURRENT_SOURCE_DIR})
# Sem o atalho de leitura em linha do lifter: toda leitura passa por vm_read*, que confere a memória.
target_compile_definitions(ppu_diff_lifted PRIVATE PPU_NO_INLINE_LOADS PPU_NO_INLINE_STORES)
if(MSVC)
	target_compile_options(ppu_diff_lifted PRIVATE /utf-8 /W1 /EHsc)
	set_property(TARGET ppu_diff_lifted PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
else()
	target_compile_options(ppu_diff_lifted PRIVATE -w)
endif()
