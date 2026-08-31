#!/usr/bin/env python3
"""QC sustav — CLI.

Primjeri:
  python qc.py scan  C:/Projekti/FNE_Vrbovec --projekt FNE_Vrbovec
  python qc.py report --projekt FNE_Vrbovec --html izvjestaj.html
  python qc.py demo                  # napravi demo projekt i pokreni sve
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from qc_core import db
from qc_core.compare import run_compare, summary, GRESKA
from qc_core.report import print_console, write_html
from qc_core.scan import load_config, scan_project

HERE = Path(__file__).parent
DEFAULT_DB = HERE / "qc.db"
DEFAULT_CONFIG = HERE / "qc_config.yaml"


def cmd_scan(args):
    config = load_config(args.config)
    conn = db.connect(args.db)
    project = args.projekt or Path(args.mapa).resolve().name
    results = scan_project(conn, project, args.mapa, config)
    if not results:
        print(
            f"Nijedna datoteka u '{args.mapa}' ne odgovara predlošcima "
            f"iz {args.config}."
        )
        return 1
    print(f"Projekt: {project}")
    for fname, template, n in results:
        print(f"  {fname}  [{template}]  ->  {n}"
              + ("" if isinstance(n, str) else " opažanja"))
    print("\nSken gotov. Pokreni: "
          f"python qc.py report --projekt {project}")
    return 0


def cmd_report(args):
    conn = db.connect(args.db)
    projects = db.list_projects(conn)
    if not projects:
        print("Baza je prazna — prvo pokreni 'scan'.")
        return 1
    project = args.projekt
    if project is None:
        if len(projects) == 1:
            project = projects[0]
        else:
            print("Vise projekata u bazi, odaberi --projekt: "
                  + ", ".join(projects))
            return 1
    findings = run_compare(conn, project)
    print_console(project, findings, show_ok=args.sve)
    if args.html:
        path = write_html(project, findings, args.html)
        print(f"\nHTML izvjestaj: {path}")
    counts = summary(findings)
    return 2 if counts[GRESKA] else 0


def cmd_demo(args):
    from demo.make_demo import make_demo_project

    demo_dir = HERE / "demo_projekt"
    make_demo_project(demo_dir)
    print(f"Demo projekt kreiran u: {demo_dir}\n")

    config = load_config(DEFAULT_CONFIG)
    conn = db.connect(args.db)
    results = scan_project(conn, "DEMO", demo_dir, config)
    for fname, template, n in results:
        print(f"  {fname}  [{template}]  ->  {n} opažanja")

    findings = run_compare(conn, "DEMO")
    print_console("DEMO", findings, show_ok=True)
    html_path = write_html("DEMO", findings, HERE / "demo_izvjestaj.html")
    print(f"\nHTML izvjestaj: {html_path}")
    return 0


def main():
    p = argparse.ArgumentParser(description="QA/QC provjera usklađenosti "
                                "podataka (DWG/Excel/Word)")
    p.add_argument("--db", default=str(DEFAULT_DB), help="putanja SQLite baze")
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("scan", help="skeniraj projektnu mapu u bazu")
    ps.add_argument("mapa", help="mapa projekta s xlsx/docx/csv datotekama")
    ps.add_argument("--projekt", help="ime projekta (default: ime mape)")
    ps.add_argument("--config", default=str(DEFAULT_CONFIG))
    ps.set_defaults(fn=cmd_scan)

    pr = sub.add_parser("report", help="ispisi i generiraj izvjestaj")
    pr.add_argument("--projekt")
    pr.add_argument("--html", help="putanja izlaznog HTML izvjestaja")
    pr.add_argument("--sve", action="store_true",
                    help="prikazi i retke koji su OK")
    pr.set_defaults(fn=cmd_report)

    pd = sub.add_parser("demo", help="kreiraj demo projekt i pokreni QC")
    pd.set_defaults(fn=cmd_demo)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
