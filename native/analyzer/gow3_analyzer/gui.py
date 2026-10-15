# SPDX-License-Identifier: GPL-2.0-only
"""Janela do GOW3_Native_Analyzer (tkinter, já incluído no Python do Windows)."""

from __future__ import annotations

import os
import queue
import sys
import threading
import traceback
import webbrowser
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from . import __version__, pipeline
from .cli import default_output

INTRO = ("Escolha o EBOOT.BIN do God of War III (PS3_GAME\\USRDIR\\EBOOT.BIN), um EBOOT.ELF preparado por você, "
         "ou a pasta do jogo. O programa lê o arquivo no seu computador e gera relatórios JSON e HTML; nada é enviado "
         "para a internet. Ele não decifra executáveis: um EBOOT.BIN de varejo cifrado é identificado, e a análise "
         "das funções precisa de um EBOOT.ELF que você mesmo prepare a partir da sua cópia.")


class App:
    def __init__(self, root: Tk):
        self.root = root
        root.title(f"GOW3 Native Analyzer {__version__}")
        root.geometry("860x620")
        root.minsize(640, 460)
        self.events: queue.Queue = queue.Queue()
        self.path = StringVar()
        self.out = StringVar(value=str(default_output()))
        self.recompile = BooleanVar(value=True)
        self.report_path = None

        frm = ttk.Frame(root, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=INTRO, wraplength=820, justify="left").pack(anchor="w", pady=(0, 10))

        row = ttk.Frame(frm)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Executável:", width=12).pack(side="left")
        ttk.Entry(row, textvariable=self.path).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(row, text="Arquivo…", command=self.pick_file).pack(side="left")
        ttk.Button(row, text="Pasta…", command=self.pick_dir).pack(side="left", padx=(4, 0))

        row2 = ttk.Frame(frm)
        row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="Relatórios em:", width=12).pack(side="left")
        ttk.Entry(row2, textvariable=self.out).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(row2, text="Escolher…", command=self.pick_out).pack(side="left")

        ttk.Checkbutton(frm, text="Recompilar e testar as funções candidatas (gera GOW3_Native_RecompTest.exe)",
                        variable=self.recompile).pack(anchor="w", pady=6)

        row3 = ttk.Frame(frm)
        row3.pack(fill="x", pady=4)
        self.run_btn = ttk.Button(row3, text="Analisar", command=self.start)
        self.run_btn.pack(side="left")
        self.open_btn = ttk.Button(row3, text="Abrir relatório", command=self.open_report, state="disabled")
        self.open_btn.pack(side="left", padx=6)
        self.folder_btn = ttk.Button(row3, text="Abrir pasta", command=self.open_folder, state="disabled")
        self.folder_btn.pack(side="left")
        self.bar = ttk.Progressbar(row3, mode="indeterminate")
        self.bar.pack(side="left", fill="x", expand=True, padx=(12, 0))

        self.log = ScrolledText(frm, height=20, font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, pady=(6, 0))
        root.after(100, self.poll)

    def pick_file(self):
        p = filedialog.askopenfilename(title="Escolha o EBOOT.BIN ou o EBOOT.ELF",
                                       filetypes=[("Executável do PS3", "*.BIN *.bin *.ELF *.elf *.self *.SELF"),
                                                  ("Todos os arquivos", "*.*")])
        if p:
            self.path.set(p)

    def pick_dir(self):
        p = filedialog.askdirectory(title="Escolha a pasta do jogo (a que contém PS3_GAME) ou a USRDIR")
        if p:
            self.path.set(p)

    def pick_out(self):
        p = filedialog.askdirectory(title="Pasta dos relatórios")
        if p:
            self.out.set(p)

    def say(self, msg: str):
        self.events.put(("log", msg))
        try:
            out = Path(self.out.get().strip())
            out.mkdir(parents=True, exist_ok=True)
            with open(out / "analise.log", "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except OSError:
            pass

    def start(self):
        if not self.path.get().strip():
            messagebox.showwarning("GOW3 Native Analyzer", "Escolha primeiro o EBOOT.BIN, o EBOOT.ELF ou a pasta do jogo.")
            return
        self.run_btn.configure(state="disabled")
        self.open_btn.configure(state="disabled")
        self.folder_btn.configure(state="disabled")
        self.log.delete("1.0", "end")
        self.bar.start(12)
        threading.Thread(target=self.work, daemon=True).start()

    def work(self):
        try:
            rep = pipeline.run(self.path.get().strip(), self.out.get().strip(), recompile=self.recompile.get(),
                               progress=self.say)
            self.events.put(("done", rep))
        except Exception as error:
            self.events.put(("error", f"{error}\n\n{traceback.format_exc()}"))

    def poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "log":
                    self.log.insert("end", data + "\n")
                    self.log.see("end")
                elif kind == "done":
                    self.finish(data)
                elif kind == "error":
                    self.bar.stop()
                    self.run_btn.configure(state="normal")
                    self.log.insert("end", "\nERRO: " + data + "\n")
                    self.log.see("end")
                    messagebox.showerror("GOW3 Native Analyzer", data.split("\n")[0])
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def finish(self, rep: dict):
        self.bar.stop()
        self.run_btn.configure(state="normal")
        self.report_path = rep["files"]["html"]
        self.open_btn.configure(state="normal")
        self.folder_btn.configure(state="normal")
        lines = ["", "Concluído.", f"Relatório: {self.report_path}"]
        rt = rep.get("recompilation_test") or {}
        if rt.get("totals"):
            t = rt["totals"]
            lines.append(f"Recompilação: {t['functions']} funções testadas — {t['identical_functions']} idênticas, "
                         f"{t['divergent_functions']} divergentes, {t['inconclusive_functions']} inconclusivas "
                         f"({t['identical_cases']}/{t['cases']} casos idênticos).")
        elif rt.get("status") == "falhou":
            lines.append("O teste de recompilação falhou: " + rt.get("error", "")[:400])
        if not rep["input"].get("ready"):
            lines.append("A análise de funções não foi feita: " + rep["input"].get("status", ""))
        self.log.insert("end", "\n".join(lines) + "\n")
        self.log.see("end")
        self.open_report()

    def open_report(self):
        if self.report_path:
            webbrowser.open(Path(self.report_path).as_uri())

    def open_folder(self):
        if self.report_path:
            folder = str(Path(self.report_path).parent)
            if os.name == "nt":
                os.startfile(folder)  # noqa: S606
            else:
                webbrowser.open(Path(folder).as_uri())


def main():
    root = Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    sys.exit(main())
