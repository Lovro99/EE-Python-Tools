"""
Kreira desktop shortcuts za sve Python programe u ovom folderu.
Pokreni jednom: python create_shortcuts.py
"""

import os
import sys
import platform

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Lijepa imena za programe (ime_fajla -> naziv shortcuta)
# NAPOMENA: imena drzi identicna postojecim .bat-ovima u launchers/ — skripta
# regenerira launchers/<ime>.bat pa krivo ime napravi duplikat umjesto azuriranja.
NAMES = {
    "excelToWord.py":       "Excel u Word",
    "ExcelToPdf.py":        "Excel u PDF",
    "crtanjekabel.py":      "Crtanje Kabela",
    "Print.py":             "Print",
    "Excel to terminal.py": "Excel Terminal",
    "search.py":            "Pretraga",
    "scrapeExcelPodaci.py": "Scrape Excel Podaci",
    "scrape_word.py":       "Scrape Word",
    "pdfPosition.py":       "PDF Pozicija",
    "ExcelPdfPlacer.py":    "Excel PDF Placer",
    "scrape_Excel.py":      "Scrape Excel",
    "CabelLength.py":       "Duzina Kabela",
    "pdfFormFiller.py":     "PDF Form Filler",
    "PrintOrganizer.py":    "PrintOrganizer",
    "hepaFormFiller.py":    "hepaFormFiller",
    "pvsolToExcel.py":      "PVSOL u Excel",
    "syncProperties.py":    "Sync Properties",
    "syncDwgFast.py":       "Sync DWG Fast",
}

# Ne-alati / skripte koje se ne pokrecu direktno pythonw-om
# (web_app.py treba `streamlit run`, generate_doc.py je dev pomagalo).
SKIP = {"create_shortcuts.py", "proba.py", "web_app.py", "generate_doc.py"}

# Alati koji NISU obican .py u root folderu — dobiju samo desktop shortcut,
# a njihovi .bat-ovi u launchers/ su RUCNO odrzavani (ne regeneriraju se ovdje).
#   target: "pythonw" + args, ili direktno .bat
EXTRA = [
    {
        # tkinter app u podfolderu — pokrece se kao modul (kao Razvodne Ploce.bat)
        "name":    "Razvodne Ploce",
        "target":  "pythonw",
        "args":    "-m ormari.app",
        "workdir": SCRIPT_DIR,
    },
    {
        # GUI za batch AutoCAD layoute zivi u zasebnom DwgLayoutCreator repou;
        # launchers/Batch Layouti.bat zna gdje je taj repo, pa shortcut gadja njega.
        "name":    "Batch Layouti",
        "target":  os.path.join(SCRIPT_DIR, "launchers", "Batch Layouti.bat"),
        "args":    "",
        "workdir": os.path.join(SCRIPT_DIR, "launchers"),
    },
]


def get_desktop():
    if platform.system() == "Windows":
        return os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
    # Linux / Mac
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(desktop):
        os.makedirs(desktop, exist_ok=True)
    return desktop


def _ps_shortcut_block(lnk_path, target, args, workdir, name):
    return f"""
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut("{lnk_path}")
$s.TargetPath = "{target}"
$s.Arguments = '{args}'
$s.WorkingDirectory = "{workdir}"
$s.IconLocation = "pythonw.exe"
$s.Description = "{name}"
$s.Save()
Write-Host "Kreiran: {name}"
"""


def create_windows_shortcuts(desktop, python_files):
    ps_lines = []
    for py_file in python_files:
        name = NAMES.get(py_file, py_file.replace(".py", ""))
        script_path = os.path.join(SCRIPT_DIR, py_file)
        lnk_path = os.path.join(desktop, f"{name}.lnk")
        ps_lines.append(_ps_shortcut_block(
            lnk_path, "pythonw", f'"{script_path}"', SCRIPT_DIR, name))

    # dodatni alati (podfolderi / drugi repoi)
    for extra in EXTRA:
        lnk_path = os.path.join(desktop, f"{extra['name']}.lnk")
        ps_lines.append(_ps_shortcut_block(
            lnk_path, extra["target"], extra["args"], extra["workdir"], extra["name"]))

    ps_script = os.path.join(SCRIPT_DIR, "_make_shortcuts.ps1")
    with open(ps_script, "w", encoding="utf-8") as f:
        f.write("\n".join(ps_lines))

    print(f"PowerShell skripta kreirana: {ps_script}")
    print("Pokreci u PowerShell-u:")
    print(f'  powershell -ExecutionPolicy Bypass -File "{ps_script}"')
    print()

    # Takodje kreiraj .bat launcher za svaki program
    # (EXTRA alati se preskacu — njihovi .bat-ovi su rucno odrzavani u launchers/)
    bat_dir = os.path.join(SCRIPT_DIR, "launchers")
    os.makedirs(bat_dir, exist_ok=True)
    for py_file in python_files:
        name = NAMES.get(py_file, py_file.replace(".py", ""))
        script_path = os.path.join(SCRIPT_DIR, py_file)
        bat_path = os.path.join(bat_dir, f"{name}.bat")
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(f'@echo off\npythonw "{script_path}"\n')
        print(f"  BAT launcher: {bat_path}")


def create_linux_shortcuts(desktop, python_files):
    python_exec = sys.executable

    entries = []
    for py_file in python_files:
        name = NAMES.get(py_file, py_file.replace(".py", ""))
        script_path = os.path.join(SCRIPT_DIR, py_file)
        entries.append((name, f'{python_exec} "{script_path}"', SCRIPT_DIR))
    for extra in EXTRA:
        if extra["target"].endswith(".bat"):
            continue  # Windows-only
        entries.append((extra["name"],
                        f'{python_exec} {extra["args"]}'.strip(),
                        extra["workdir"]))

    for name, exec_cmd, workdir in entries:
        desktop_file = os.path.join(desktop, f"{name}.desktop")
        content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name={name}
Exec={exec_cmd}
Path={workdir}
Terminal=false
StartupNotify=true
"""
        with open(desktop_file, "w") as f:
            f.write(content)
        os.chmod(desktop_file, 0o755)
        print(f"  Kreiran: {desktop_file}")


def main():
    py_files = [
        f for f in os.listdir(SCRIPT_DIR)
        if f.endswith(".py") and f not in SKIP
    ]
    py_files.sort()

    desktop = get_desktop()
    print(f"Desktop: {desktop}")
    print(f"Nadeno {len(py_files)} Python programa (+{len(EXTRA)} dodatnih).\n")

    if platform.system() == "Windows":
        print("Windows detektovan — kreiram .lnk shortcuts i .bat launchere...")
        create_windows_shortcuts(desktop, py_files)
    else:
        print("Linux detektovan — kreiram .desktop shortcuts...")
        create_linux_shortcuts(desktop, py_files)

    print("\nGotovo!")


if __name__ == "__main__":
    main()
