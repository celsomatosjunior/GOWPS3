// GOW3 nativo: o RSX do RPCS3 (ponte gpu/ do ps3recomp) no lugar do live draw, com PS3_RSX=rpcs3.
//
// Adaptado do runtime/ppu/tests/boot_main.cpp do ps3kit de Arnaldo Lima (ramo ascension-perf, 2e972569:
// ps3rsx_select, rpcs3_rsx_start, s_rpcs3_hooks, o tratador de falhas), usado com a permissão dele. A ponte
// é o RSX do RPCS3 (GPL-2.0): este arquivo e o executável que o liga ficam sob GPL-2.0.
//
// Sem PS3_RSX=rpcs3 nada aqui age: gow3_rsx_select() devolve 0 e o main.cpp segue com a memória e o live
// draw de sempre. Ganchos do runtime do ps3kit que o nosso ainda não tem (a espera de relatórios
// g_rsx_hold_kick, os PUTs de SPU pelas travas da FIFO do RSX g_spu_dma_put_copy_hook, o aviso de DMA de SPU
// em página protegida g_vm_protected_page_hook) ficam de fora por enquanto; o tratador de exceções cobre a
// falha numa página que o RSX protegeu, em qualquer thread.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#ifdef _WIN32
#include <windows.h>
#endif
#include "ps3rsx.h"

extern "C" uint8_t* vm_base;
extern "C" void* rsx_null_backend_get_hwnd(void);
extern "C" void cellGcm_rsx_event(unsigned events, unsigned user_arg);
extern "C" void spu_lockline_lock(void);
extern "C" void spu_lockline_unlock(void);
extern "C" void spu_coh_notify_write(uint32_t ea);
extern "C" void spu_put_fifo_map(uint32_t ea, uint32_t io, uint32_t size);
extern "C" void spu_put_fifo_unmap(uint32_t io, uint32_t size);
extern "C" int g_gow3_rsx_external;

struct CellGcmRsxHooks {
    int  (*start)(uint32_t context_addr, uint32_t local_size);
    void (*iomap)(uint32_t ea, uint32_t io, uint32_t size);
    void (*iounmap)(uint32_t io, uint32_t size);
    void (*set_display_buffer)(uint32_t id, uint32_t offset, uint32_t pitch, uint32_t width, uint32_t height);
    int  (*flip)(uint32_t id);
};
extern "C" void cellGcm_set_rsx_hooks(const CellGcmRsxHooks* hooks);

// GOW3_FLAGWATCH=<ea hex> (e.g. 70038CEC, the SPURS workload flag RsxSync receives): the RSX's stores that cover
// it, how many left it zero (read inside the lock; the lock-free path reads it after the store) and when the last
// one was -- printed by the GOW3_STALL dump next to the kernel's consumptions of the flag (cellSpurs.c).
extern "C" { volatile unsigned g_gow3_flag_reports = 0, g_gow3_flag_report_zero = 0;
             volatile unsigned long long g_gow3_flag_report_ms = 0; }
static void flag_note(unsigned ea, unsigned size)
{
    static uint32_t w = 1;   /* 1: not read yet; 0: off */
    if (w == 1) { const char* e = getenv("GOW3_FLAGWATCH"); w = e ? (uint32_t)strtoul(e, nullptr, 16) : 0; }
    if (!w || w < ea || w >= ea + size) return;
    g_gow3_flag_reports++;
    g_gow3_flag_report_ms = GetTickCount64();
    uint32_t v; memcpy(&v, vm_base + w, 4);
    if (!v) g_gow3_flag_report_zero++;
}

// A label the RSX wrote: an SPU may hold a reservation on its line (a GETLLAR poll on an RSX fence), and
// must see the line as written, as the PPU's stores do (VM_WRITE_COH).
static void rpcs3_rsx_guest_write(unsigned ea, unsigned size)
{
    if (!size) return;
    flag_note(ea, size);
    spu_lockline_lock();
    for (uint32_t line = ea & ~127u; line < ea + size; line += 128u) spu_coh_notify_write(line);
    spu_lockline_unlock();
}

