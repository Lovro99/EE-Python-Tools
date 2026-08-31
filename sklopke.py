"""
Klasifikacija blokova: svjetiljke, sklopke rasvjete, ostala trošila
====================================================================
Faza 1 plana `PLAN_KabelSklopke.md`.

Imena blokova rasvjete i sklopki žive u vanjskoj DWG biblioteci koja nije
dio ovih repozitorija — u kodu ih nema i ne smiju se hardkodirati. Zato se
mapiranje `ime bloka → uloga / tip sklopke` **uči iz crteža**: pri
učitavanju CSV-a se izliste sva neprepoznata imena, korisnik im jednom
dodijeli ulogu, i mapiranje se spremi u JSON.

Ugrađeni uzorci su samo početno nagađanje po uobičajenim hrvatskim
nazivima — nisu autoritet i korisnik ih uvijek nadglasava.

Redoslijed prioriteta pri klasifikaciji:
  1. naučena mapa (točno ime bloka)      – korisnik je izričito rekao
  2. korisnički uzorci iz konfiguracije
  3. natuknica iz CSV-a (stupac Uloga)   – uzorak zadan u AutoCAD-u
  4. ugrađeni zadani uzorci
  5. NEPOZNATO                            – traži se od korisnika
"""

import json
import os
import unicodedata
from fnmatch import fnmatchcase

# ── Uloge ─────────────────────────────────────────────────────
ULOGA_SVJETILJKA = "SVJETILJKA"   # rasvjetno tijelo – meta sklopke
ULOGA_TROSILO    = "TROSILO"      # ostalo trošilo (utičnica…) – nije meta
ULOGA_SKLOPKA    = "SKLOPKA"      # zidna sklopka rasvjete
ULOGA_NEPOZNATO  = "NEPOZNATO"

ULOGE = (ULOGA_SVJETILJKA, ULOGA_TROSILO, ULOGA_SKLOPKA)

# ── Tipovi sklopki ────────────────────────────────────────────
TIP_ISKLJUCNA  = "ISKLJUCNA"
TIP_SERIJSKA   = "SERIJSKA"
TIP_IZMJENICNA = "IZMJENICNA"
TIP_KRIZNA     = "KRIZNA"

TIPOVI_SKLOPKI = (TIP_ISKLJUCNA, TIP_SERIJSKA, TIP_IZMJENICNA, TIP_KRIZNA)

# Kad je blok prepoznat kao sklopka ali tip nije poznat.
TIP_ZADANI = TIP_ISKLJUCNA

# ── Tablica žila (odluka iz plana: klasično 3/4/4 × 1,5) ──────
#   dovod  – kabel od trase do sklopke
#   veza   – kabel između sklopki (izmjenična ↔ križna ↔ izmjenična)
#   povrat – kabel od zadnje sklopke do svjetiljke
ZILE = {
    TIP_ISKLJUCNA:  {"dovod": "3x1,5", "veza": None,    "povrat": None},
    TIP_SERIJSKA:   {"dovod": "4x1,5", "veza": None,    "povrat": None},
    TIP_IZMJENICNA: {"dovod": "3x1,5", "veza": "4x1,5", "povrat": "3x1,5"},
    TIP_KRIZNA:     {"dovod": None,    "veza": "4x1,5", "povrat": None},
}

# ── Ugrađeni zadani uzorci (samo nagađanje, najspecifičniji prvi) ──
# PAŽNJA: u AutoLisp repozitoriju blok `PREKIDAC` je minijaturni zaštitni
# prekidač (MCB) u ormaru, a `FID-sklopka` je fidovka — NISU zidne sklopke.
# Ako takav blok ikad uđe u selekciju, uzorci ispod bi ga krivo proglasili
# sklopkom rasvjete; naučena mapa to nadglasava i odluka se pamti.
ZADANI_UZORCI = [
    ("*KRIZ*",     ULOGA_SKLOPKA,    TIP_KRIZNA),
    ("*IZMJEN*",   ULOGA_SKLOPKA,    TIP_IZMJENICNA),
    ("*SERIJ*",    ULOGA_SKLOPKA,    TIP_SERIJSKA),
    ("*ISKLJUC*",  ULOGA_SKLOPKA,    TIP_ISKLJUCNA),
    ("*TIPKAL*",   ULOGA_SKLOPKA,    TIP_ISKLJUCNA),
    ("*SKLOP*",    ULOGA_SKLOPKA,    None),
    ("*PREKID*",   ULOGA_SKLOPKA,    None),
    ("*SVJETIL*",  ULOGA_SVJETILJKA, None),
    ("*RASVJET*",  ULOGA_SVJETILJKA, None),
    ("*LAMP*",     ULOGA_SVJETILJKA, None),
    ("*REFLEKT*",  ULOGA_SVJETILJKA, None),
]

