// SPDX-License-Identifier: GPL-2.0-only
/*
 * GOW3 Native: watchdog de travamento (Windows). GOW3_WATCHDOG=<s> espera <s> segundos e então, a
 * cada 5 s, imprime para cada thread o RIP (módulo + RVA) e os endereços de retorno do próprio
 * executável achados na pilha, e quais threads do jogo estão dentro de uma chamada HLE. Os RVAs se
 * resolvem com o GOW3Native.map que o link gera (/MAP). Inspirado no hang_watchdog do boot_main.cpp
 * do ps3recomp, reduzido ao que o GOW3 precisa.
 */
#ifdef _WIN32
#include <windows.h>
#include <tlhelp32.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

extern "C" const char* g_hle_inflight[];   /* ppu_hle.cpp, 64 entradas */

static char s_buf[1 << 16];
static size_t s_len;

/* Nada de stdio com uma thread suspensa: ela pode ter o lock do CRT. Junta tudo e escreve depois. */
static void add(const char* fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(s_buf + s_len, sizeof s_buf - s_len, fmt, ap);
    va_end(ap);
    if (n > 0) s_len = s_len + (size_t)n < sizeof s_buf ? s_len + (size_t)n : sizeof s_buf - 1;
}

static void module_of(uint64_t addr, HMODULE* m, const char** name, char* path, size_t n)
{
    *m = NULL;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCSTR)addr, m);
    path[0] = '?'; path[1] = 0;
    if (*m) GetModuleFileNameA(*m, path, (DWORD)n);
    const char* s = strrchr(path, '\\');
    *name = s ? s + 1 : path;
}

extern "C" uint8_t* vm_base;

static uint32_t peek32(uint32_t ea)
{
    const uint8_t* p = vm_base + ea;
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
}

/* GOW3_PEEK="ea[,ea...]": u32 em cada EA; "*ea" segue o ponteiro e mostra 4 palavras a partir dele. */
static void peek(void)
{
    const char* e = getenv("GOW3_PEEK");
    if (!e || !vm_base) return;
    char buf[512];
    snprintf(buf, sizeof buf, "%s", e);
    for (char* t = strtok(buf, ","); t; t = strtok(NULL, ",")) {
        int deref = *t == '*';
        uint32_t ea = (uint32_t)strtoul(t + deref, NULL, 16);
        uint32_t v = peek32(ea);
        if (!deref) { add("[GOW3-WD]   [0x%08X] = 0x%08X\n", ea, v); continue; }
        add("[GOW3-WD]   [0x%08X] = 0x%08X ->", ea, v);
        for (int k = 0; k < 4 && v; k++) add(" +%X:0x%08X", k * 4, peek32(v + k * 4));
        add("\n");
    }
}

