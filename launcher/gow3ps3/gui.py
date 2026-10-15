# SPDX-License-Identifier: GPL-2.0-only
"""Interface do launcher (tkinter, incluso no Python do Windows)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import app, diagnostics, rpcs3, settings as settings_mod, sysinfo

BG, PANEL, TEXT, MUTED, ACCENT = "#151313", "#221d1c", "#efe6dc", "#a39488", "#b3261e"
LEVEL_COLOR = {"ok": "#6fbf73", "aviso": "#e0b44c", "erro": "#ff6b5e"}
LEVEL_MARK = {"ok": "✓", "aviso": "!", "erro": "✗"}


def open_path(path) -> None:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606 - abre a pasta no Explorer
    else:
        subprocess.Popen(["xdg-open", str(path)])


class LauncherWindow:
    def __init__(self, root: tk.Tk, launcher: app.Launcher | None = None):
        self.root = root
        self.launcher = launcher or app.Launcher()
        self.settings = self.launcher.load_settings()
        self.process = None
        root.title(f"{app.APP_NAME} {app.VERSION}")
        root.geometry("900x620")
        root.minsize(760, 520)
        root.configure(bg=BG)
        self._style()
        self.vars: dict[str, tk.Variable] = {}

        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", padx=18, pady=(14, 6))
        tk.Label(header, text="GOW3 PS3 PC", font=("Segoe UI", 20, "bold"), fg=TEXT, bg=BG).pack(side="left")
        tk.Label(header, text="God of War III (PS3) com RPCS3 · projeto independente, sem afiliação com a Sony",
                 fg=MUTED, bg=BG).pack(side="left", padx=12, pady=(8, 0))

        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill="both", expand=True, padx=18, pady=(0, 14))
        self._home(self._tab("HOME"))
        self._graphics(self._tab("GRAPHICS"))
        self._performance(self._tab("PERFORMANCE"))
        self._controls(self._tab("CONTROLS"))
        self._advanced(self._tab("ADVANCED"))
        self.refresh()

    # ---------- montagem ----------
    def _style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background=PANEL, foreground=TEXT, fieldbackground="#2d2625")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#2a2322", foreground=MUTED, padding=(16, 7))
        style.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", TEXT)])
        style.configure("TFrame", background=PANEL)
        style.configure("TLabel", background=PANEL, foreground=TEXT)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("TCheckbutton", background=PANEL, foreground=TEXT)
        style.map("TCombobox", fieldbackground=[("readonly", "#2d2625")], foreground=[("readonly", TEXT)],
                  selectbackground=[("readonly", "#2d2625")], selectforeground=[("readonly", TEXT)])
        self.root.option_add("*TCombobox*Listbox.background", "#2d2625")
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        style.configure("Play.TButton", background=ACCENT, foreground="white", font=("Segoe UI", 13, "bold"),
                        padding=(30, 10))
        style.map("Play.TButton", background=[("active", "#d0342a"), ("disabled", "#5a3a37")])

    def _tab(self, name):
        frame = ttk.Frame(self.tabs, padding=16)
        self.tabs.add(frame, text=name)
        return frame

    def _var(self, name, kind=tk.StringVar):
        var = kind(value=getattr(self.settings, name))
        var.trace_add("write", lambda *_: self._changed(name, var))
        self.vars[name] = var
        return var

    def _changed(self, name, var):
        try:
            setattr(self.settings, name, var.get())
        except tk.TclError:
            return
        self.launcher.save_settings(self.settings)

    def _choice(self, parent, row, label, name, options, kind=tk.StringVar, hint=""):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        box = ttk.Combobox(parent, textvariable=self._var(name, kind), values=list(options),
                           state="readonly", width=34)
        box.grid(row=row, column=1, sticky="w", pady=5)
        if hint:
            ttk.Label(parent, text=hint, style="Muted.TLabel").grid(row=row, column=2, sticky="w", padx=10)

    def _check(self, parent, row, label, name, hint=""):
        ttk.Checkbutton(parent, text=label, variable=self._var(name, tk.BooleanVar)).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=5)
        if hint:
            ttk.Label(parent, text=hint, style="Muted.TLabel").grid(row=row, column=2, sticky="w", padx=10)

    def _path_row(self, parent, row, label, name, command):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self._var(name), width=62).grid(row=row, column=1, sticky="we", pady=4)
        ttk.Button(parent, text="Procurar…", command=command).grid(row=row, column=2, padx=6)

    def _home(self, tab):
        tab.columnconfigure(1, weight=1)
        self._path_row(tab, 0, "RPCS3", "rpcs3_path", self.pick_rpcs3)
        self._path_row(tab, 1, "God of War III", "game_path", self.pick_game)
        self.status = tk.Text(tab, height=14, bg="#1b1716", fg=TEXT, relief="flat", wrap="word",
                              font=("Consolas", 10), padx=10, pady=8)
        self.status.grid(row=2, column=0, columnspan=3, sticky="nsew", pady=12)
        tab.rowconfigure(2, weight=1)
        for level, color in LEVEL_COLOR.items():
            self.status.tag_configure(level, foreground=color)
        bar = ttk.Frame(tab)
        bar.grid(row=3, column=0, columnspan=3, sticky="we")
        ttk.Button(bar, text="Verificar de novo", command=self.refresh).pack(side="left")
        ttk.Button(bar, text="Instalar firmware…", command=self.install_firmware).pack(side="left", padx=8)
        self.play_button = ttk.Button(bar, text="JOGAR", style="Play.TButton", command=self.play)
        self.play_button.pack(side="right")

    def _graphics(self, tab):
        self._choice(tab, 0, "Resolução interna", "internal_resolution", settings_mod.INTERNAL_RESOLUTIONS,
                     hint="720p é a resolução original do jogo")
        self._choice(tab, 1, "Escalonamento para a tela", "output_scaling", settings_mod.SCALING,
                     hint="fsr = AMD FidelityFX Super Resolution 1")
        ttk.Label(tab, text="Nitidez RCAS (0–100)").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Scale(tab, from_=0, to=100, variable=self._var("rcas_sharpening", tk.IntVar),
                  orient="horizontal", length=240).grid(row=2, column=1, sticky="w")
        ttk.Label(tab, text="vale só com FSR", style="Muted.TLabel").grid(row=2, column=2, sticky="w", padx=10)
        self._choice(tab, 3, "Filtragem anisotrópica", "anisotropic", settings_mod.ANISOTROPIC, tk.IntVar,
                     hint="0 = o jogo decide")
        self._choice(tab, 4, "VSync", "vsync", settings_mod.VSYNC)
        self._check(tab, 5, "Tela cheia", "fullscreen")
        ttk.Label(tab, text="Renderizador: Vulkan (fixo). DLSS, XeSS e FSR 3/4 não são suportados.",
                  style="Muted.TLabel").grid(row=6, column=0, columnspan=3, sticky="w", pady=(18, 0))

    def _performance(self, tab):
        self._choice(tab, 0, "Limite de FPS", "frame_limit", settings_mod.FRAME_LIMIT,
                     hint="Auto segue o jogo (até 60)")
        self._choice(tab, 1, "Compilação de shaders", "shader_mode", settings_mod.SHADER_MODE,
                     hint="async_interpreter evita travadas")
        self._choice(tab, 2, "Tamanho de bloco SPU", "spu_block_size", settings_mod.SPU_BLOCK,
                     hint="Safe é o recomendado pela wiki do RPCS3")
        self._choice(tab, 3, "Threads SPU preferidas", "preferred_spu_threads", range(0, 7), tk.IntVar,
                     hint="0 = automático")
        self._check(tab, 4, "Write Color Buffers", "write_color_buffers",
                    hint="recomendado pela wiki para este jogo")
        self._check(tab, 5, "Overlay de desempenho do RPCS3", "performance_overlay")
        self._check(tab, 6, "Avisar quando estiver compilando shaders", "shader_compilation_hint")

    def _controls(self, tab):
        ttk.Label(tab, wraplength=780, justify="left", text=(
            "Os controles usam o sistema do próprio RPCS3 (Xbox/XInput, DualSense, DualShock 4, SDL e teclado). "
            "O botão abaixo abre o RPCS3 com o perfil separado deste launcher: configure em "
            "Configuração → Controles, feche o RPCS3, e a configuração passa a valer aqui."
        )).pack(anchor="w")
        ttk.Button(tab, text="Abrir configuração de controles do RPCS3",
                   command=self.open_rpcs3_ui).pack(anchor="w", pady=14)

    def _advanced(self, tab):
        bar = ttk.Frame(tab)
        bar.pack(fill="x")
        for text, command in (("Diagnóstico do log", self.show_diagnostics),
                              ("Verificar integridade", self.check_integrity),
                              ("Limpar cache do jogo", self.clear_cache),
                              ("Abrir pasta do perfil", lambda: open_path(self.launcher.profile_dir)),
                              ("Abrir salvamentos", lambda: open_path(self.launcher.paths.savedata))):
            ttk.Button(bar, text=text, command=command).pack(side="left", padx=(0, 6))
        self.log_view = tk.Text(tab, bg="#1b1716", fg=TEXT, relief="flat", font=("Consolas", 9), wrap="none")
        self.log_view.pack(fill="both", expand=True, pady=10)
        for level, color in LEVEL_COLOR.items():
            self.log_view.tag_configure(level, foreground=color)

    # ---------- ações ----------
    def _write(self, widget, findings, title=""):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        if title:
            widget.insert("end", title + "\n\n")
        for finding in findings:
            widget.insert("end", f" {LEVEL_MARK[finding.level]}  {finding.message}\n", finding.level)
        widget.configure(state="disabled")

    def refresh(self):
        findings, self.info = self.launcher.preflight(self.settings)
        self._write(self.status, findings)
        self.play_button.state(["disabled"] if any(f.level == "erro" for f in findings) else ["!disabled"])
        threading.Thread(target=self._system_check, daemon=True).start()

    def _system_check(self):
        findings = sysinfo.evaluate(sysinfo.collect())
        self.root.after(0, lambda: self._append_system(findings))

    def _append_system(self, findings):
        self.status.configure(state="normal")
        self.status.insert("end", "\nComputador\n")
        for finding in findings:
            self.status.insert("end", f" {LEVEL_MARK[finding.level]}  {finding.message}\n", finding.level)
        self.status.configure(state="disabled")

    def pick_rpcs3(self):
        path = filedialog.askopenfilename(title="Executável do RPCS3",
                                          filetypes=[("RPCS3", "rpcs3.exe rpcs3 *.AppImage"), ("Todos", "*")])
        if path:
            self.vars["rpcs3_path"].set(path)
            self.refresh()

    def pick_game(self):
        path = filedialog.askdirectory(title="Pasta do God of War III (com PS3_GAME)")
        if path:
            self.vars["game_path"].set(path)
            self.refresh()

    def play(self):
        try:
            self.process = self.launcher.play(self.settings)
        except (RuntimeError, OSError, ValueError) as error:
            messagebox.showerror(app.APP_NAME, str(error))
            return
        self.play_button.state(["disabled"])
        threading.Thread(target=self._wait_game, daemon=True).start()

    def _wait_game(self):
        code = self.process.wait()
        self.root.after(0, lambda: self._game_closed(code))

    def _game_closed(self, code):
        self.refresh()
        report = diagnostics.analyse(self.launcher.paths.log_file)
        if code != 0 or report.explanations:
            text = "\n\n".join(report.explanations) or "Consulte ADVANCED → Diagnóstico do log."
            messagebox.showwarning(app.APP_NAME, f"O RPCS3 terminou com código {code}.\n\n{text}")

    def install_firmware(self):
        path = filedialog.askopenfilename(title="PS3UPDAT.PUP", filetypes=[("Firmware do PS3", "*.PUP")])
        if not path:
            return
        try:
            process = self.launcher.install_firmware(self.settings, path)
        except (RuntimeError, OSError) as error:
            messagebox.showerror(app.APP_NAME, str(error))
            return
        threading.Thread(target=lambda: (process.wait(), self.root.after(0, self.refresh)), daemon=True).start()

    def open_rpcs3_ui(self):
        executable = rpcs3.find_executable(self.settings.rpcs3_path) if self.settings.rpcs3_path else None
        if executable is None:
            messagebox.showerror(app.APP_NAME, "Escolha a pasta do RPCS3 na aba HOME.")
            return
        rpcs3.start([str(executable)], self.launcher.profile_dir, self.launcher.platform)

    def show_diagnostics(self):
        log_file = self.launcher.paths.log_file
        report = diagnostics.analyse(log_file)
        from .game import Finding
        findings = [Finding("aviso", text) for text in report.explanations]
        findings += [Finding("erro", line) for line in report.fatal]
        if not report.found:
            findings = [Finding("aviso", f"Nenhum log ainda em {log_file}")]
        elif not findings:
            findings = [Finding("ok", f"Sem erros fatais. {report.errors} erros e {report.warnings} avisos no log.")]
        self._write(self.log_view, findings, f"Log: {log_file}")
        self.log_view.configure(state="normal")
        self.log_view.insert("end", "\nÚltimas linhas:\n" + diagnostics.tail(log_file, 80))
        self.log_view.configure(state="disabled")

    def check_integrity(self):
        if not getattr(self, "info", None) or not self.info.ok:
            messagebox.showerror(app.APP_NAME, "Escolha uma pasta válida do jogo primeiro.")
            return
        self._write(self.log_view, [], "Calculando SHA-256 de todos os arquivos do jogo…")

        def work():
            findings = self.launcher.check_integrity(self.info)
            self.root.after(0, lambda: self._write(self.log_view, findings, "Integridade"))
        threading.Thread(target=work, daemon=True).start()

    def clear_cache(self):
        serial = getattr(self, "info", None) and self.info.serial
        if not serial:
            return
        target = self.launcher.paths.cache_dir / serial
        if target.is_dir() and messagebox.askyesno(
                app.APP_NAME, f"Apagar {target}?\nPPU, SPU e shaders serão recompilados no próximo início."):
            shutil.rmtree(target)
            self._write(self.log_view, [], f"Cache apagado: {target}")


def main() -> int:
    root = tk.Tk()
    LauncherWindow(root)
    root.mainloop()
    return 0
