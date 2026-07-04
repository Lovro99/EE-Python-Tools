"""Izvjestaj o odstupanjima — konzola (ANSI boje) i samostojeci HTML."""

import html
from datetime import datetime

from .compare import GRESKA, UPOZORENJE, OK, summary

_ANSI = {GRESKA: "\033[91m", UPOZORENJE: "\033[93m", OK: "\033[92m"}
_RESET = "\033[0m"


def print_console(project, findings, show_ok=False):
    counts = summary(findings)
    print(f"\n=== QC izvjestaj: {project} ===")
    print(
        f"GRESKE: {counts[GRESKA]}   "
        f"UPOZORENJA: {counts[UPOZORENJE]}   OK: {counts[OK]}\n"
    )
    for f in findings:
        if f.status == OK and not show_ok:
            continue
        color = _ANSI[f.status]
        print(f"{color}[{f.status:<10}]{_RESET} {f.tag}  ·  {f.attribute}")
        if f.status == GRESKA:
            for val, sources in f.values.items():
                for fname, _stype, raw, loc in sources:
                    loc_s = f" ({loc})" if loc else ""
                    print(f"    {fname}: '{raw}'{loc_s}")
        elif f.status == UPOZORENJE:
            print(f"    {f.opis()}")
    if counts[GRESKA] == 0 and counts[UPOZORENJE] == 0:
        print("Nema odstupanja — svi izvori se slažu. ✔")


_CSS = """
body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:2rem auto;
     max-width:1100px;padding:0 1rem;color:#1a1a1a;background:#fafafa}
h1{font-size:1.4rem} .meta{color:#666;font-size:.85rem;margin-bottom:1.5rem}
.sum{display:flex;gap:1rem;margin:1rem 0}
.sum div{padding:.6rem 1.2rem;border-radius:8px;font-weight:600}
.s-g{background:#fde8e8;color:#b91c1c}.s-u{background:#fef3cd;color:#92400e}
.s-o{background:#def7e5;color:#166534}
table{border-collapse:collapse;width:100%;background:#fff;font-size:.9rem}
th,td{border:1px solid #e2e2e2;padding:.45rem .7rem;text-align:left;
      vertical-align:top}
th{background:#f1f1f1} tr.g td:first-child{border-left:4px solid #dc2626}
tr.u td:first-child{border-left:4px solid #d97706}
tr.o td:first-child{border-left:4px solid #16a34a}
.b{font-weight:600} .src{color:#555;font-size:.82rem}
@media(prefers-color-scheme:dark){
 body{background:#111;color:#e5e5e5} table{background:#1b1b1b}
 th{background:#262626} th,td{border-color:#333} .src{color:#9a9a9a}}
"""


def write_html(project, findings, out_path, show_ok=True):
    counts = summary(findings)
    now = datetime.now().strftime("%d.%m.%Y. %H:%M")
    rows_html = []
    cls = {GRESKA: "g", UPOZORENJE: "u", OK: "o"}
    for f in findings:
        if f.status == OK and not show_ok:
            continue
        cells = []
        for val, sources in f.values.items():
            for fname, _stype, raw, loc in sources:
                loc_s = f" <span class='src'>({html.escape(loc)})</span>" if loc else ""
                cells.append(
                    f"<div><span class='b'>{html.escape(raw)}</span>"
                    f" — {html.escape(fname)}{loc_s}</div>"
                )
        rows_html.append(
            f"<tr class='{cls[f.status]}'><td>{f.status}</td>"
            f"<td class='b'>{html.escape(f.tag)}</td>"
            f"<td>{html.escape(f.attribute)}</td>"
            f"<td>{''.join(cells)}</td></tr>"
        )

    doc = f"""<!doctype html><html lang="hr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>QC izvještaj — {html.escape(project)}</title>
<style>{_CSS}</style></head><body>
<h1>QC izvještaj — {html.escape(project)}</h1>
<div class="meta">Generirano: {now}</div>
<div class="sum">
  <div class="s-g">Greške: {counts[GRESKA]}</div>
  <div class="s-u">Upozorenja: {counts[UPOZORENJE]}</div>
  <div class="s-o">OK: {counts[OK]}</div>
</div>
<table><thead><tr><th>Status</th><th>Oznaka</th><th>Atribut</th>
<th>Vrijednosti po izvorima</th></tr></thead>
<tbody>{''.join(rows_html)}</tbody></table>
</body></html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)
    return out_path
