# SPDX-License-Identifier: GPL-2.0-only
"""Cliente mínimo do protocolo remoto do GDB (RSP), para ler estados do jogo rodando no RPCS3.

O servidor GDB do RPCS3 (Emu/GDB.cpp) liga sozinho quando um jogo está rodando (configuração
"Misc: GDB Server", padrão 127.0.0.1:2345). Ele atende: ? g p P m M H qfThreadInfo qC Z0 z0 vCont
e a interrupção 0x03. Particularidades tratadas aqui:
- a resposta de parada é só "S05" (sem a thread): a thread parada é achada pelo PC;
- qfThreadInfo vem como "m<id>,<id>...l" numa resposta só;
- XER e FPSCR vêm como "xxxxxxxx" (não informados);
- breakpoints (Z0) só funcionam com o PPU Decoder em "Interpreter"; com LLVM o RPCS3 responde OK
  mas não para.
O QEMU (qemu-ppc64 -g) fala o mesmo protocolo e é usado no autoteste, sem o jogo.
Numeração de registradores do GDB para powerpc64: r0-r31 = 0-31, f0-f31 = 32-63, pc = 64,
msr = 65, cr = 66, lr = 67, ctr = 68, xer = 69, fpscr = 70.
"""

from __future__ import annotations

import socket
import time

REG_PC, REG_CR, REG_LR, REG_CTR, REG_XER = 64, 66, 67, 68, 69


class GdbError(RuntimeError):
    pass


class GdbClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 2345, timeout: float = 10.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # pacotes pequenos sem atraso
        self.sock.settimeout(timeout)
        self.buf = b""

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass

    # --- camada de pacotes -------------------------------------------------------------------
    def _recv_byte(self, deadline: float | None) -> int:
        while not self.buf:
            if deadline is not None:
                left = deadline - time.time()
                if left <= 0:
                    raise TimeoutError
                self.sock.settimeout(min(left, 1.0))
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout:
                continue
            if not chunk:
                raise GdbError("o servidor GDB fechou a conexão")
            self.buf += chunk
        c, self.buf = self.buf[0], self.buf[1:]
        return c

    def _send_packet(self, data: str):
        raw = data.encode("latin-1")
        packet = b"$" + raw + b"#" + ("%02x" % (sum(raw) % 256)).encode()
        for _ in range(5):
            self.sock.sendall(packet)
            ack = self._recv_byte(time.time() + 10)
            if ack == ord("+"):
                return
            if ack != ord("-"):
                # alguns servidores mandam a resposta direto; devolve o byte ao buffer
                self.buf = bytes([ack]) + self.buf
                return
        raise GdbError("o servidor GDB rejeitou o pacote " + data[:40])

    def _recv_packet(self, timeout: float | None = 10.0) -> str:
        deadline = None if timeout is None else time.time() + timeout
        while True:
            c = self._recv_byte(deadline)
            if c == ord("$"):
                break
        body = bytearray()
        while True:
            c = self._recv_byte(deadline)
            if c == ord("#"):
                break
            body.append(c)
        self._recv_byte(deadline)
        self._recv_byte(deadline)  # checksum (TCP já garante a integridade)
        self.sock.sendall(b"+")
        out = bytearray()
        i = 0
        while i < len(body):  # escape '}'
            if body[i] == 0x7D and i + 1 < len(body):
                out.append(body[i + 1] ^ 0x20)
                i += 2
            else:
                out.append(body[i])
                i += 1
        return out.decode("latin-1")

    def command(self, data: str, timeout: float | None = 10.0) -> str:
        self._send_packet(data)
        reply = self._recv_packet(timeout)
        while reply.startswith("O") and not reply.startswith("OK"):  # saída do programa (QEMU)
            reply = self._recv_packet(timeout)
        return reply

    # --- operações ----------------------------------------------------------------------------
    def stop_reason(self) -> str:
        return self.command("?")

    def threads(self) -> list[str]:
        out: list[str] = []
        reply = self.command("qfThreadInfo")
        while reply.startswith("m"):
            body = reply[1:]
            last = body.endswith("l")
            out += [t for t in body.rstrip("l").split(",") if t]
            if last:
                break
            reply = self.command("qsThreadInfo")
        return out

    def select_thread(self, tid: str) -> bool:
        return self.command("Hg" + tid) == "OK"

    def read_register(self, n: int) -> int | None:
        r = self.command("p%x" % n)
        if not r or r.startswith("E") or "x" in r:
            return None
        return int(r, 16)

    def read_all_registers(self) -> dict | None:
        """Comando 'g' (layout powerpc64 do GDB, igual no RPCS3 e no QEMU): 32 GPR e 32 FPR de 8 bytes,
        pc e msr de 8, cr de 4, lr e ctr de 8, xer e fpscr de 4. Campos 'xx' = não informado."""
        r = self.command("g")
        sizes = [8] * 66 + [4, 8, 8, 4, 4]
        if len(r) < sum(sizes) * 2:
            return None
        vals, i = [], 0
        for n in sizes:
            field = r[i:i + 2 * n]
            i += 2 * n
            vals.append(None if "x" in field else int(field, 16))
        return {"gpr": vals[0:32], "fpr": vals[32:64], "pc": vals[64], "cr": vals[66], "lr": vals[67],
                "ctr": vals[68], "xer": vals[69]}

    def read_memory(self, addr: int, size: int, chunk: int = 0x400) -> bytes | None:
        """Lê `size` bytes. Devolve None se o primeiro bloco não puder ser lido; um final parcial
        (memória acaba no meio) volta mais curto."""
        out = bytearray()
        a = addr
        while a < addr + size:
            n = min(chunk, addr + size - a)
            r = self.command("m%x,%x" % (a, n))
            if not r or r.startswith("E"):
                return bytes(out) if out else None
            out += bytes.fromhex(r)
            if len(r) // 2 < n:
                break
            a += n
        return bytes(out)

    def set_breakpoint(self, addr: int) -> bool:
        return self.command("Z0,%x,4" % addr) == "OK"

    def remove_breakpoint(self, addr: int) -> bool:
        return self.command("z0,%x,4" % addr) == "OK"

    def resume(self):
        """Continua todas as threads; não espera a parada (use wait_stop)."""
        self._send_packet("vCont;c")

    def wait_stop(self, timeout: float) -> str | None:
        try:
            return self._recv_packet(timeout)
        except TimeoutError:
            return None

    def interrupt(self, timeout: float = 15.0) -> str | None:
        self.sock.sendall(b"\x03")
        return self.wait_stop(timeout)
