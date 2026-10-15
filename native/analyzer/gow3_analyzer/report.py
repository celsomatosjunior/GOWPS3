# SPDX-License-Identifier: GPL-2.0-only
"""Relatórios JSON, CSV e HTML (um arquivo, sem dependências externas).

Só entram metadados: endereços, tamanhos, contagens, nomes de bibliotecas/NIDs e resultados dos
testes. Nenhum byte ou instrução do jogo é copiado para os relatórios.
"""

from __future__ import annotations

import csv
import datetime as dt
import html
import json
from pathlib import Path

from . import __version__

TARGET_TITLE = "BCES00510"


def ladder(report: dict) -> list[dict]:
    ident = report.get("input", {})
    an = report.get("analysis")
    rt = report.get("recompilation_test") or {}
    t = rt.get("totals", {})
    steps = [{"step": "1. Ferramentas compiladas", "state": "ok",
              "detail": f"GOW3_Native_Analyzer {__version__} em execução (ps3recomp, referência e compilador empacotados)"}]
    if an:
        steps.append({"step": "2. Executável analisado", "state": "ok",
                      "detail": f"{an['function_count']} funções PPU, {an['instruction_count']} instruções, "
                                f"{an['import_count']} importações"})
    else:
        steps.append({"step": "2. Executável analisado", "state": "blocked" if ident.get("encrypted") else "todo",
                      "detail": ident.get("status", "sem análise")})
    if t.get("functions"):
        steps.append({"step": "3. Código PPU recompilado", "state": "partial",
                      "detail": f"{t['functions']} funções folha recompiladas e testadas: {t['identical_functions']} "
                                f"idênticas à referência, {t['divergent_functions']} divergentes, "
                                f"{t['inconclusive_functions']} inconclusivas; o restante do executável não foi recompilado"})
    else:
        steps.append({"step": "3. Código PPU recompilado", "state": "todo", "detail": "nenhuma função do jogo testada"})
    for name in ("4. Código SPU recompilado", "5. Runtime inicializado", "6. Primeiro quadro renderizado",
                 "7. Menu principal", "8. Gameplay", "9. Salvamento e carregamento", "10. Jogo completo"):
        steps.append({"step": name, "state": "todo", "detail": ""})
    return steps


def write_json(report: dict, out: Path) -> Path:
    p = out / "relatorio_gow3.json"
    p.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    return p


def write_functions_csv(report: dict, out: Path) -> Path | None:
    an = report.get("analysis")
    if not an:
        return None
    p = out / "funcoes_ppu.csv"
    cols = ["start", "end", "size", "insns", "toc", "callers", "calls", "import_calls", "indirect_calls", "bctr",
            "syscalls", "loops", "loads", "stores", "fp", "vmx", "tls_r13", "unsafe"]
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(cols)
        for fn in an["functions"]:
            row = []
            for c in cols:
                v = fn.get(c)
                row.append(len(v) if isinstance(v, list) else v)
            w.writerow(row)
    return p


STATE_ICON = {"ok": ("✔", "ok"), "partial": ("◐", "partial"), "blocked": ("✖", "blocked"), "todo": ("○", "todo")}

CSS = """
:root{--bg:#f7f7f5;--fg:#1d1d1b;--muted:#6b6b66;--card:#fff;--line:#e2e1dc;--ok:#1f7a3a;--warn:#9a6700;--bad:#b42318;--accent:#2b59c3}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecebe6;--muted:#a3a29b;--card:#1f1f1d;--line:#34332f;--ok:#5cc47a;--warn:#e0b341;--bad:#f07063;--accent:#7ea2ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:32px 0 10px}
.muted{color:var(--muted)}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:10px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}.kpi b{display:block;font-size:22px}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600}.wrap{overflow-x:auto}code{font:12px ui-monospace,Consolas,monospace}
.ok{color:var(--ok)}.partial{color:var(--warn)}.blocked{color:var(--bad)}.todo{color:var(--muted)}
.badge{display:inline-block;padding:1px 8px;border-radius:99px;font-size:12px;border:1px solid currentColor}
details summary{cursor:pointer;color:var(--accent)}.note{border-left:3px solid var(--warn);padding:8px 12px;background:var(--card)}
"""


def _e(v) -> str:
    return html.escape(str(v))