// The reports and labels the RSX stores into guest memory, made inside the lock-line lock (ps3recomp
// gpu/rsx/Emu/RSX/ps3recomp_store.h): a store that landed between the compare and the commit of an SPU's
// PUTLLC was written back over. The report that zeroes the SPURS workload flag (spurs+0x6C) shares its line
// with what the SPURS kernel commits; a lost zero leaves RsxSync (wid 11) unstarted, label 0x51 unwritten
// and the RSX waiting for it (the bridge's rare stop, semaphore_acquire timed out at 0x2E200510).
// PS3_RSX_STORE_LOCK=0: as before (the store, then rpcs3_rsx_guest_write).
static void rpcs3_rsx_store_unlock(unsigned ea, unsigned size)
{
    flag_note(ea, size);
    for (uint32_t line = ea & ~127u; line < ea + size; line += 128u) spu_coh_notify_write(line);
    spu_lockline_unlock();
}

static int rpcs3_rsx_start(uint32_t context_addr, uint32_t local_size)
{
    // cellGcmInit runs on a guest thread; the window is the frame clock's (the live draw's window).
    void* hwnd = nullptr;
    for (int i = 0; i < 500 && !(hwnd = rsx_null_backend_get_hwnd()); i++) Sleep(10);
    if (!hwnd) {
        fprintf(stderr, "[ps3rsx] no window to present into\n");
        return -1;
    }
    ps3rsx_params p = {};
    p.hwnd = hwnd;
    const char* r = getenv("PS3_RSX_RENDERER");
    p.renderer = (r && !strcmp(r, "opengl")) ? PS3RSX_OPENGL : PS3RSX_VULKAN;
    p.context_addr = context_addr;
    p.local_size = local_size;
    p.on_event = cellGcm_rsx_event;
    p.on_guest_write = rpcs3_rsx_guest_write;
    {
        const char* sl = getenv("PS3_RSX_STORE_LOCK");
        if (!sl || strcmp(sl, "0")) { p.store_lock = spu_lockline_lock; p.store_unlock = rpcs3_rsx_store_unlock; }
        fprintf(stderr, "[ps3rsx] reports and labels stored %s the lock-line lock\n", p.store_lock ? "inside" : "outside");
    }
    if (const char* e = getenv("PS3_PERF_OVERLAY")) p.perf_overlay = atoi(e);
    fprintf(stderr, "[ps3rsx] starting RPCS3's RSX (%s), context 0x%08X, local 0x%X\n",
            p.renderer == PS3RSX_OPENGL ? "OpenGL" : "Vulkan", context_addr, local_size);
    return ps3rsx_start(&p);
}

static int rpcs3_rsx_flip(uint32_t id) { return ps3rsx_flip(id); }

// The io-mapped ranges also go to the SPU PUT path: the GOW3 SPUs write the RSX command stream there, over
// "jump to self" holes, and a PUT that fills one stores the hole last (ps3recomp spu_put_copy).
static void rpcs3_rsx_iomap(unsigned ea, unsigned io, unsigned size)
{
    spu_put_fifo_map(ea, io, size);
    ps3rsx_iomap(ea, io, size);
}
static void rpcs3_rsx_iounmap(unsigned io, unsigned size)
{
    spu_put_fifo_unmap(io, size);
    ps3rsx_iounmap(io, size);
}

static const CellGcmRsxHooks s_rpcs3_hooks = {
    rpcs3_rsx_start, rpcs3_rsx_iomap, rpcs3_rsx_iounmap, ps3rsx_set_display_buffer, rpcs3_rsx_flip,
};