static void dump(HMODULE self, int round)
{
    s_len = 0;
    add("[GOW3-WD] rodada %d\n", round);
    peek();
    for (unsigned t = 0; t < 64u; t++)
        if (g_hle_inflight[t]) add("[GOW3-WD]   guest-tid %u dentro de %s\n", t, g_hle_inflight[t]);
    DWORD me = GetCurrentThreadId(), pid = GetCurrentProcessId();
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    THREADENTRY32 te;
    te.dwSize = sizeof te;
    if (snap != INVALID_HANDLE_VALUE && Thread32First(snap, &te)) {
        do {
            if (te.th32OwnerProcessID != pid || te.th32ThreadID == me) continue;
            HANDLE th = OpenThread(THREAD_GET_CONTEXT | THREAD_SUSPEND_RESUME, FALSE, te.th32ThreadID);
            if (!th) continue;
            SuspendThread(th);
            CONTEXT c;
            c.ContextFlags = CONTEXT_CONTROL;
            if (GetThreadContext(th, &c)) {
                HMODULE m; const char* mn; char path[MAX_PATH];
                module_of(c.Rip, &m, &mn, path, sizeof path);
                add("[GOW3-WD] tid %5lu rip %s+0x%llX ret:", (unsigned long)te.th32ThreadID, mn,
                    m ? (unsigned long long)(c.Rip - (uint64_t)m) : (unsigned long long)c.Rip);
                MEMORY_BASIC_INFORMATION mbi;
                uint64_t* sp = (uint64_t*)c.Rsp;
                uint64_t end = (uint64_t)sp;
                if (VirtualQuery(sp, &mbi, sizeof mbi) && mbi.State == MEM_COMMIT &&
                    !(mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD)))
                    end = (uint64_t)mbi.BaseAddress + mbi.RegionSize;
                int found = 0;
                for (uint64_t* p = sp; (uint64_t)(p + 1) <= end && p < sp + 0x20000 && found < 14; p++) {
                    HMODULE mm = NULL;
                    if (*p < (uint64_t)self) continue;
                    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                                       GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT, (LPCSTR)*p, &mm);
                    if (mm == self) { add(" 0x%llX", (unsigned long long)(*p - (uint64_t)self)); found++; }
                }
                add("\n");
            }
            ResumeThread(th);
            CloseHandle(th);
        } while (Thread32Next(snap, &te));
    }
    if (snap != INVALID_HANDLE_VALUE) CloseHandle(snap);
    fwrite(s_buf, 1, s_len, stderr);
    fflush(stderr);
}

extern "C" void ppu_report_guest_lrs(void);   /* ppu_loader.cpp: LR do PS3 de cada thread do jogo */

static DWORD WINAPI watchdog(LPVOID arg)
{
    int first = (int)(intptr_t)arg;
    HMODULE self = GetModuleHandleA(NULL);
    Sleep((DWORD)first * 1000);
    for (int round = 1; round <= 6; round++) {
        fprintf(stderr, "[GOW3-WD] LRs do PS3 (rodada %d):\n", round);
        ppu_report_guest_lrs();
        dump(self, round);
        Sleep(5000);
    }
    return 0;
}

static int start_watchdog()
{
    const char* e = getenv("GOW3_WATCHDOG");
    int s = e ? atoi(e) : 0;
    if (s > 0) CreateThread(NULL, 0, watchdog, (LPVOID)(intptr_t)s, 0, NULL);
    return s;
}

static int s_started = start_watchdog();

/* GOW3_WATCH_EA=<ea hex>: armadilha de escrita na página do PS3 que contém <ea>. Cada escrita nela
 * gera uma linha com o RIP do código que escreveu (resolver com o .map) e o valor novo do u32 em <ea>,
 * lido depois da escrita. A página fica protegida contra escrita; o tratador libera, executa a
 * instrução em passo único e protege de novo. Só diagnóstico: deixa cada escrita na página lenta.
 * Limitação conhecida: um tratador de faltas do runtime pode receber a falta antes deste e repeti-la
 * em laço; nesse caso o jogo para e nada é registrado. */
static uint8_t* s_watch_page;
static uint32_t s_watch_ea;
/* RIP da escrita que caiu na armadilha, por thread, até o passo único seguinte. */
static __declspec(thread) uint64_t g_gow3_watch_rip;

