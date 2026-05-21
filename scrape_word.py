import os, glob, csv
from pathlib import Path
from docx_properties import DocxProperties

TARGETS = {
    "pr_inv": ["proizvođač invertera", "proizođač invertera"],
    "md_inv": ["model invertera", "model  invertera"],
    "pr_pan": ["proizvođač panela"],
    "md_pan": ["model panela"],
    "zak_snaga": ["zakupljena snaga"],
    "inst_snaga_fne": ["instalirana snaga fne"],
    "mj_i_dat": ["mjesto i datum"],
    
}


def extract_from_file(path):
    try:
        doc = DocxProperties(path)
        found = {tag: None for tag in TARGETS.keys()}
        custom_props = doc.get_custom_properties()
    except Exception as e:
        print(f"Greška prilikom čitanja datoteke {path}: {e}")
        return None

    for tag, keys in TARGETS.items():
        for key in keys:
            for prop_name, prop_value in custom_props.items():
                if key in prop_name.lower():
                    found[tag] = prop_value
                    break
            if found[tag] is not None:
                break

    found["path"] = os.path.abspath(path)

    # Skip if all extracted values are None (only path present)
    if all(found[k] is None for k in TARGETS.keys()):
        return None

    return [
        found["pr_inv"],
        found["md_inv"],
        found["pr_pan"],
        found["md_pan"],
        found["zak_snaga"],
        found["inst_snaga_fne"],
        found["mj_i_dat"],
        found["path"],
    ]


def run_recursive(root, out_csv):
    rows = []
    patterns = ["**/*.docx", "**/*.docm"]
    for pattern in patterns:
        search_path = str(Path(root) / pattern)
        for path in glob.glob(search_path, recursive=True):
            if Path(path).name.startswith("~"):
                continue
            rec = extract_from_file(path)
            if rec is not None:
                rows.append(rec)

    if not rows:
        print("Nema pronađenih vrijednosti u dokumentima.")
        return

    with open(out_csv, "w", newline="", encoding="utf-16") as f:
        w = csv.writer(f)
        w.writerow([
            "Proizvođač Invertera",
            "Model Invertera",
            "Proizvođač Panela",
            "Model Panela",
            "Zakupljena snaga",
            "Instalirana snaga FNE",
            "Mjesto i datum",
            "Path"
        ])
        w.writerows(rows)

if __name__ == "__main__":
    import tkinter as tk
    from tkinter import filedialog
    root_tk = tk.Tk()
    root_tk.withdraw()

    selected_root = filedialog.askdirectory(title="Odaberite root mapu za pretraživanje (.docx)")
    if not selected_root:
        print("Nije odabrana mapa. Prekid.")
        raise SystemExit(0)

    out_csv_path = filedialog.asksaveasfilename(
        title="Spremi rezultat kao CSV",
        defaultextension=".csv",
        initialfile="rezultat.csv",
        initialdir=selected_root,
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
    )
    if not out_csv_path:
        print("Nije odabran izlazni CSV. Prekid.")
        raise SystemExit(0)

    run_recursive(selected_root, out_csv_path)
    print(f"Gotovo. Rezultat: {out_csv_path}")