#ifdef _WIN32
// A fault on a page RPCS3's RSX protected (its texture and surface caches watch guest memory): its handler
// unprotects and invalidates; anything else is left to the next handler (the ps3kit's vm_rsx_veh).
static LONG WINAPI vm_rsx_veh(EXCEPTION_POINTERS* ep)
{
    if (ep->ExceptionRecord->ExceptionCode != EXCEPTION_ACCESS_VIOLATION) return EXCEPTION_CONTINUE_SEARCH;
    const ULONG_PTR kind = ep->ExceptionRecord->ExceptionInformation[0];
    const void* addr = (const void*)ep->ExceptionRecord->ExceptionInformation[1];
    if (ps3rsx_handle_fault(addr, kind == 1)) return EXCEPTION_CONTINUE_EXECUTION;
    // not the RSX's: name the first few (guest address, read/write, module, rva and callers for the .map)
    static volatile long n = 0;
    if (InterlockedIncrement(&n) <= 8) {
        const uintptr_t a = (uintptr_t)addr, base = (uintptr_t)vm_base;
        const uintptr_t rip = (uintptr_t)ep->ExceptionRecord->ExceptionAddress;
        HMODULE m = nullptr;
        GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           (LPCSTR)rip, &m);
        char mod[260] = "?"; if (m) GetModuleFileNameA(m, mod, sizeof mod);
        fprintf(stderr, "[ps3rsx] in %s\n", mod);
        fprintf(stderr, "[ps3rsx] fault %s host %p (guest 0x%08llX) at rva 0x%llX tid %lu\n", kind == 1 ? "write" : "read",
                addr, (unsigned long long)(a >= base && a - base < 0x100000000ull ? a - base : 0xFFFFFFFFull),
                (unsigned long long)(m ? rip - (uintptr_t)m : rip), GetCurrentThreadId());
        { // the callers (rvas in the exe, for the .map)
          CONTEXT c = *ep->ContextRecord;
          for (int f = 0; f < 12 && c.Rip; f++) {
              DWORD64 ib = 0; PRUNTIME_FUNCTION rf = RtlLookupFunctionEntry(c.Rip, &ib, nullptr);
              fprintf(stderr, "[ps3rsx]   #%d rva 0x%llX%s", f, (unsigned long long)(ib ? c.Rip - ib : c.Rip), "\n");
              if (!rf) { c.Rip = *(DWORD64*)c.Rsp; c.Rsp += 8; continue; }
              void* hd = nullptr; DWORD64 ef = 0;
              RtlVirtualUnwind(UNW_FLAG_NHANDLER, ib, c.Rip, rf, &c, &hd, &ef, nullptr);
          } }
        fflush(stderr);
    }
    return EXCEPTION_CONTINUE_SEARCH;
}
#endif

// From main.cpp, in place of its own guest memory: 1 when RPCS3's RSX took over (vm_base is its vm),
// 0 when PS3_RSX does not ask for it (main.cpp then allocates as always).
extern "C" int gow3_rsx_select(void)
{
    /* Default since 13/11 (Celso's ok): RPCS3's RSX when PS3_RSX is unset; PS3_RSX=live (any value other
     * than rpcs3) keeps the live draw. */
    if (!getenv("PS3_RSX")) {
#ifdef _WIN32
        _putenv_s("PS3_RSX", "rpcs3");
        SetEnvironmentVariableA("PS3_RSX", "rpcs3");
#else
        setenv("PS3_RSX", "rpcs3", 0);
#endif
    }
    if (!ps3rsx_requested()) return 0;
#ifdef _WIN32
    AddVectoredExceptionHandler(1, vm_rsx_veh);
#endif
    vm_base = ps3rsx_init_memory();
    if (!vm_base) {
        fprintf(stderr, "[ps3rsx] RPCS3's vm did not come up\n");
        return 0;
    }
    atexit(ps3rsx_shutdown);
#ifdef _WIN32
    _putenv_s("RSX_LIVE_DRAW", "0");   // the live draw stays out; its window is the RSX's
#endif
    g_gow3_rsx_external = 1;           // gow3_rsx.cpp: the null backend's window, no present of its own
    cellGcm_set_rsx_hooks(&s_rpcs3_hooks);
    fprintf(stderr, "[ps3rsx] RPCS3's RSX selected (PS3_RSX=rpcs3)\n");
    return 1;
}