ZADANA_PUTANJA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "sklopke_config.json")


def normaliziraj(s):
    """VELIKA slova bez dijakritike — imena blokova u AutoCAD-u su
    najčešće bez č/ć/ž/š/đ, pa se `*KRIZ*` mora poklopiti i s KRIŽNA."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", str(s).strip())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.replace("Đ", "D").replace("đ", "d").upper()


class Klasifikacija:
    """Rezultat klasifikacije jednog imena bloka."""

    __slots__ = ("ime", "uloga", "tip", "izvor", "tip_pretpostavljen")

    def __init__(self, ime, uloga, tip=None, izvor="nepoznato",
                 tip_pretpostavljen=False):
        self.ime   = ime
        self.uloga = uloga
        self.tip   = tip
        self.izvor = izvor
        self.tip_pretpostavljen = tip_pretpostavljen

    @property
    def je_sklopka(self):
        return self.uloga == ULOGA_SKLOPKA

    @property
    def je_poznato(self):
        return self.uloga != ULOGA_NEPOZNATO

    def __repr__(self):
        return (f"Klasifikacija({self.ime!r}, {self.uloga}, {self.tip}, "
                f"izvor={self.izvor})")


class Klasifikator:
    """Naučena mapa imena blokova + uzorci, uz JSON perzistenciju."""

    def __init__(self, putanja=None):
        self.putanja = putanja or ZADANA_PUTANJA
        self.mapa    = {}   # normalizirano ime → {"uloga":…, "tip":…}
        self.uzorci  = []   # [(uzorak, uloga, tip)] – korisnički
        self.ucitaj()

    # ── perzistencija ────────────────────────────────────────
    def ucitaj(self):
        if not os.path.exists(self.putanja):
            return
        try:
            with open(self.putanja, encoding="utf-8") as f:
                cfg = json.load(f)
        except (OSError, ValueError):
            return          # oštećena konfiguracija ne smije srušiti alat
        self.mapa = {normaliziraj(k): v
                     for k, v in (cfg.get("blokovi") or {}).items()}
        self.uzorci = [(u.get("uzorak", ""), u.get("uloga"), u.get("tip"))
                       for u in (cfg.get("uzorci") or [])
                       if u.get("uzorak")]

    def snimi(self):
        cfg = {
            "_opis": ("Mapiranje imena AutoCAD blokova na ulogu i tip "
                      "sklopke. Uređuje ga Kabelski graf; može se i ručno."),
            "blokovi": self.mapa,
            "uzorci": [{"uzorak": u, "uloga": r, "tip": t}
                       for u, r, t in self.uzorci],
        }
        with open(self.putanja, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)

    # ── učenje ───────────────────────────────────────────────
    def zapamti(self, ime, uloga, tip=None):
        """Zapamti izričitu odluku korisnika za točno ime bloka."""
        if uloga not in ULOGE:
            raise ValueError(f"nepoznata uloga: {uloga!r}")
        if uloga != ULOGA_SKLOPKA:
            tip = None
        elif tip is not None and tip not in TIPOVI_SKLOPKI:
            raise ValueError(f"nepoznat tip sklopke: {tip!r}")
        self.mapa[normaliziraj(ime)] = {"uloga": uloga, "tip": tip}

    def zaboravi(self, ime):
        self.mapa.pop(normaliziraj(ime), None)

    # ── klasifikacija ────────────────────────────────────────
    def klasificiraj(self, ime, uloga_csv="", tip_csv="", ima_krug=False):
        """Klasificiraj jedno ime bloka.

        `uloga_csv` / `tip_csv` su natuknice iz CSV-a (stupci Uloga i
        Tip_Sklopke koje piše ExportCSVdata.lsp v3.3).

        `ima_krug` = blok nosi Circuit_Label. Takav blok je po definiciji
        trošilo — do v3.1 su samo takvi i dolazili u CSV. Zato ne završava
        kao NEPOZNATO i ne pita se za njega: stara se ponašanja time ne
        mijenjaju, a pita se samo za ono što je uistinu novo (sklopke).
        """
        n = normaliziraj(ime)

        # 1. naučena mapa – izričita odluka korisnika
        zapis = self.mapa.get(n)
        if zapis and zapis.get("uloga") in ULOGE:
            uloga = zapis["uloga"]
            tip   = zapis.get("tip")
            return self._dovrsi(ime, uloga, tip, "mapa")

        # 2. korisnički uzorci, pa 3. natuknica CSV-a, pa 4. zadani uzorci
        uloga = tip = None
        izvor = None

        for uzorak, u, t in self.uzorci:
            if fnmatchcase(n, normaliziraj(uzorak)):
                uloga, tip, izvor = u, t, "uzorak"
                break

        if uloga is None:
            u_csv = normaliziraj(uloga_csv)
            if u_csv in ULOGE:
                uloga, izvor = u_csv, "csv"
                t_csv = normaliziraj(tip_csv)
                if t_csv in TIPOVI_SKLOPKI:
                    tip = t_csv

        if uloga is None or tip is None:
            for uzorak, u, t in ZADANI_UZORCI:
                if fnmatchcase(n, uzorak):
                    if uloga is None:
                        uloga, izvor = u, "zadano"
                    # tip preuzmi samo ako se uzorak slaže oko uloge
                    if tip is None and u == uloga:
                        tip = t
                    break

        if uloga is None:
            if ima_krug:
                # Nosi oznaku kruga → trošilo, kao i do sada. Ne pitaj.
                return self._dovrsi(ime, ULOGA_TROSILO, None, "krug")
            return Klasifikacija(ime, ULOGA_NEPOZNATO, None, "nepoznato")

        return self._dovrsi(ime, uloga, tip, izvor or "zadano")

    def _dovrsi(self, ime, uloga, tip, izvor):
        """Sklopka bez poznatog tipa dobiva zadani tip, ali označen kao
        pretpostavljen — to mora biti vidljivo u izvještaju."""
        pretpostavljen = False
        if uloga == ULOGA_SKLOPKA and tip not in TIPOVI_SKLOPKI:
            tip, pretpostavljen = TIP_ZADANI, True
        elif uloga != ULOGA_SKLOPKA:
            tip = None
        return Klasifikacija(ime, uloga, tip, izvor, pretpostavljen)

    # ── skupna obrada ────────────────────────────────────────
    def klasificiraj_sve(self, zapisi):
        """`zapisi` = iterable (ime, uloga_csv, tip_csv[, ima_krug]).

        Isti blok se u CSV-u pojavljuje više puta, pa se natuknice prvo
        skupe po imenu, a svako se ime klasificira jednom.
        Vraća dict: normalizirano ime → Klasifikacija.
        """
        skup = {}
        for z in zapisi:
            ime, u_csv, t_csv = z[0], z[1], z[2]
            n = normaliziraj(ime)
            if not n:
                continue
            a = skup.setdefault(n, {"ime": ime, "u": "", "t": "",
                                    "krug": False})
            a["u"]    = a["u"] or u_csv
            a["t"]    = a["t"] or t_csv
            a["krug"] = a["krug"] or (bool(z[3]) if len(z) > 3 else False)
        return {n: self.klasificiraj(a["ime"], a["u"], a["t"], a["krug"])
                for n, a in skup.items()}

    @staticmethod
    def nepoznati(klasifikacije):
        """Imena koja traže odluku korisnika, abecedno."""
        return sorted(k.ime for k in klasifikacije.values()
                      if not k.je_poznato)


def _celija(serija, i):
    """Vrijednost kao string; prazan za None i za NaN (pandas prazna
    ćelija pri dtype=str), da 'nan' ne završi kao ime bloka."""
    if serija is None:
        return ""
    v = serija.iloc[i]
    if v is None or v != v:          # NaN != NaN
        return ""
    return str(v).strip()


def iz_dataframea(df):
    """Izvuci (Block_Name, Uloga, Tip_Sklopke, ima_krug) iz CSV DataFramea.
    Tolerira stare CSV-e (v3.1) koji nemaju nove stupce."""
    if df is None or getattr(df, "empty", True):
        return []
    imena = df.get("Block_Name")
    if imena is None:
        return []
    uloge  = df.get("Uloga")
    tipovi = df.get("Tip_Sklopke")
    krugovi = df.get("Circuit_Label")
    return [(_celija(imena, i), _celija(uloge, i), _celija(tipovi, i),
             bool(_celija(krugovi, i)))
            for i in range(len(df))]


def sazetak(klasifikacije):
    """Kratki izvještaj po ulogama za info panel."""
    broj = {}
    for k in klasifikacije.values():
        broj[k.uloga] = broj.get(k.uloga, 0) + 1
    return broj