static LONG WINAPI watch_veh(EXCEPTION_POINTERS* ep)
{
    EXCEPTION_RECORD* er = ep->ExceptionRecord;
    if (er->ExceptionCode == EXCEPTION_ACCESS_VIOLATION && er->ExceptionInformation[0] == 1) {
        uint8_t* a = (uint8_t*)er->ExceptionInformation[1];
        if (a >= s_watch_page && a < s_watch_page + 0x1000) {
            DWORD old;
            VirtualProtect(s_watch_page, 0x1000, PAGE_READWRITE, &old);
            g_gow3_watch_rip = ep->ContextRecord->Rip;
            ep->ContextRecord->EFlags |= 0x100;   /* passo único: a escrita roda, e o próximo trap loga */
            return EXCEPTION_CONTINUE_EXECUTION;
        }
    }
    if (er->ExceptionCode == EXCEPTION_SINGLE_STEP) {
        if (g_gow3_watch_rip) {
            uint64_t rip = g_gow3_watch_rip;
            g_gow3_watch_rip = 0;
            const uint8_t* p = vm_base + s_watch_ea;
            uint32_t v = ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
            static volatile LONG logged;
            if (InterlockedIncrement(&logged) <= 200) {
                char line[160];
                int n = snprintf(line, sizeof line, "[GOW3-WATCH] escrita na página: rip EXE+0x%llX  [0x%08X]=0x%08X\n",
                                 (unsigned long long)(rip - (uint64_t)GetModuleHandleA(NULL)), s_watch_ea, v);
                DWORD w;
                WriteFile(GetStdHandle(STD_ERROR_HANDLE), line, (DWORD)n, &w, NULL);
            }
            DWORD old;
            VirtualProtect(s_watch_page, 0x1000, PAGE_READONLY, &old);
            return EXCEPTION_CONTINUE_EXECUTION;
        }
    }
    return EXCEPTION_CONTINUE_SEARCH;
}

extern "C" uint32_t cellGcm_control_guest_addr(void);
extern "C" uint32_t ppu_hle_inject_base;

extern "C" void gow3_watch_install(void)
{
    const char* e = getenv("GOW3_WATCH_EA");
    if (!e || !*e || !vm_base) return;
    /* "ctrl" = o registro de controle do GCM (put/get/ref), onde quer que o runtime o tenha posto. */
    s_watch_ea = strcmp(e, "ctrl") == 0 ? cellGcm_control_guest_addr() : (uint32_t)strtoul(e, NULL, 16);
    fprintf(stderr, "[GOW3-WATCH] inject_base=0x%08X controle=0x%08X\n", ppu_hle_inject_base,
            cellGcm_control_guest_addr());
    s_watch_page = vm_base + (s_watch_ea & ~0xFFFu);
    s_watch_page[0] = s_watch_page[0];   /* garante a página já comprometida */
    /* O runtime instala o próprio tratador de faltas (que compromete páginas e repete a instrução)
     * quando o jogo começa a rodar; um tratador nosso instalado antes dele nunca é chamado primeiro e
     * a escrita fica em laço. Instala-se então de uma thread, um instante depois. */
    CreateThread(NULL, 0, [](LPVOID) -> DWORD {
        const char* d = getenv("GOW3_WATCH_DELAY_MS");
        Sleep(d ? (DWORD)atoi(d) : 300);
        AddVectoredExceptionHandler(1, watch_veh);
        DWORD old;
        VirtualProtect(s_watch_page, 0x1000, PAGE_READONLY, &old);
        fprintf(stderr, "[GOW3-WATCH] vigiando escritas na página de 0x%08X\n", s_watch_ea);
        return 0;
    }, NULL, 0, NULL);
}
#else
extern "C" void gow3_watch_install(void) {}
#endif

/* Gancho de depuração para instrumentar à mão uma função recompilada (só em builds locais de
 * investigação): registra as primeiras chamadas com r3 e lr. */
extern "C" void gow3_dbg_call(unsigned fn, unsigned long long r3, unsigned long long lr)
{
    static volatile long n = 0;
    if (n++ < 40) fprintf(stderr, "[GOW3-DBG] func_%08X r3=0x%llX lr=0x%llX\n", fn, r3, lr);
}

extern "C" uint64_t ppu_timebase_now(void);

/* Retorno de uma função recompilada instrumentada à mão: as 8 primeiras vezes e depois 1 a cada 200. */
extern "C" void gow3_dbg_ret(unsigned fn, unsigned long long r3, double f1, unsigned long long arg)
{
    static volatile long n = 0;
    long k = n++;
    if (k < 8 || k % 200 == 0)
        fprintf(stderr, "[GOW3-DBG] #%ld func_%08X -> r3=0x%llX f1=%g arg=0x%llX tb=%llu\n", k, fn, r3, f1, arg,
                (unsigned long long)ppu_timebase_now());
}