def _table(headers, rows) -> str:
    h = "".join(f"<th>{_e(x)}</th>" for x in headers)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="wrap"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def write_html(report: dict, out: Path) -> Path:
    ident = report["input"]
    an = report.get("analysis")
    rt = report.get("recompilation_test")
    parts = [f"<h1>GOW3 PS3 Native — análise do executável</h1>",
             f'<div class="muted">GOW3_Native_Analyzer {__version__} · {_e(report["generated_at"])}</div>']

    # Arquivo
    sfo = report.get("param_sfo") or {}
    title = sfo.get("TITLE", "")
    tid = sfo.get("TITLE_ID", "")
    rows = [("Arquivo", _e(ident["name"])), ("Tamanho", f"{ident['size']:,} bytes".replace(",", ".")),
            ("SHA-256", f"<code>{_e(ident['sha256'])}</code>"), ("Formato", _e(ident.get("format"))),
            ("Arquitetura", _e((ident.get("elf") or {}).get("machine", "?"))),
            ("Cifrado", "sim" if ident.get("encrypted") else "não"),
            ("Pronto para análise", "sim" if ident.get("ready") else "não")]
    if tid:
        rows.insert(1, ("Jogo (PARAM.SFO)", f"{_e(title)} — {_e(tid)} {_e(sfo.get('APP_VER', ''))}"))
    if ident.get("self_type"):
        rows.append(("Tipo de SELF", _e(ident["self_type"])))
    parts.append("<h2>Arquivo</h2><div class=card>" + _table(["", ""], rows) + "</div>")
    parts.append(f'<div class="note">{_e(ident.get("status", ""))}</div>')
    if tid and tid != TARGET_TITLE:
        parts.append(f'<div class="note">O PARAM.SFO indica {_e(tid)}; o alvo do projeto é {TARGET_TITLE}.</div>')
    if ident.get("segments"):
        seg_rows = [(_e(s["type"]), _e(s["flags"]), f"<code>0x{s['vaddr']:08X}</code>", f"{s['filesz']:,}".replace(",", "."),
                     f"{s['memsz']:,}".replace(",", "."), "sim" if s.get("encrypted") else ("não" if "encrypted" in s else ""))
                    for s in ident["segments"]]
        parts.append("<details><summary>Segmentos</summary>" +
                     _table(["Tipo", "Permissões", "Endereço", "Tamanho no arquivo", "Tamanho na memória", "Cifrado"], seg_rows) +
                     "</details>")

    # Escada
    parts.append("<h2>Escada de progresso</h2><div class=card>")
    lad = []
    for s in report["ladder"]:
        icon, cls = STATE_ICON[s["state"]]
        lad.append((f'<span class="{cls}">{icon}</span> {_e(s["step"])}', _e(s["detail"])))
    parts.append(_table(["Etapa", "Situação"], lad) + "</div>")

    if an:
        sm = an["summary"]
        kpis = [("Funções PPU", an["function_count"]), ("Instruções", an["instruction_count"]),
                ("Importações (NIDs)", an["import_count"]), ("Bibliotecas", len(an["imports"])),
                ("Funções folha", sm["leaf_functions"]), ("Com VMX", sm["with_vmx"]),
                ("Com ponto flutuante", sm["with_fp"]), ("Com chamadas indiretas", sm["with_indirect_calls"]),
                ("Com syscalls diretas", sm["with_syscalls"]), ("Programas SPU embutidos", len(an["spu"]["images"]))]
        parts.append("<h2>Resumo PPU</h2><div class=grid>" +
                     "".join(f'<div class="card kpi"><b>{v:,}</b><span class=muted>{_e(k)}</span></div>'.replace(",", ".")
                             for k, v in kpis) + "</div>")
        lo = an["loader"]
        parts.append(f'<div class="card muted">Entrada: <code>{_e(lo.get("entry_code", "?"))}</code> · TOC: '
                     f'<code>{_e(lo.get("toc", "?"))}</code> · lista completa de funções em <code>funcoes_ppu.csv</code></div>')

        lib_rows = []
        for lib, items in an["imports"].items():
            hle = sum(1 for i in items if i["hle"])
            lib_rows.append((f"<code>{_e(lib)}</code>", len(items), f"{hle}/{len(items)}",
                             sum(i["callers"] for i in items)))
        parts.append("<h2>Bibliotecas do sistema importadas</h2><div class=card>"
                     "<div class=muted>HLE = funções que o runtime do ps3recomp já implementa.</div>" +
                     _table(["Biblioteca", "Funções", "HLE no ps3recomp", "Chamadas no código"], lib_rows) + "</div>")
        imp_rows = []
        for lib, items in an["imports"].items():
            for i in items:
                imp_rows.append((f"<code>{_e(lib)}</code>", _e(i["name"] or "?"), f"<code>{_e(i['nid'])}</code>",
                                 "sim" if i["hle"] else "não", i["callers"]))
        parts.append("<details><summary>Todas as importações</summary>" +
                     _table(["Biblioteca", "Função", "NID", "HLE", "Chamadores"], imp_rows) + "</details>")

        prx = an["prx_dependencies"]
        parts.append("<h2>Dependências PRX e SPU</h2><div class=card>" +
                     f"<p>Arquivos PRX citados no executável: {', '.join(f'<code>{_e(p)}</code>' for p in prx['prx_files_referenced']) or 'nenhum'}</p>" +
                     f"<p>Programas SPU embutidos (ELF SPU): {len(an['spu']['images'])}" +
                     (" — " + ", ".join(f"{_e(i.get('name', '?'))} ({i.get('size', 0):,} bytes)".replace(",", ".")
                                       for i in an["spu"]["images"][:30]) if an["spu"]["images"] else "") + "</p>" +
                     f"<p>Funções PPU que chamam APIs de SPU/SPURS: {an['spu']['functions_calling_spu_apis_count']}</p></div>")
        if an["syscalls"]:
            parts.append("<h2>Syscalls diretas (LV2)</h2><div class=card>" +
                         _table(["Número", "Locais"], [(_e(s["number"] if s["number"] is not None else "?"), s["sites"])
                                                      for s in an["syscalls"]]) + "</div>")
        parts.append("<h2>Fluxo a partir da entrada (até 3 níveis)</h2><details><summary>Mostrar</summary>" +
                     _table(["Função", "Nível", "Chamadas", "Importações usadas"],
                            [(f"<code>{_e(n['func'])}</code>", n["depth"], n.get("calls", "?"),
                              _e(", ".join(n.get("imports", [])))) for n in an["entry_flow"]]) + "</details>")
        parts.append("<h2>Funções mais chamadas</h2><details><summary>Mostrar</summary>" +
                     _table(["Função", "Chamadores"], [(f"<code>{_e(m['func'])}</code>", m["callers"])
                                                      for m in an["most_called"]]) + "</details>")
        parts.append("<h2>Candidatas à recompilação</h2><div class=card><div class=muted>Funções folha, sem syscalls, "
                     "sem bibliotecas do sistema, sem VMX e sem instruções dependentes do sistema.</div>" +
                     _table(["Função", "Início", "Fim", "Instruções", "Por quê"],
                            [(f"<code>{_e(c['func'])}</code>", f"<code>{_e(c['start'])}</code>", f"<code>{_e(c['end'])}</code>",
                              c["insns"], _e(c["why"])) for c in an["candidates"]]) + "</div>")

    if rt and rt.get("status") == "executado":
        t = rt["totals"]
        parts.append("<h2>Teste da recompilação</h2>")
        parts.append(f'<div class=card><p>{_e(rt["method"])}</p><p class=muted>Referência: {_e(rt["reference"])} · '
                     f'executável de teste: <code>{_e(rt["test_executable"])}</code> ({_e(rt["target"])}) · '
                     f'{rt["cases_per_function"]} casos por função</p></div>')
        kp = [("Funções testadas", t["functions"]), ("Idênticas", t["identical_functions"]),
              ("Divergentes", t["divergent_functions"]), ("Inconclusivas", t["inconclusive_functions"]),
              ("Casos", t["cases"]), ("Casos idênticos", t["identical_cases"]),
              ("Falharam igual nos dois", t["both_faulted_cases"]), ("Casos divergentes", t["divergent_cases"])]
        parts.append("<div class=grid>" + "".join(f'<div class="card kpi"><b>{v}</b><span class=muted>{_e(k)}</span></div>'
                                                  for k, v in kp) + "</div>")
        cls = {"idêntica": "ok", "divergente": "blocked", "inconclusiva": "partial"}
        rows = []
        for f in rt["functions"]:
            div = ""
            for d in f["divergences"][:2]:
                div += f"caso {d['case']}: " + "; ".join(
                    f"{_e(x['campo'])} {_e(x.get('recompilado', ''))} ≠ {_e(x.get('referência', ''))}" for x in d["diffs"][:3]) + "<br>"
            rows.append((f"<code>{_e(f['func'])}</code>", f'<span class="badge {cls.get(f["status"], "todo")}">{_e(f["status"])}</span>',
                         f"{f['identical']}/{f['cases']}", f["both_faulted"], f["divergent"], _e(f["why"]), div))
        parts.append("<div class=card>" + _table(["Função", "Resultado", "Idênticos", "Falha igual", "Divergentes",
                                                  "Perfil", "Divergências (amostra)"], rows) + "</div>")
        parts.append("<div class=card><b>Limitações</b><ul>" + "".join(f"<li>{_e(x)}</li>" for x in rt["limitations"]) +
                     "</ul><p class=muted>Arquivos para repetir a comparação: " +
                     ", ".join(f"<code>recomp_test/{_e(x)}</code>" for x in rt["files"]) + "</p></div>")
    elif rt:
        parts.append(f'<h2>Teste da recompilação</h2><div class="note">{_e(rt.get("status"))}: {_e(rt.get("error", ""))}</div>')

    parts.append('<h2>O que isto não prova</h2><div class=card><ul>'
                 '<li>Este relatório descreve o executável e testa funções isoladas. Ele não executa o jogo.</li>'
                 '<li>Funções idênticas à referência mostram que a tradução dessas funções está correta para os '
                 'estados testados; o God of War III só estará recompilado quando todas as etapas da escada estiverem concluídas.</li>'
                 '</ul></div>')
    doc = (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" '
           f'content="width=device-width,initial-scale=1"><title>Relatório GOW3 Native</title><style>{CSS}</style>'
           f'</head><body><main>{"".join(parts)}</main></body></html>')
    p = out / "relatorio_gow3.html"
    p.write_text(doc, encoding="utf-8")
    return p


def now() -> str:
    return dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
