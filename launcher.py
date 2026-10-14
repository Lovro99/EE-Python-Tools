"""
EE Alati - centralni launcher za Python alate
=============================================
Jedno mjesto za pokretanje svih alata: popis s imenom, kratkim opisom,
verzijom i datumom zadnje promjene, grupiran po kategorijama. Kad mis miruje
iznad retka ~1 s, otvara se tooltip s duzim opisom i uputama. Alat se
pokrece dvoklikom, tipkom Enter ili gumbom "Pokreni".

Pokretanje:  preko precaca "EE Alati" (napravi ga Instaliraj EE Alati.bat)
             ili rucno: pythonw launcher.py

Dva nacina rada (odabire se sam):
  RAZVOJ   - launcher je u git repou: svakih 5 min provjeri GitHub i javi
             kad ima novih promjena (azurira se tek kad kliknes "Azuriraj");
             izbornik "Verzija" pokrece alate s bilo koje grane (testna
             kopija u .grane/), npr. da isprobas promjenu prije merge-a.
  STABILNO - launcher je na network shareu (deploy.ps1): kolege vide samo
             objavljenu verziju, info o njoj cita se iz VERSION.json.

Popis alata, opisi i upute ureduju se u tools.json - za dodavanje/izmjenu
alata nije potrebno dirati kod. Polja po alatu:
  ime         - naziv u popisu
  skripta     - .py datoteka relativno uz launcher  (ILI "modul", npr. "ormari.app")
                (moze i apsolutna putanja za alat izvan repoa)
  verzija     - broj verzije alata, npr. "1.2" (povecaj kad mijenjas alat)
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
import threading
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import ttk, messagebox

import launcher_git as lg

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

PROVJERA_MS = 5 * 60 * 1000  # koliko cesto provjeravati ima li novih promjena
NOVO_DANA = 7                # alat promijenjen u zadnjih N dana oznaci kao novo
TOOLTIP_DELAY_MS = 1000      # mirovanje misa prije prikaza tooltipa
TOOLTIP_WRAP_PX = 440        # sirina teksta u tooltipu
TOOLTIP_BG = "#ffffe0"
BOJA_TEST = "#f4a340"        # traka "testna grana"
BOJA_OBAVIJEST = "#d6eaff"   # traka "dostupna nova verzija"
LAUNCHER_DATOTEKE = {"launcher.py", "launcher_git.py"}


def ucitaj_alate(korijen):
    with open(os.path.join(korijen, "tools.json"), encoding="utf-8") as f:
        return json.load(f)["alati"]


def putanja_skripte(alat, korijen):
    """Apsolutna putanja .py datoteke alata, ili None za modul-unose."""
    if "skripta" in alat:
        return os.path.join(korijen, alat["skripta"])
    return None


def alat_postoji(alat, korijen):
    p = putanja_skripte(alat, korijen)
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


def pokreni_alat(alat, korijen, verzija_tekst):
    konzola = bool(alat.get("konzola"))
    interp = nadji_interpreter(konzola)
    skripta = putanja_skripte(alat, korijen)
    if "modul" in alat:
        cmd = [interp, "-m", alat["modul"]]
    else:
        cmd = [interp, skripta]
    cmd += list(alat.get("argumenti", []))

    # alati iz repoa rade u korijenu repoa (ili testne kopije), vanjski u svojoj mapi
    cwd = korijen
    if lg.putanja_alata_u_repou(alat) is None and skripta:
        cwd = os.path.dirname(skripta)

    env = dict(os.environ)
    env["EE_VERZIJA"] = verzija_tekst  # alati ga prikazu u naslovu (ee_verzija.py)

    flags = 0
    if os.name == "nt":
        if konzola:
            flags = subprocess.CREATE_NEW_CONSOLE
        else:
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(cmd, cwd=cwd, env=env, creationflags=flags, close_fds=True)


def je_novo(iso):
    try:
        t = datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return False
    return datetime.now(t.tzinfo) - t < timedelta(days=NOVO_DANA)


class Tooltip:
    """Prozorcic s dugim opisom i uputama, prati redak ispod misa."""

    def __init__(self, master):
        self.master = master
        self.win = None

    def prikazi(self, alat, x, y, verzija_red=""):
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
        if verzija_red:
            redak(verzija_red, font=("Segoe UI", 8), fg="#555555", pady=(0, 4))
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
    def __init__(self, root):
        self.root = root
        self.tooltip = Tooltip(root)
        self._hover_iid = None
        self._hover_job = None

        # git / verzije
        self.razvoj = lg.je_git_repo(SCRIPT_DIR)
        self.korijen = SCRIPT_DIR    # odakle se pokrecu alati (repo ili testna kopija)
        self.glavna = None           # grana glavnog repoa (npr. master)
        self.test_grana = None       # odabrana testna grana, ili None
        self.info = None             # zadnji commit aktivnog korijena
        self.promjene = {}           # putanja alata -> zadnji commit koji ju je dirao
        self.verzija_json = None     # STABILNO: sadrzaj VERSION.json
        self.grane = []              # udaljene grane (najnovija prva)
        self.poznate_grane = None    # za obavijest "nova testna grana"
        self.nove_grane = []
        self.ima_azuriranja = False
        self.zauzet = False          # u tijeku fetch / azuriranje / prebacivanje grane
        self.alati = []

        root.title("EE Alati")
        root.geometry("980x620")
        root.minsize(680, 420)
        self._build_ui()
        self._ucitaj_korijen()
        self._provjeri_pakete()
        if self.razvoj:
            self.root.after(800, self._provjeri_novosti)
        elif os.path.exists(os.path.join(SCRIPT_DIR, ".git")):
            self.status_var.set("Git nije dostupan — provjera novih verzija je isključena")
        self.root.after(PROVJERA_MS, self._periodicka_provjera)

    # -- UI ----------------------------------------------------------------
    def _build_ui(self):
        vrh = tk.Frame(self.root)
        vrh.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(vrh, text="Traži:", font=("Segoe UI", 9)).pack(side="left")
        self.trazi_var = tk.StringVar()
        self.trazi_var.trace_add("write", lambda *a: self._popuni())
        entry = tk.Entry(vrh, textvariable=self.trazi_var, font=("Segoe UI", 10))
        entry.pack(side="left", fill="x", expand=True, padx=(6, 12))
        entry.focus_set()

        if self.razvoj:
            tk.Label(vrh, text="Verzija:", font=("Segoe UI", 9)).pack(side="left")
            self.grana_var = tk.StringVar()
            self.grana_cb = ttk.Combobox(
                vrh, textvariable=self.grana_var, state="readonly", width=46,
                postcommand=self._otvoren_izbornik_grana,
            )
            self.grana_cb.pack(side="left", padx=(6, 0))
            self.grana_cb.bind("<<ComboboxSelected>>", self._na_odabir_grane)
            self._grana_po_oznaci = {}
        else:
            tk.Label(vrh, text="Stabilna verzija", font=("Segoe UI", 9, "bold"),
                     fg="#2e7d32").pack(side="left")

        # trake: testna grana (narancasta) i obavijest o novoj verziji (plava)
        self.traka_test = tk.Label(
            self.root, bg=BOJA_TEST, font=("Segoe UI", 9, "bold"), anchor="w", padx=10,
        )
        self.traka_obavijest = tk.Label(
            self.root, bg=BOJA_OBAVIJEST, font=("Segoe UI", 9), anchor="w",
            padx=10, cursor="hand2",
        )
        self.traka_obavijest.bind("<Button-1>", lambda e: self._azuriraj())

        self.sredina = tk.Frame(self.root)
        self.sredina.pack(fill="both", expand=True, padx=10, pady=4)

        self.tree = ttk.Treeview(
            self.sredina, columns=("opis", "verzija", "promjena"), selectmode="browse"
        )
        self.tree.heading("#0", text="Alat", anchor="w")
        self.tree.heading("opis", text="Opis", anchor="w")
        self.tree.heading("verzija", text="Verzija", anchor="w")
        self.tree.heading("promjena", text="Zadnja promjena", anchor="w")
        self.tree.column("#0", width=230, minwidth=170)
        self.tree.column("opis", width=480, minwidth=220)
        self.tree.column("verzija", width=70, minwidth=55, stretch=False)
        self.tree.column("promjena", width=120, minwidth=95, stretch=False)
        self.tree.tag_configure("nedostaje", foreground="#9a9a9a")
        self.tree.tag_configure("novo", foreground="#1a7f37")
        self.tree.tag_configure("kategorija", font=("Segoe UI", 9, "bold"))

        scroll = ttk.Scrollbar(self.sredina, orient="vertical", command=self.tree.yview)
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
        self.btn_azuriraj = tk.Button(
            dno, text="⟳  Ažuriraj", font=("Segoe UI", 9),
            command=self._azuriraj, padx=10,
        )
        self.btn_azuriraj.pack(side="right", padx=(0, 6))
        if self.razvoj:
            tk.Button(
                dno, text="Objavi kolegama", font=("Segoe UI", 9),
                command=self._objavi_kolegama, padx=10,
            ).pack(side="right", padx=(0, 6))

        lijevo = tk.Frame(dno)
        lijevo.pack(side="left", fill="x", expand=True)
        self.verzija_var = tk.StringVar(value="Verzija: …")
        tk.Label(
            lijevo, textvariable=self.verzija_var, font=("Segoe UI", 8, "bold"),
            fg="#444444", anchor="w",
        ).pack(fill="x")
        self.status_var = tk.StringVar(
            value="Dvoklik na alat za pokretanje · zadrži miš iznad retka za upute"
        )
        tk.Label(
            lijevo, textvariable=self.status_var, font=("Segoe UI", 8),
            fg="#777777", anchor="w",
        ).pack(fill="x")

    def _prikazi_trake(self):
        """Trake su izmedu trazilice i popisa; prikazane samo kad imaju sto reci."""
        for t in (self.traka_test, self.traka_obavijest):
            t.pack_forget()
        if self.test_grana:
            self.traka_test.config(
                text=f"🧪  TESTNA GRANA: {self.test_grana}  — alati se pokreću s ove "
                     f"grane, a ne s glavne. Za normalan rad odaberi "
                     f"„{self.glavna}” u izborniku Verzija."
            )
            self.traka_test.pack(fill="x", padx=10, pady=(2, 0), before=self.sredina)
        poruke = []
        if self.ima_azuriranja:
            poruke.append("🔔 Dostupna je nova verzija — klikni ovdje ili ⟳ Ažuriraj")
        if self.nove_grane:
            imena = ", ".join(self.nove_grane[:3])
            poruke.append(f"🆕 Nova grana za testiranje: {imena} (izbornik Verzija)")
        if poruke:
            self.traka_obavijest.config(text="     ".join(poruke))
            self.traka_obavijest.pack(fill="x", padx=10, pady=(2, 0), before=self.sredina)

    # -- verzija -------------------------------------------------------------
    def _osnova_verzije(self):
        """Dio teksta verzije zajednicki svim alatima (grana · hash)."""
        if self.razvoj and self.info:
            if self.test_grana:
                return f"TEST {self.test_grana} · {self.info['hash']}"
            return f"{self.glavna or 'HEAD'} · {self.info['hash']}"
        if self.verzija_json:
            return f"stabilna · {self.verzija_json['commit']['hash']}"
        return ""

    def _verzija_alata(self, alat):
        """Tekst za EE_VERZIJA (naslov prozora alata)."""
        dijelovi = []
        if alat.get("verzija"):
            dijelovi.append(f"v{alat['verzija']}")
        if self._osnova_verzije():
            dijelovi.append(self._osnova_verzije())
        return " · ".join(dijelovi)

    def _osvjezi_verziju(self):
        if self.razvoj and self.info:
            i = self.info
            gdje = f"TEST {self.test_grana}" if self.test_grana else (self.glavna or "HEAD")
            self.verzija_var.set(f"Verzija: {gdje} · {i['hash']} · {i['datum']} — {i['poruka']}")
        elif self.verzija_json:
            c = self.verzija_json["commit"]
            self.verzija_var.set(
                f"Stabilna verzija: {c['hash']} · {c['datum']} — {c['poruka']}"
            )
        else:
            self.verzija_var.set("Verzija: nepoznata")
        naslov = "EE Alati"
        if self.test_grana:
            naslov += f"  —  TEST: {self.test_grana}"
        self.root.title(naslov)

    def _promjena_alata(self, alat):
        p = lg.putanja_alata_u_repou(alat)
        return self.promjene.get(p) if p else None

    # -- popis -----------------------------------------------------------------
    def _ucitaj_korijen(self):
        """(Ponovno) ucitaj tools.json iz aktivnog korijena i info o verziji."""
        try:
            self.alati = ucitaj_alate(self.korijen)
        except Exception as e:
            self.alati = []
            messagebox.showerror(
                "EE Alati", f"Ne mogu učitati tools.json:\n{self.korijen}\n\n{e}"
            )
        self.promjene = {}
        self._popuni()

        if not self.razvoj:
            self.verzija_json = lg.ucitaj_verziju_json(SCRIPT_DIR)
            if self.verzija_json:
                self.promjene = self.verzija_json.get("alati", {})
            self._osvjezi_verziju()
            self._prikazi_trake()
            self._popuni()
            return

        korijen = self.korijen
        putanje = [lg.putanja_alata_u_repou(a) for a in self.alati]

        def posao():
            return (lg.trenutna_grana(SCRIPT_DIR), lg.info_commita(korijen),
                    lg.zadnje_promjene(korijen, putanje))

        def gotovo(r, greska):
            if korijen != self.korijen:
                return  # u medjuvremenu prebaceno na drugu granu
            if greska:
                self.status_var.set(f"Git: {greska}")
                return
            self.glavna, self.info, self.promjene = r
            self._osvjezi_verziju()
            self._prikazi_trake()
            self._popuni()

        self._u_pozadini(posao, gotovo)

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
            postoji = alat_postoji(alat, self.korijen)
            ime = f"{alat.get('ikona', '')} {alat['ime']}".strip()
            if not postoji:
                ime += "  (nije pronađen)"
            promjena = self._promjena_alata(alat)
            datum = promjena["datum"] if promjena else ""
            tagovi = []
            if not postoji:
                tagovi.append("nedostaje")
            elif promjena and je_novo(promjena.get("iso")):
                tagovi.append("novo")
                datum += "  ★"
            self.tree.insert(
                kategorije[kat], "end", iid=f"alat-{i}", text=ime,
                values=(alat.get("opis", ""), alat.get("verzija", ""), datum),
                tags=tagovi,
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

    # -- pozadinski poslovi --------------------------------------------------
    def _u_pozadini(self, posao, gotovo):
        """posao() u zasebnoj niti (git/mreza ne smrzava prozor), a
        gotovo(rezultat, greska) zatim u GUI niti."""
        stanje = {}

        def radi():
            try:
                stanje["r"] = posao()
            except Exception as e:
                stanje["e"] = e
            stanje["kraj"] = True

        def provjeri():
            if "kraj" not in stanje:
                self.root.after(120, provjeri)
                return
            gotovo(stanje.get("r"), stanje.get("e"))

        threading.Thread(target=radi, daemon=True).start()
        self.root.after(120, provjeri)

    def _zauzmi(self, poruka):
        if self.zauzet:
            return False
        self.zauzet = True
        self.btn_azuriraj.config(state="disabled")
        if self.razvoj:
            self.grana_cb.config(state="disabled")
        self.status_var.set(poruka)
        return True

    def _oslobodi(self, poruka=None):
        self.zauzet = False
        self.btn_azuriraj.config(state="normal")
        if self.razvoj:
            self.grana_cb.config(state="readonly")
        if poruka is not None:
            self.status_var.set(poruka)

    # -- provjera novosti (bez azuriranja) ---------------------------------------
    def _periodicka_provjera(self):
        if not self.zauzet:
            if self.razvoj:
                self._provjeri_novosti(tiho=True)
            else:
                self._provjeri_stabilnu()
        self.root.after(PROVJERA_MS, self._periodicka_provjera)

    def _provjeri_novosti(self, tiho=False):
        """git fetch + usporedba; samo javlja, nista ne mijenja u mapama."""
        if not self._zauzmi("Provjeravam ima li novih promjena na GitHubu…"):
            return
        test_grana = self.test_grana
        korijen = self.korijen

        def posao():
            lg.fetch(SCRIPT_DIR)
            grane = lg.udaljene_grane(SCRIPT_DIR)
            imena = {g["ime"] for g in grane}
            up = lg.upstream(SCRIPT_DIR)
            iza = lg.broj_commita_iza(SCRIPT_DIR, up) if up else 0
            test_iza = test_nestala = False
            if test_grana:
                if test_grana in imena:
                    test_iza = lg.broj_commita_iza(korijen, f"origin/{test_grana}") > 0
                else:
                    test_nestala = True
            lg.ocisti_kopije(SCRIPT_DIR, imena | {test_grana})
            return grane, iza, test_iza, test_nestala

        def gotovo(r, greska):
            if greska:
                self._oslobodi(f"Provjera nije uspjela: {greska}")
                return
            grane, iza, test_iza, test_nestala = r
            self.grane = grane
            imena = [g["ime"] for g in grane]
            if self.poznate_grane is not None:
                for ime in imena:
                    if (ime not in self.poznate_grane and ime != self.glavna
                            and ime not in self.nove_grane):
                        self.nove_grane.append(ime)
            self.poznate_grane = set(imena)
            self.ima_azuriranja = (test_iza if self.test_grana else iza > 0)
            self._popuni_grane()
            self._prikazi_trake()
            if test_nestala:
                poruka = (f"Grana {self.test_grana} više ne postoji na GitHubu "
                          f"(vjerojatno je mergana) — prebaci se na „{self.glavna}”.")
            elif self.ima_azuriranja:
                poruka = "Dostupna je nova verzija."
            else:
                poruka = "Imaš najnoviju verziju." + (
                    f"  (provjereno {datetime.now():%H:%M})" if tiho else "")
            self._oslobodi(poruka)

        self._u_pozadini(posao, gotovo)

    def _provjeri_stabilnu(self):
        """STABILNO: je li u medjuvremenu objavljena nova verzija na share."""
        def gotovo(novi, greska):
            if greska or not novi or not self.verzija_json:
                return
            if novi["commit"]["hash"] != self.verzija_json["commit"]["hash"]:
                self.ima_azuriranja = True
                self._prikazi_trake()

        self._u_pozadini(lambda: lg.ucitaj_verziju_json(SCRIPT_DIR), gotovo)

    # -- grane ------------------------------------------------------------------
    def _popuni_grane(self):
        glavna = self.glavna or "HEAD"
        oznake = {f"{glavna}  (glavna)": None}
        for g in self.grane:
            if g["ime"] == glavna:
                continue
            novo = "🆕 " if g["ime"] in self.nove_grane else ""
            oznake[f"{novo}🧪 {g['ime']}   · {g['datum']}"] = g["ime"]
        if self.test_grana and self.test_grana not in oznake.values():
            oznake[f"🧪 {self.test_grana}   · (obrisana na GitHubu)"] = self.test_grana
        self._grana_po_oznaci = oznake
        self.grana_cb.config(values=list(oznake))
        for oznaka, ime in oznake.items():
            if ime == self.test_grana:
                self.grana_var.set(oznaka)
                break

    def _otvoren_izbornik_grana(self):
        if not self.grane and not self.zauzet:
            self._provjeri_novosti()

    def _na_odabir_grane(self, event=None):
        grana = self._grana_po_oznaci.get(self.grana_var.get())
        if grana == self.test_grana:
            return
        if grana in self.nove_grane:
            self.nove_grane.remove(grana)
        if grana is None:
            self.test_grana = None
            self.korijen = SCRIPT_DIR
            self.ima_azuriranja = False
            self._popuni_grane()
            self._ucitaj_korijen()
            self._provjeri_pakete()
            self._provjeri_novosti(tiho=True)
            return
        if not self._zauzmi(f"Pripremam testnu kopiju grane {grana}…"):
            return

        def gotovo(r, greska):
            if greska:
                self._oslobodi("")
                self._popuni_grane()  # vrati izbornik na prethodnu granu
                messagebox.showerror(
                    "Grana", f"Ne mogu pripremiti granu {grana}:\n\n{greska}"
                )
                return
            put, _stari = r
            self.test_grana = grana
            self.korijen = put
            self.ima_azuriranja = False
            self._popuni_grane()
            self._ucitaj_korijen()
            self._oslobodi(f"Alati se sada pokreću s grane {grana}.")
            self._provjeri_pakete()

        self._u_pozadini(lambda: lg.osiguraj_kopiju(SCRIPT_DIR, grana), gotovo)

    # -- azuriranje (samo na klik) ----------------------------------------------
    def _azuriraj(self):
        if not self.razvoj:
            # STABILNO: share se mijenja deployem, ovdje samo ponovno ucitaj
            self.ima_azuriranja = False
            self._ucitaj_korijen()
            self._provjeri_pakete()
            self.status_var.set("Učitana je trenutno objavljena verzija.")
            return
        if self.test_grana:
            self._azuriraj_testnu()
        else:
            self._azuriraj_glavnu()

    def _azuriraj_glavnu(self):
        if not self._zauzmi("Ažuriram s GitHuba…"):
            return

        def posao():
            lg.fetch(SCRIPT_DIR)
            up = lg.upstream(SCRIPT_DIR)
            if not up:
                raise lg.GitGreska(
                    f"Grana {self.glavna} nije povezana s GitHubom (nema upstream)."
                )
            stari = lg.info_commita(SCRIPT_DIR)["puni_hash"]
            try:
                lg.azuriraj_ff(SCRIPT_DIR, up)
            except lg.GitGreska as e:
                izmjene = lg.lokalne_promjene(SCRIPT_DIR)
                if izmjene:
                    raise lg.GitGreska(
                        "Lokalno su izmijenjene datoteke koje bi ažuriranje "
                        "pregazilo, pa ništa nije promijenjeno:\n  "
                        + "\n  ".join(izmjene[:15])
                        + "\n\nAko ti te izmjene ne trebaju, vrati ih "
                          "(git checkout -- <datoteka>) pa ponovno klikni Ažuriraj."
                    ) from e
                raise
            novi = lg.info_commita(SCRIPT_DIR)["puni_hash"]
            return lg.promijenjene_datoteke(SCRIPT_DIR, stari, novi)

        self._u_pozadini(posao, self._nakon_azuriranja)

    def _azuriraj_testnu(self):
        grana = self.test_grana
        if not self._zauzmi(f"Ažuriram granu {grana}…"):
            return

        def posao():
            lg.fetch(SCRIPT_DIR)
            if grana not in {g["ime"] for g in lg.udaljene_grane(SCRIPT_DIR)}:
                raise lg.GitGreska(
                    f"Grana {grana} više ne postoji na GitHubu (vjerojatno je "
                    f"mergana). Odaberi „{self.glavna}” u izborniku Verzija."
                )
            put, stari = lg.osiguraj_kopiju(SCRIPT_DIR, grana)
            novi = lg.info_commita(put)["puni_hash"]
            return lg.promijenjene_datoteke(put, stari, novi) if stari else []

        self._u_pozadini(posao, self._nakon_azuriranja)

    def _nakon_azuriranja(self, promijenjene, greska):
        if greska:
            self._oslobodi("Ažuriranje nije uspjelo.")
            messagebox.showerror("Ažuriranje", str(greska))
            return
        self.ima_azuriranja = False
        self._ucitaj_korijen()
        if not promijenjene:
            self._oslobodi("Već imaš najnoviju verziju.")
            self._prikazi_trake()
            return
        self._oslobodi(f"Ažurirano — promijenjeno datoteka: {len(promijenjene)}.")
        if "requirements.txt" in promijenjene:
            self._provjeri_pakete()
        if not self.test_grana and LAUNCHER_DATOTEKE & set(promijenjene):
            if messagebox.askyesno(
                "EE Alati", "Ažuriran je i sam launcher.\n\nPonovno ga pokrenuti sada?"
            ):
                self._ponovno_pokreni()

    def _ponovno_pokreni(self):
        flags = 0
        if os.name == "nt":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(
            [sys.executable, os.path.join(SCRIPT_DIR, "launcher.py")],
            cwd=SCRIPT_DIR, creationflags=flags, close_fds=True,
        )
        self.root.destroy()

    def _provjeri_pakete(self):
        """Ako se requirements.txt promijenio, doinstaliraj pakete u venv."""
        req = os.path.join(self.korijen, "requirements.txt")
        if not lg.treba_instalirati(req):
            return
        if not lg.u_venvu():
            self.status_var.set(
                "requirements.txt je promijenjen — pokreni Instaliraj EE Alati.bat"
            )
            return
        python = nadji_interpreter(konzola=True)
        self.status_var.set("Instaliram nove Python pakete (može potrajati)…")

        def gotovo(r, greska):
            ok, poruka = r if r else (False, str(greska))
            if ok:
                self.status_var.set("Python paketi su ažurirani.")
            else:
                self.status_var.set("Instalacija paketa nije uspjela.")
                messagebox.showerror("Instalacija paketa", poruka or "Nepoznata greška")

        self._u_pozadini(lambda: lg.instaliraj_pakete(python, req), gotovo)

    # -- objava kolegama -----------------------------------------------------------
    def _objavi_kolegama(self):
        deploy = os.path.join(SCRIPT_DIR, "deploy.ps1")
        if os.name != "nt":
            messagebox.showinfo("Objavi kolegama", "Objava radi samo na Windowsima.")
            return
        glavna = self.glavna or "master"
        if not messagebox.askyesno(
            "Objavi kolegama",
            f"Kolegama će se objaviti verzija s GitHuba: origin/{glavna}.\n\n"
            "(Testne grane i lokalne izmjene se NE objavljuju — samo ono što je "
            "mergano u glavnu granu.)\n\nNastaviti?",
        ):
            return
        subprocess.Popen(
            ["powershell", "-NoExit", "-ExecutionPolicy", "Bypass",
             "-File", deploy, "-Grana", glavna],
            cwd=SCRIPT_DIR, creationflags=subprocess.CREATE_NEW_CONSOLE,
        )

    # -- tooltip -----------------------------------------------------------
    def _na_pomak(self, event):
        iid = self.tree.identify_row(event.y)
        if iid == self._hover_iid:
            return
        self._ugasi_tooltip()
        self._hover_iid = iid
        alat = self._alat_za_iid(iid)
        if alat is not None:
            self._hover_job = self.root.after(
                TOOLTIP_DELAY_MS,
                lambda: self.tooltip.prikazi(
                    alat, event.x_root, event.y_root, self._verzija_red(alat)
                ),
            )

    def _verzija_red(self, alat):
        dijelovi = []
        if alat.get("verzija"):
            dijelovi.append(f"Verzija {alat['verzija']}")
        p = self._promjena_alata(alat)
        if p:
            dijelovi.append(f"zadnja promjena {p['datum']} — {p['poruka']}")
        return " · ".join(dijelovi)

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
        if not alat_postoji(alat, self.korijen):
            messagebox.showwarning(
                "Alat nije pronađen",
                f"Skripta ne postoji:\n{putanja_skripte(alat, self.korijen)}",
            )
            return
        try:
            pokreni_alat(alat, self.korijen, self._verzija_alata(alat))
            gdje = f" (grana {self.test_grana})" if self.test_grana else ""
            self.status_var.set(f"Pokrenuto: {alat['ime']}{gdje}")
        except Exception as e:
            messagebox.showerror("Greška pri pokretanju", f"{alat['ime']}\n\n{e}")


def main():
    root = tk.Tk()
    try:
        root.iconbitmap(os.path.join(SCRIPT_DIR, "ee_alati.ico"))
    except tk.TclError:
        pass  # .ico radi samo na Windowsima
    LauncherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
