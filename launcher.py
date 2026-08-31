"""
EE Alati - centralni launcher za Python alate
=============================================
Jedno mjesto za pokretanje svih alata: popis s imenom i kratkim opisom,
grupiran po kategorijama. Kad mis miruje iznad retka ~1 s, otvara se
tooltip s duzim opisom i uputama za koristenje. Alat se pokrece
dvoklikom, tipkom Enter ili gumbom "Pokreni".

Pokretanje:  pythonw launcher.py   (ili launchers/EE Alati.bat)

Popis alata, opisi i upute ureduju se u tools.json pored ove skripte -
za dodavanje/izmjenu alata nije potrebno dirati kod. Polja po alatu:
  ime         - naziv u popisu
  skripta     - .py datoteka relativno uz launcher  (ILI "modul", npr. "ormari.app")
  kategorija  - grupa u popisu
  opis        - kratki opis (kolona u popisu)
  dugi_opis   - duzi opis (tooltip)
  upute       - upute za koristenje (tooltip)
  ikona       - emoji ispred imena (opcionalno)
  konzola     - true ako alat treba konzolni prozor (input/print)
  argumenti   - lista dodatnih argumenata (opcionalno)
"""

import json
import os
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, messagebox

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_JSON = os.path.join(SCRIPT_DIR, "tools.json")

TOOLTIP_DELAY_MS = 1000  # mirovanje misa prije prikaza tooltipa
TOOLTIP_WRAP_PX = 440    # sirina teksta u tooltipu
TOOLTIP_BG = "#ffffe0"


def ucitaj_alate():
    with open(TOOLS_JSON, encoding="utf-8") as f:
        return json.load(f)["alati"]


def putanja_skripte(alat):
    """Apsolutna putanja .py datoteke alata, ili None za modul-unose."""
    if "skripta" in alat:
        return os.path.join(SCRIPT_DIR, alat["skripta"])
    return None


def alat_postoji(alat):
    p = putanja_skripte(alat)
    return True if p is None else os.path.isfile(p)


def nadji_interpreter(konzola):
    """pythonw za GUI alate, python za konzolne; fallback sys.executable."""
    if os.name == "nt":
        exe = "python.exe" if konzola else "pythonw.exe"
        kandidat = os.path.join(os.path.dirname(sys.executable), exe)
        if os.path.isfile(kandidat):
            return kandidat
        na_pathu = shutil.which(exe)
        if na_pathu:
            return na_pathu
    return sys.executable


def pokreni_alat(alat):
    konzola = bool(alat.get("konzola"))
    interp = nadji_interpreter(konzola)
    if "modul" in alat:
        cmd = [interp, "-m", alat["modul"]]
    else:
        cmd = [interp, putanja_skripte(alat)]
    cmd += list(alat.get("argumenti", []))

    flags = 0
    if os.name == "nt":
        if konzola:
            flags = subprocess.CREATE_NEW_CONSOLE
        else:
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(cmd, cwd=SCRIPT_DIR, creationflags=flags, close_fds=True)


class Tooltip:
    """Prozorcic s dugim opisom i uputama, prati redak ispod misa."""

    def __init__(self, master):
        self.master = master
        self.win = None

    def prikazi(self, alat, x, y):
        self.sakrij()
        self.win = tk.Toplevel(self.master)
        self.win.wm_overrideredirect(True)
        self.win.attributes("-topmost", True)

        okvir = tk.Frame(self.win, bg=TOOLTIP_BG, bd=1, relief="solid")
        okvir.pack()

        def redak(tekst, **kw):
            pady = kw.pop("pady", 0)
            tk.Label(
                okvir, text=tekst, bg=TOOLTIP_BG, justify="left",
                wraplength=TOOLTIP_WRAP_PX, anchor="w", padx=10, **kw
            ).pack(fill="x", pady=pady)

        naslov = f"{alat.get('ikona', '')} {alat['ime']}".strip()
        redak(naslov, font=("Segoe UI", 10, "bold"), pady=(8, 2))
        if alat.get("dugi_opis"):
            redak(alat["dugi_opis"], font=("Segoe UI", 9), pady=(0, 4))
        if alat.get("upute"):
            redak("Upute:", font=("Segoe UI", 9, "bold"))
            redak(alat["upute"], font=("Segoe UI", 9), pady=(0, 8))
        else:
            redak("", pady=(0, 4))

        # pozicioniraj uz kursor, ali da ne izade van ekrana
        self.win.update_idletasks()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        px, py = x, y
        x = max(min(x + 16, sw - w - 8), 0)
        y = max(min(y + 12, sh - h - 8), 0)
        if x <= px <= x + w and y <= py <= y + h:
            # ne smije zavrsiti pod kursorom (izaziva Leave pa treperi)
            y = max(py - h - 12, 0)
        self.win.wm_geometry(f"+{x}+{y}")

    def sakrij(self):
        if self.win is not None:
            self.win.destroy()
            self.win = None


