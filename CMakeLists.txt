# SPDX-License-Identifier: GPL-2.0-only
cmake_minimum_required(VERSION 3.21)
project(GOW3_PS3_PC VERSION 0.2.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
# Runtime do C++ embutido no .exe: o aplicativo não depende do Visual C++ Redistributable.
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

enable_testing()

if(MINGW)
	# Teste local com MinGW: sem DLLs do GCC ao lado do .exe.
	add_link_options(-static)
endif()

add_library(gow3core STATIC
	app/core/common.cpp
	app/core/diagnostics.cpp
	app/core/game.cpp
	app/core/psf.cpp
	app/core/runtime.cpp
	app/core/settings.cpp
	app/core/sha256.cpp)

if(MSVC)
	target_compile_options(gow3core PUBLIC /utf-8 /W4 /permissive- /EHsc)
else()
	target_compile_options(gow3core PUBLIC -Wall -Wextra)
endif()

add_executable(core_tests app/tests/core_tests.cpp)
target_link_libraries(core_tests PRIVATE gow3core)
add_test(NAME core_tests COMMAND core_tests)

if(WIN32)
	enable_language(RC)
	add_executable(GOW3_PS3_PC WIN32
		app/win/controller.cpp
		app/win/main.cpp
		app/win/platform.cpp
		app/win/ui.cpp
		app/res/app.rc)
	target_link_libraries(GOW3_PS3_PC PRIVATE gow3core comctl32 shell32 ole32 uuid advapi32 user32 gdi32)
	configure_file(app/res/version.h.in ${CMAKE_CURRENT_BINARY_DIR}/generated/version.h @ONLY)
	target_include_directories(GOW3_PS3_PC PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/generated)
	target_compile_definitions(GOW3_PS3_PC PRIVATE UNICODE _UNICODE)
	if(MSVC)
		# O manifesto vem do app.rc; evita o manifesto duplicado gerado pelo linker.
		target_link_options(GOW3_PS3_PC PRIVATE /MANIFEST:NO)
	else()
		target_link_options(GOW3_PS3_PC PRIVATE -municode)
	endif()
	add_test(NAME core_tests_pe COMMAND core_tests --pe $<TARGET_FILE:GOW3_PS3_PC>)
	add_test(NAME app_version COMMAND GOW3_PS3_PC --version)
endif()