class LauncherApp:
    def __init__(self, root, alati):
        self.root = root
        self.alati = alati
        self.tooltip = Tooltip(root)
        self._hover_iid = None
        self._hover_job = None

        root.title("EE Alati")
        root.geometry("860x600")
        root.minsize(620, 400)
        self._build_ui()
        self._popuni()

    # -- UI ----------------------------------------------------------------
    def _build_ui(self):
        vrh = tk.Frame(self.root)
        vrh.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(vrh, text="Traži:", font=("Segoe UI", 9)).pack(side="left")
        self.trazi_var = tk.StringVar()
        self.trazi_var.trace_add("write", lambda *a: self._popuni())
        entry = tk.Entry(vrh, textvariable=self.trazi_var, font=("Segoe UI", 10))
        entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
        entry.focus_set()

        sredina = tk.Frame(self.root)
        sredina.pack(fill="both", expand=True, padx=10, pady=4)

        self.tree = ttk.Treeview(sredina, columns=("opis",), selectmode="browse")
        self.tree.heading("#0", text="Alat", anchor="w")
        self.tree.heading("opis", text="Opis", anchor="w")
        self.tree.column("#0", width=240, minwidth=180)
        self.tree.column("opis", width=560, minwidth=240)
        self.tree.tag_configure("nedostaje", foreground="#9a9a9a")
        self.tree.tag_configure("kategorija", font=("Segoe UI", 9, "bold"))

        scroll = ttk.Scrollbar(sredina, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.tree.bind("<Motion>", self._na_pomak)
        self.tree.bind("<Leave>", lambda e: self._ugasi_tooltip())
        self.tree.bind("<ButtonPress>", lambda e: self._ugasi_tooltip())
        self.tree.bind("<MouseWheel>", lambda e: self._ugasi_tooltip())
        self.tree.bind("<Double-1>", self._na_dvoklik)
        self.tree.bind("<Return>", lambda e: self._pokreni_odabrani())

        dno = tk.Frame(self.root)
        dno.pack(fill="x", padx=10, pady=(4, 10))
        tk.Button(
            dno, text="▶  Pokreni", font=("Segoe UI", 10, "bold"),
            command=self._pokreni_odabrani, padx=14,
        ).pack(side="right")
        self.status_var = tk.StringVar(
            value="Dvoklik na alat za pokretanje · zadrži miš iznad retka za upute"
        )
        tk.Label(
            dno, textvariable=self.status_var, font=("Segoe UI", 8),
            fg="#777777", anchor="w",
        ).pack(side="left", fill="x", expand=True)

    def _popuni(self):
        self._ugasi_tooltip()
        self.tree.delete(*self.tree.get_children())
        filtar = self.trazi_var.get().casefold().strip()

        kategorije = {}  # naziv -> iid cvora (redoslijed iz tools.json)
        for i, alat in enumerate(self.alati):
            if filtar and not self._odgovara(alat, filtar):
                continue
            kat = alat.get("kategorija", "Ostalo")
            if kat not in kategorije:
                kategorije[kat] = self.tree.insert(
                    "", "end", text=kat, open=True, tags=("kategorija",)
                )
            postoji = alat_postoji(alat)
            ime = f"{alat.get('ikona', '')} {alat['ime']}".strip()
            if not postoji:
                ime += "  (nije pronađen)"
            self.tree.insert(
                kategorije[kat], "end", iid=f"alat-{i}", text=ime,
                values=(alat.get("opis", ""),),
                tags=() if postoji else ("nedostaje",),
            )

    @staticmethod
    def _odgovara(alat, filtar):
        polja = (
            alat.get("ime", ""), alat.get("opis", ""),
            alat.get("dugi_opis", ""), alat.get("kategorija", ""),
        )
        return any(filtar in p.casefold() for p in polja)

    def _alat_za_iid(self, iid):
        if iid and iid.startswith("alat-"):
            return self.alati[int(iid.split("-", 1)[1])]
        return None

    # -- tooltip -----------------------------------------------------------
    def _na_pomak(self, event):
        iid = self.tree.identify_row(event.y)
        if iid == self._hover_iid:
            return
        self._ugasi_tooltip()
        self._hover_iid = iid
        if self._alat_za_iid(iid) is not None:
            self._hover_job = self.root.after(
                TOOLTIP_DELAY_MS,
                lambda: self.tooltip.prikazi(
                    self._alat_za_iid(iid), event.x_root, event.y_root
                ),
            )

    def _ugasi_tooltip(self):
        if self._hover_job is not None:
            self.root.after_cancel(self._hover_job)
            self._hover_job = None
        self._hover_iid = None
        self.tooltip.sakrij()

    # -- pokretanje ----------------------------------------------------------
    def _na_dvoklik(self, event):
        alat = self._alat_za_iid(self.tree.identify_row(event.y))
        if alat is not None:
            self._pokreni(alat)
            return "break"  # ne toggle-aj kategoriju

    def _pokreni_odabrani(self):
        sel = self.tree.selection()
        if sel:
            alat = self._alat_za_iid(sel[0])
            if alat is not None:
                self._pokreni(alat)

    def _pokreni(self, alat):
        self._ugasi_tooltip()
        if not alat_postoji(alat):
            messagebox.showwarning(
                "Alat nije pronađen",
                f"Skripta ne postoji:\n{putanja_skripte(alat)}",
            )
            return
        try:
            pokreni_alat(alat)
            self.status_var.set(f"Pokrenuto: {alat['ime']}")
        except Exception as e:
            messagebox.showerror("Greška pri pokretanju", f"{alat['ime']}\n\n{e}")


def main():
    try:
        alati = ucitaj_alate()
    except Exception as e:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "EE Alati", f"Ne mogu učitati tools.json:\n{TOOLS_JSON}\n\n{e}"
        )
        return
    root = tk.Tk()
    LauncherApp(root, alati)
    root.mainloop()


if __name__ == "__main__":
    main()
