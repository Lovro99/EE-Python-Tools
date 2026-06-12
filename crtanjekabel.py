"""
Kabelski Graf  –  AutoCAD CSV → topološki graf  v3.4
=====================================================
Modovi rada:
  EE – Serijski : MST koji spaja RK i sve blokove jednog strujnog kruga
  EK – Zvijezda : Najkraći put od RK do svakog bloka zasebno

Novo u v3.4 (točnost):
  - Težine bridova = STVARNE duljine segmenata iz CSV-a (Segment_Lengths,
    LISP v3.1) – lukovi/bulge uračunati; fallback: 3D euklid iz vrhova.
  - Snap više ne mijenja duljine (težina je originalna geometrija, ne
    udaljenost snapanih centara); centri klastera se usrednjavaju;
    unutarnji vrhovi snapaju se malom tolerancijom (tol/10), puni snap
    samo na krajevima polilinija.
  - EE mod: duljina = suma JEDINSTVENIH bridova trase (bez dvostrukog
    brojanja zajedničkih dionica MST putanja).
  - EE mod: PRIJEDLOG RAZDJELNIH KUTIJA — točke gdje se stablo kruga
    grana izvan RK i trošila (tu je potreban spoj da bi izračun
    vrijedio); prikaz na grafu (romb) + broj po krugu i ukupno.
  - Blokovi se spajaju projekcijom na najbliži SEGMENT trase (virtualni
    čvor), ne samo na najbliži vrh.
  - Z koordinata se čita i ulazi u fallback duljinu.
  - EE vertikale: (2·n_blokova − 1) × v_uređaj (ulaz + izlaz po trošilu).
  - Rezerva po spoju (fiksni dodatak po terminaciji) uz postotni buffer.
  - Izbor jedinica DWG-a (mm/cm/m) – rezultati u metrima.
  - T-spoj tolerancija vezana uz snap toleranciju (max(2, tol/10)).

Novo u v3.3:
  - Vertikalni model: procjena vertikalnih kabelskih hodova (po podu ili
    spuštenim stropom). Parametri: visina etaže, visina RK, visina uređaja.

Ovisnosti:
  pip install customtkinter networkx pandas matplotlib
"""

import os
import re
import math
import csv
from collections import defaultdict

import pandas as pd
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import networkx as nx
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog, messagebox

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

MODE_EE      = "EE"
MODE_EK      = "EK"
DEFAULT_TOL  = 100.0
DEFAULT_RK   = "RK-1"

# ── Defaultne visine vertikalnog modela (u DWG jedinicama) ────
DEFAULT_V_ETAZA  = "280"
DEFAULT_V_RK_H   = "150"
DEFAULT_V_UREDAJ = "30"

# ── Palete boja ──────────────────────────────────────────────
C_BG_POLY  = "#1E3040"   # pozadinska mapa polilinija
C_EE       = "#1E88E5"   # EE brid
C_EK       = "#43A047"   # EK brid
C_HL_OUTER = "#FF6F00"   # highlight vanjski
C_HL_INNER = "#FFD600"   # highlight unutarnji
C_KRAJ     = "#66BB6A"   # čvor deg=1
C_TRAN     = "#FFA726"   # čvor deg=2
C_CVOR     = "#EF5350"   # čvorište deg≥3
C_BLOK     = "#E53935"   # trošilo (kvadrat)
C_RK       = "#FFD600"   # razvodna kutija (zvijezdica)
C_VEZA     = "#9C27B0"   # isprekidana veza blok→čvor
C_STACK    = "#FFFFFF"   # stacking broj
C_KUTIJA   = "#FFB300"   # predložena razdjelna kutija (romb)


# ══════════════════════════════════════════════════════════════
#  CSV UČITAVANJE
# ══════════════════════════════════════════════════════════════

def _parse_pts(raw):
    """'(x y z) (x y z) ...'  →  lista (x, y, z) tuplova (z=0 ako fali)."""
    pts = []
    for p in re.findall(r'\((.*?)\)', str(raw)):
        c = p.strip().split()
        if len(c) >= 2:
            try:
                z = float(c[2]) if len(c) >= 3 else 0.0
                pts.append((float(c[0]), float(c[1]), z))
            except ValueError:
                pass
    return pts


def _parse_lens(raw):
    """'l1 l2 l3 ...' → lista floatova ili None ako nevaljano/prazno."""
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return None
    vals = []
    for tok in str(raw).split():
        try:
            vals.append(float(tok))
        except ValueError:
            return None
    return vals or None


def ucitaj_kabele(path):
    """Vraca (kabeli, handle_map)."""
    if not os.path.exists(path):
        return [], []
    df = pd.read_csv(path, sep=";", dtype=str)
    kabeli, hmap = [], []
    for _, row in df.iterrows():
        pts = _parse_pts(row.get("Vertex_Coords(X,Y,Z)", ""))
        if len(pts) >= 2:
            # Stvarne duljine segmenata iz LISP-a v3.1 (lukovi uračunati);
            # None ako kolone nema ili se ne poklapa s brojem vrhova.
            lens = _parse_lens(row.get("Segment_Lengths", None))
            if lens is not None and len(lens) != len(pts) - 1:
                lens = None
            kabeli.append(pts)
            hmap.append({
                "kabel_id": row.get("Kabel_ID", ""),
                "handle":   row.get("Handle",   ""),
                "layer":    row.get("Layer",     ""),
                "width":    row.get("Width",     ""),
                "seg_lens": lens,
            })
    return kabeli, hmap


def ucitaj_blokove(path):
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path, sep=";", dtype=str)
    for col in ("X", "Y", "Z"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df


# ══════════════════════════════════════════════════════════════
#  GRADNJA GRAFA
# ══════════════════════════════════════════════════════════════

def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _dist3(a, b):
    za = a[2] if len(a) > 2 else 0.0
    zb = b[2] if len(b) > 2 else 0.0
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (za - zb) ** 2)


def _pt_to_segment_dist(p, a, b):
    """Udaljenost točke p od segmenta ab + parametar t ∈ [0,1]."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    seg2 = dx * dx + dy * dy
    if seg2 < 1e-12:
        return _dist(p, a), 0.0
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / seg2
    t = max(0.0, min(1.0, t))
    return _dist(p, (a[0] + t * dx, a[1] + t * dy)), t


def _tol_seg(tol):
    """T-spoj / unutarnja tolerancija vezana uz snap toleranciju."""
    return max(2.0, tol * 0.1)


def _razriješi_t_spojeve(kabeli, lens, tol_seg=2.0):
    """
    T-spoj fix: za svaki vrh kabela A koji leži NA segmentu kabela B
    (udaljenost ≤ tol_seg, ali nije blizu ni jednom vrhu segmenta),
    umetni taj vrh kao novu točku u kabel B. Duljina segmenta dijeli
    se proporcionalno parametru t (točno za ravne segmente).

    Rezultat: snap algoritam automatski poveže obje polilinije
    bez potrebe za velikim snap tolerancijama.
    """
    kabeli = [list(k) for k in kabeli]
    lens   = [list(l) for l in lens]
    for j in range(len(kabeli)):
        nova, nlen = [kabeli[j][0]], []
        for si in range(len(kabeli[j]) - 1):
            a, b = kabeli[j][si], kabeli[j][si + 1]
            L = lens[j][si]
            ubaci = []
            for i, ki in enumerate(kabeli):
                if i == j:
                    continue
                for pt in ki:
                    # Preskoči ako je već blizu vrha segmenta
                    if _dist(pt, a) <= tol_seg or _dist(pt, b) <= tol_seg:
                        continue
                    d, t = _pt_to_segment_dist(pt, a, b)
                    if d <= tol_seg and 0.001 < t < 0.999:
                        ubaci.append((t, pt))
            ubaci.sort(key=lambda x: x[0])
            # Deduplikacija: ne ubacuj dvije točke koje su si blizu
            dedup = []
            for t_val, pt in ubaci:
                if not any(_dist(pt, s[1]) <= tol_seg for s in dedup):
                    dedup.append((t_val, pt))
            t_prev = 0.0
            for t_val, pt in dedup:
                nova.append(pt)
                nlen.append((t_val - t_prev) * L)
                t_prev = t_val
            nova.append(b)
            nlen.append((1.0 - t_prev) * L)
        kabeli[j], lens[j] = nova, nlen
    return kabeli, lens


class _Snap:
    """Spaja vrhove polilinija unutar tolerancije u isti čvor.
    Centar klastera = prosjek spojenih točaka; bira se NAJBLIŽI
    centar (ne prvi), pa redoslijed kabela ne mijenja rezultat.

    Dvije razine: KRAJEVI polilinija spajaju se punom tolerancijom
    (tamo se kabeli fizički nastavljaju), a UNUTARNJI vrhovi punom
    tolerancijom samo na klastere krajeva — međusobno tek malom
    tolerancijom, da se paralelne trase ne sliju u istu."""

    def __init__(self, tol):
        self.tol = tol
        self.pts = []
        self._n  = []
        self.end = []

    def _nadji(self, pt, tol, samo_end=False):
        best_i, best_d = -1, tol
        for i, c in enumerate(self.pts):
            if samo_end and not self.end[i]:
                continue
            d = _dist(pt, c)
            if d <= best_d:
                best_d, best_i = d, i
        return best_i

    def _spoji(self, i, pt):
        n = self._n[i]
        c = self.pts[i]
        self.pts[i] = ((c[0] * n + pt[0]) / (n + 1),
                       (c[1] * n + pt[1]) / (n + 1))
        self._n[i] += 1
        return i

    def _novi(self, pt, end):
        self.pts.append((pt[0], pt[1]))
        self._n.append(1)
        self.end.append(end)
        return len(self.pts) - 1

    def dodaj_kraj(self, pt):
        i = self._nadji(pt, self.tol)
        if i >= 0:
            self.end[i] = True
            return self._spoji(i, pt)
        return self._novi(pt, True)

    def dodaj_unutarnji(self, pt, tol_seg):
        i = self._nadji(pt, self.tol, samo_end=True)
        if i < 0:
            i = self._nadji(pt, tol_seg)
        if i >= 0:
            return self._spoji(i, pt)
        return self._novi(pt, False)


def izgradi_graf(kabeli, hmap, tol):
    # Duljine segmenata: stvarne iz CSV-a (LISP v3.1) ili 3D euklid fallback
    lens = []
    for pi, poli in enumerate(kabeli):
        sl = hmap[pi].get("seg_lens") if pi < len(hmap) else None
        if not sl or len(sl) != len(poli) - 1:
            sl = [_dist3(poli[k], poli[k + 1]) for k in range(len(poli) - 1)]
        lens.append(list(sl))

    # Riješi T-spojeve prije snap-a (vrh jednog kabela na segmentu drugog)
    ts = _tol_seg(tol)
    kabeli, lens = _razriješi_t_spojeve(kabeli, lens, tol_seg=ts)

    # Dvorazinski snap: krajevi polilinija punom tolerancijom,
    # unutarnji vrhovi punom samo na klastere krajeva (vidi _Snap).
    snap = _Snap(tol)
    end_ids = {}
    for pi, poli in enumerate(kabeli):
        end_ids[(pi, 0)] = snap.dodaj_kraj(poli[0])
        end_ids[(pi, len(poli) - 1)] = snap.dodaj_kraj(poli[-1])

    G = nx.Graph()
    for pi, poli in enumerate(kabeli):
        ids = [end_ids[(pi, vi)] if (pi, vi) in end_ids
               else snap.dodaj_unutarnji(p, ts)
               for vi, p in enumerate(poli)]
        hi  = hmap[pi] if pi < len(hmap) else {}
        for k in range(len(ids) - 1):
            u, v = ids[k], ids[k + 1]
            if u == v:
                continue
            # Težina = originalna duljina geometrije, NE udaljenost
            # snapanih centara — snap ne smije mijenjati duljinu.
            d  = lens[pi][k]
            ed = dict(weight=d,
                      handle=hi.get("handle", ""),
                      layer=hi.get("layer",   ""))
            if G.has_edge(u, v):
                par = G[u][v].get("parallel", 1) + 1
                if d < G[u][v]["weight"]:
                    G[u][v].update(**ed)
                G[u][v]["parallel"] = par
            else:
                G.add_edge(u, v, parallel=1, **ed)
    for i, (x, y) in enumerate(snap.pts):
        if G.has_node(i):
            G.nodes[i]["x"] = x
            G.nodes[i]["y"] = y
    return G, snap.pts


def _najblizi(cvorovi, xy):
    if not cvorovi:
        raise ValueError("Lista čvorova je prazna — graf nije ispravno izgrađen.")
    best_i, best_d = 0, float("inf")
    for i, c in enumerate(cvorovi):
        d = _dist(xy, c)
        if d < best_d:
            best_d, best_i = d, i
    return best_i, best_d


def _umetni_virtualni(G, cvorovi, u, v, t):
    """Umetni virtualni čvor na bridu (u,v) na parametru t; duljina
    brida dijeli se proporcionalno. Vraća indeks novog čvora."""
    a, b = cvorovi[u], cvorovi[v]
    w  = len(cvorovi)
    px = a[0] + t * (b[0] - a[0])
    py = a[1] + t * (b[1] - a[1])
    cvorovi.append((px, py))
    data = dict(G[u][v])
    L = data.pop("weight")
    G.remove_edge(u, v)
    G.add_edge(u, w, weight=t * L, **data)
    G.add_edge(w, v, weight=(1.0 - t) * L, **data)
    G.nodes[w]["x"] = px
    G.nodes[w]["y"] = py
    return w


def povezi_blokove(G, cvorovi, blokovi):
    """Spoji svaki blok na najbližu TOČKU trase: ako je okomita
    projekcija na neki segment bliža od najbližeg vrha, umeće se
    virtualni čvor na projekciji (točniji priključak i kraći snap)."""
    veze = []
    if blokovi.empty:
        return veze
    for _, row in blokovi.iterrows():
        bx, by   = float(row["X"]), float(row["Y"])
        idx, d   = _najblizi(cvorovi, (bx, by))

        best = None  # (d, t, u, v)
        for u, v in G.edges():
            de, t = _pt_to_segment_dist((bx, by), cvorovi[u], cvorovi[v])
            if best is None or de < best[0]:
                best = (de, t, u, v)
        if best and best[0] < d - 1e-9 and 0.02 < best[1] < 0.98:
            idx = _umetni_virtualni(G, cvorovi, best[2], best[3], best[1])
            d   = best[0]

        veze.append({
            "label":      str(row.get("Circuit_Label", "")),
            "blok_xy":    (bx, by),
            "cvor_idx":   idx,
            "snap_d":     d,
            "handle":     str(row.get("Handle",     "")),
            "tip":        str(row.get("Tip_Kabela", "")),
            "block_name": str(row.get("Block_Name", "")),
        })
    return veze


# ══════════════════════════════════════════════════════════════
#  ANALIZA TOLERANCIJE  –  prijedlog
# ══════════════════════════════════════════════════════════════

def analiziraj_toleranciju(kabeli, tol_tren):
    """
    Pronalazi krajnje točke polilinija koje NISU spojene pri trenutnoj
    toleranciji i predlaže minimalnu toleranciju za spajanje.
    Također detektira T-spojeve (vrh na segmentu) koji se ne mogu
    riješiti povećanjem tolerancije.
    """
    krajevi = []
    for poli in kabeli:
        krajevi.append(poli[0])
        krajevi.append(poli[-1])

    razmaci = sorted(
        _dist(krajevi[i], krajevi[j])
        for i in range(len(krajevi))
        for j in range(i + 1, len(krajevi))
        if _dist(krajevi[i], krajevi[j]) > 0.001
    )
    if not razmaci:
        return None

    nepov = [d for d in razmaci if d > tol_tren]

    # T-spoj detekcija: vrh jednog kabela koji leži na segmentu drugog
    # ali nije blizu nijednom vrhu (ne može se riješiti snap tolerancijom)
    t_spoj_count = 0
    seen = set()
    for i, ki in enumerate(kabeli):
        for vi, pt in enumerate(ki):
            for j, kj in enumerate(kabeli):
                if i == j:
                    continue
                for si in range(len(kj) - 1):
                    a, b = kj[si], kj[si + 1]
                    # Preskoči ako je već blizu vrha → riješit će snap
                    if _dist(pt, a) <= tol_tren or _dist(pt, b) <= tol_tren:
                        continue
                    d, t = _pt_to_segment_dist(pt, a, b)
                    if d <= _tol_seg(tol_tren) and 0.001 < t < 0.999:
                        key = (min(i, j), max(i, j), vi, si)
                        if key not in seen:
                            seen.add(key)
                            t_spoj_count += 1

    return {
        "min_razmak":   round(razmaci[0], 2),
        "top10":        [round(d, 2) for d in razmaci[:10]],
        "nepov_min":    round(nepov[0], 2)    if nepov else None,
        "predlozena":   round(nepov[0] * 1.15, 1) if nepov else tol_tren,
        "sve_spojeno":  len(nepov) == 0,
        "t_spojevi":    t_spoj_count,
    }


# ══════════════════════════════════════════════════════════════
#  VALIDACIJA  –  detekcija otoka
# ══════════════════════════════════════════════════════════════

def provjeri_otoke(G, tol):
    n = nx.number_connected_components(G)
    if n <= 1:
        return []
    komponente = sorted(nx.connected_components(G), key=len, reverse=True)
    upoz = []
    for ki, komp in enumerate(komponente[1:], 1):
        handles = [d.get("handle", "")
                   for u, v, d in G.edges(data=True)
                   if u in komp and v in komp and d.get("handle", "")][:5]
        upoz.append(
            f"OTOK #{ki}: {len(komp)} čv. | tol={tol:.0f} | "
            f"Handle: {', '.join(handles) or '—'}"
        )
    return upoz


# ══════════════════════════════════════════════════════════════
#  VERTIKALNI MODEL
# ══════════════════════════════════════════════════════════════

RAZVOD_POD    = "pod"
RAZVOD_STROP  = "strop"

def izracunaj_v(tip, h_etaza, h_rk, h_uredaj):
    """
    Vraca (v_rk, v_uredaj) – vertikalni dodatak za izlaz iz RK i ulaz
    u svaki uređaj, ovisno o tipu razvoda.

    Po podu (RAZVOD_POD):
      Kabel silazi s visine montaže do poda (0), vodi se pod podom,
      zatim se diže do visine montaže uređaja.
        v_rk    = h_rk          (silazak od RK do poda)
        v_uredaj = h_uredaj     (uspon od poda do uređaja)

    Spušteni strop (RAZVOD_STROP):
      Kabel se penje od visine montaže do stropa, vodi se nad stropom,
      zatim silazi do visine montaže uređaja.
        v_rk    = h_etaza - h_rk       (uspon od RK do stropa)
        v_uredaj = h_etaza - h_uredaj  (silazak od stropa do uređaja)
    """
    if tip == RAZVOD_POD:
        return max(0.0, float(h_rk)), max(0.0, float(h_uredaj))
    else:
        return max(0.0, float(h_etaza) - float(h_rk)), \
               max(0.0, float(h_etaza) - float(h_uredaj))


# ══════════════════════════════════════════════════════════════
#  EE  –  SERIJSKA INSTALACIJA  (MST po strujnom krugu)
# ══════════════════════════════════════════════════════════════

def analiziraj_ee(G, cvorovi, veze, rk_label, v_rk=0.0, v_uredaj=0.0,
                  rezerva=0.0):
    """
    Za svaki Circuit_Label gradi metric-closure auxiliary graf
    ({RK čvor} ∪ {čvorovi svih blokova tog kruga}), iz njega
    izvlači MST (Steiner aproksimacija). Duljina trase = suma
    JEDINSTVENIH bridova svih putanja — zajedničke dionice se ne
    broje dvaput.

    Prijedlog razdjelnih kutija: zajednička dionica se smije brojati
    jednom samo ako na točki razdvajanja postoji mjesto za spoj.
    Zato se za svaki krug vraćaju čvorovi u kojima se stablo grana
    (stupanj ≥ 3) izvan RK i trošila — tu treba razdjelna kutija
    da bi izračun vrijedio.

    Vraca (rezultati, edge_usage).
    """
    rk_v = next((v for v in veze if v["label"] == rk_label), None)
    if not rk_v:
        return [], {}

    izvor      = rk_v["cvor_idx"]
    izvor_snap = rk_v["snap_d"]

    grupe = defaultdict(list)
    for v in veze:
        if v["label"] != rk_label:
            grupe[v["label"]].append(v)

    edge_usage = {}
    rezultati  = []

    for label, blokovi_k in grupe.items():
        terminali = list({izvor} | {b["cvor_idx"] for b in blokovi_k})

        # Metric closure: kompletni aux-graf s težinama = shortest_path_length
        aux   = nx.Graph()
        aux.add_nodes_from(terminali)
        paths = {}

        for i, ti in enumerate(terminali):
            for tj in terminali[i + 1:]:
                try:
                    put = nx.shortest_path(G, ti, tj, weight="weight")
                    d   = sum(G[put[k]][put[k+1]]["weight"]
                              for k in range(len(put) - 1))
                    aux.add_edge(ti, tj, weight=d)
                    paths[(ti, tj)] = put
                    paths[(tj, ti)] = put[::-1]
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    pass

        if not nx.is_connected(aux):
            rezultati.append({
                "label":     label,   "tip":       "EE",
                "duljina":   None,    "greska":    "Nepovezani čvorovi",
                "putanje":   [],      "n_blokova": len(blokovi_k),
            })
            continue

        MST     = nx.minimum_spanning_tree(aux, weight="weight")
        snap_e  = izvor_snap + sum(b["snap_d"] for b in blokovi_k)
        n_bl    = len(blokovi_k)
        # Vertikale: izlaz iz RK + ulaz I izlaz po trošilu u lancu
        # (zadnje trošilo samo ulaz) → (2·n − 1) vertikala uređaja.
        vert    = v_rk + max(0, 2 * n_bl - 1) * v_uredaj
        # Fiksna rezerva po terminaciji: RK + svako trošilo
        rez     = rezerva * (n_bl + 1)

        # Duljina trase = unija jedinstvenih bridova svih MST putanja
        # (kabel zajedničkom dionicom fizički prolazi jednom).
        putanje = []
        used    = set()
        trasa   = 0.0
        for ti, tj in MST.edges():
            put = paths.get((ti, tj)) or paths.get((tj, ti))
            if put:
                putanje.append(put)
                for k in range(len(put) - 1):
                    e = (min(put[k], put[k+1]), max(put[k], put[k+1]))
                    edge_usage[e] = edge_usage.get(e, 0) + 1
                    if e not in used:
                        used.add(e)
                        trasa += G[put[k]][put[k+1]]["weight"]

        # Predložene razdjelne kutije: grananja stabla izvan RK/trošila
        T = nx.Graph()
        T.add_edges_from(used)
        term_nodes = {izvor} | {b["cvor_idx"] for b in blokovi_k}
        kutije = sorted(n for n in T.nodes()
                        if T.degree(n) >= 3 and n not in term_nodes)

        rezultati.append({
            "label":      label,
            "tip":        "EE",
            "duljina":    trasa + snap_e + vert + rez,
            "mst_len":    trasa,
            "snap_extra": snap_e,
            "vertikalno": vert,
            "rezerva":    rez,
            "v_rk":       v_rk,
            "v_uredaj":   v_uredaj,
            "greska":     None,
            "putanje":    putanje,
            "n_blokova":  n_bl,
            "kutije":     kutije,
        })

    rezultati.sort(key=lambda r: r["duljina"] or float("inf"))
    return rezultati, edge_usage


# ══════════════════════════════════════════════════════════════
#  EK  –  ZVIJEZDASTA INSTALACIJA  (shortest_path po bloku)
# ══════════════════════════════════════════════════════════════

def analiziraj_ek(G, cvorovi, veze, rk_label, v_rk=0.0, v_uredaj=0.0,
                  rezerva=0.0):
    """
    Za svaki blok: nx.shortest_path od RK do tog bloka.
    Svaki blok dobiva zaseban kabel (zvijezdasta topologija).

    Vraca (rezultati, edge_usage).
    """
    rk_v = next((v for v in veze if v["label"] == rk_label), None)
    if not rk_v:
        return [], {}

    izvor      = rk_v["cvor_idx"]
    izvor_snap = rk_v["snap_d"]

    edge_usage = {}
    rezultati  = []

    for i, veza in enumerate(veze):
        if veza["label"] == rk_label:
            continue

        cilj       = veza["cvor_idx"]
        cilj_snap  = veza["snap_d"]
        oznaka     = (veza["label"] or veza.get("block_name", "") or f"Blok_{i+1}")

        try:
            put    = nx.shortest_path(G, izvor, cilj, weight="weight")
            plen   = sum(G[put[k]][put[k+1]]["weight"]
                         for k in range(len(put) - 1))
            # Vertikale: jedan izlaz iz RK + jedan ulaz u uređaj
            vert   = v_rk + v_uredaj
            # Fiksna rezerva: 2 terminacije po kabelu (RK + uređaj)
            rez    = rezerva * 2
            ukupno = izvor_snap + plen + cilj_snap + vert + rez

            for k in range(len(put) - 1):
                e = (min(put[k], put[k+1]), max(put[k], put[k+1]))
                edge_usage[e] = edge_usage.get(e, 0) + 1

            rezultati.append({
                "label":      oznaka,  "tip":        "EK",
                "duljina":    ukupno,  "path_len":   plen,
                "snap_rk":    izvor_snap, "snap_blok": cilj_snap,
                "vertikalno": vert,    "v_rk":       v_rk,
                "v_uredaj":   v_uredaj, "rezerva":   rez,
                "greska":     None,    "putanje":    [put],
                "blok_xy":    veza["blok_xy"],
            })

        except (nx.NetworkXNoPath, nx.NodeNotFound):
            rezultati.append({
                "label":   oznaka, "tip":     "EK",
                "duljina": None,   "greska":  "Nema puta u grafu",
                "putanje": [],     "blok_xy": veza["blok_xy"],
            })

    rezultati.sort(key=lambda r: r["duljina"] or float("inf"))
    return rezultati, edge_usage


# ══════════════════════════════════════════════════════════════
#  EXPORT  CSV
# ══════════════════════════════════════════════════════════════

def exportiraj_csv(rezultati, path, buffer_pct=0.0,
                   unit_factor=None, unit_name="jed."):
    """unit_factor: množitelj DWG jed. → metri (npr. mm=0.001);
    None = bez konverzije, vrijednosti ostaju u DWG jedinicama."""
    has_buf = buffer_pct > 0
    has_rez = any(r.get("rezerva", 0.0) > 0
                  for r in rezultati if not r.get("greska"))
    scale   = unit_factor if unit_factor else 1.0
    u       = "m" if unit_factor else unit_name

    header = ["Oznaka", "Tip_Instalacije",
              f"Horizontalno [{u}]", f"Vertikalno [{u}]"]
    if has_rez:
        header.append(f"Rezerva [{u}]")
    header.append(f"Duljina_Kabela [{u}]")
    if has_buf:
        header.append(f"S_bufferom_{buffer_pct:.1f}% [{u}]")

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(header)
        ukupno = 0.0
        for r in rezultati:
            d    = r.get("duljina")
            vert = r.get("vertikalno", 0.0) if not r.get("greska") else 0.0
            rez  = r.get("rezerva",    0.0) if not r.get("greska") else 0.0
            horiz = (d - vert - rez) if d is not None else None
            row = [
                r["label"],
                r["tip"],
                f"{horiz * scale:.2f}" if horiz is not None else "GREŠKA",
                f"{vert * scale:.2f}"  if d    is not None else "GREŠKA",
            ]
            if has_rez:
                row.append(f"{rez * scale:.2f}" if d is not None else "GREŠKA")
            row.append(f"{d * scale:.2f}" if d is not None else "GREŠKA")
            if has_buf:
                row.append(f"{d * scale * (1 + buffer_pct / 100):.2f}"
                           if d is not None else "GREŠKA")
            w.writerow(row)
            if d:
                ukupno += d

        uk_row = ["UKUPNO", "", "", ""]
        if has_rez:
            uk_row.append("")
        uk_row.append(f"{ukupno * scale:.2f}")
        if has_buf:
            uk_row.append(f"{ukupno * scale * (1 + buffer_pct / 100):.2f}")
        w.writerow(uk_row)


# ══════════════════════════════════════════════════════════════
#  ZOOM / PAN
# ══════════════════════════════════════════════════════════════

class ZoomPan:
    """Kotačić = zoom | Desni klik+drag = pan | R/Home = reset."""
    def __init__(self, ax, scale=1.25):
        self.ax    = ax
        self.scale = scale
        self._press = None
        self._orig  = None
        c = ax.figure.canvas
        c.mpl_connect("scroll_event",         self._scroll)
        c.mpl_connect("button_press_event",   self._press_ev)
        c.mpl_connect("button_release_event", self._release)
        c.mpl_connect("motion_notify_event",  self._motion)
        c.mpl_connect("key_press_event",      self._key)

    def save_home(self):
        self._orig = (self.ax.get_xlim(), self.ax.get_ylim())

    def _scroll(self, ev):
        if ev.inaxes != self.ax or ev.xdata is None:
            return
        f  = self.scale if ev.button == "up" else 1 / self.scale
        xl, yl = self.ax.get_xlim(), self.ax.get_ylim()
        self.ax.set_xlim(ev.xdata - (ev.xdata - xl[0]) * f,
                         ev.xdata + (xl[1] - ev.xdata) * f)
        self.ax.set_ylim(ev.ydata - (ev.ydata - yl[0]) * f,
                         ev.ydata + (yl[1] - ev.ydata) * f)
        self.ax.figure.canvas.draw_idle()

    def _press_ev(self, ev):
        if ev.inaxes == self.ax and ev.button == 3 and ev.xdata is not None:
            self._press = (ev.xdata, ev.ydata,
                           self.ax.get_xlim(), self.ax.get_ylim())

    def _release(self, ev):
        self._press = None

    def _motion(self, ev):
        if self._press is None or ev.inaxes != self.ax or ev.xdata is None:
            return
        x0, y0, xl, yl = self._press
        dx, dy = ev.xdata - x0, ev.ydata - y0
        self.ax.set_xlim(xl[0] - dx, xl[1] - dx)
        self.ax.set_ylim(yl[0] - dy, yl[1] - dy)
        self.ax.figure.canvas.draw_idle()

    def _key(self, ev):
        if ev.key in ("r", "R", "home") and self._orig:
            self.ax.set_xlim(self._orig[0])
            self.ax.set_ylim(self._orig[1])
            self.ax.figure.canvas.draw_idle()


# ══════════════════════════════════════════════════════════════
#  VIZUALIZACIJA
# ══════════════════════════════════════════════════════════════

def nacrtaj(ax, G, cvorovi, kabeli_raw, blokovi, veze,
            rezultati, edge_usage, izvor_idx, rk_label,
            mode, highlighted=None, buffer_pct=0.0, fmt=None):
    if fmt is None:
        fmt = lambda v: f"{v:,.1f} jed."
    ax.clear()
    ax.set_facecolor("#0C1A28")
    ax.set_aspect("equal")

    if not cvorovi:
        ax.text(0.5, 0.5, "Nema podataka",
                transform=ax.transAxes, ha="center", va="center",
                color="#444", fontsize=13)
        return

    # 1. Pozadinska mapa – sve polilinije iz CSV-a
    for poli in kabeli_raw:
        xs = [p[0] for p in poli]
        ys = [p[1] for p in poli]
        ax.plot(xs, ys, color=C_BG_POLY, lw=2.0, alpha=0.78,
                zorder=1, solid_capstyle="round")

    # 2. Skupi sve aktivne i highlight bridove
    sve_e = set()
    for r in rezultati:
        if not r.get("greska"):
            for put in r.get("putanje", []):
                for k in range(len(put) - 1):
                    sve_e.add((min(put[k], put[k+1]), max(put[k], put[k+1])))

    hl_e = set()
    if highlighted and not highlighted.get("greska"):
        for put in highlighted.get("putanje", []):
            for k in range(len(put) - 1):
                hl_e.add((min(put[k], put[k+1]), max(put[k], put[k+1])))

    # 3. Aktivni bridovi (debljina ~ broj kabela na trasi)
    boja = C_EE if mode == MODE_EE else C_EK
    for u, v in G.edges():
        e = (min(u, v), max(u, v))
        if e not in sve_e or e in hl_e:
            continue
        x1, y1 = cvorovi[u]
        x2, y2 = cvorovi[v]
        cnt = edge_usage.get(e, 0)
        lw  = 3.0 + min(cnt, 8) * 0.45
        ax.plot([x1, x2], [y1, y2], color=boja, lw=lw,
                alpha=0.95, zorder=3, solid_capstyle="round")

    # 4. Highlight putanje
    if hl_e:
        for u, v in G.edges():
            e = (min(u, v), max(u, v))
            if e not in hl_e:
                continue
            x1, y1 = cvorovi[u]
            x2, y2 = cvorovi[v]
            ax.plot([x1, x2], [y1, y2], color=C_HL_OUTER, lw=6.0,
                    alpha=0.45, zorder=4)
            ax.plot([x1, x2], [y1, y2], color=C_HL_INNER, lw=2.5,
                    alpha=1.00, zorder=5, solid_capstyle="round")

    # 5. Stacking brojevi (samo gdje > 1 kabel dijeli brid)
    for e, cnt in edge_usage.items():
        if cnt < 2:
            continue
        u, v = e
        if u >= len(cvorovi) or v >= len(cvorovi):
            continue
        mx = (cvorovi[u][0] + cvorovi[v][0]) / 2
        my = (cvorovi[u][1] + cvorovi[v][1]) / 2
        ax.text(mx, my, str(cnt),
                fontsize=9, fontweight="bold", color=C_STACK,
                ha="center", va="center", zorder=9,
                bbox=dict(boxstyle="round,pad=0.22",
                          fc="#0A2A50", ec="#42A5F5", linewidth=0.9,
                          alpha=0.93))

    # 6. Čvorovi grafa
    for i, (cx, cy) in enumerate(cvorovi):
        if i == izvor_idx:
            continue
        deg  = G.degree(i) if i in G else 0
        boja_c = C_KRAJ if deg == 1 else (C_CVOR if deg >= 3 else C_TRAN)
        ax.scatter(cx, cy, s=30, c=boja_c, zorder=6,
                   edgecolors="none", alpha=0.85)

    # 7. Isprekidane veze blok → čvor
    for veza in veze:
        bx, by = veza["blok_xy"]
        cx, cy = cvorovi[veza["cvor_idx"]]
        ax.plot([bx, cx], [by, cy], color=C_VEZA, lw=0.7,
                ls="--", alpha=0.45, zorder=5)

    # 7b. Predložene razdjelne kutije (EE): romb na grananjima stabla
    kutije_sve = set()
    for r in rezultati:
        if not r.get("greska"):
            kutije_sve.update(r.get("kutije") or [])
    kutije_hl = set()
    if highlighted and not highlighted.get("greska"):
        kutije_hl = set(highlighted.get("kutije") or [])
    for k in kutije_sve:
        if k >= len(cvorovi):
            continue
        kx, ky = cvorovi[k]
        hl = k in kutije_hl
        ax.scatter(kx, ky, marker="D",
                   s=170 if hl else 120,
                   c=C_HL_INNER if hl else C_KUTIJA,
                   edgecolors="#4E342E", linewidths=1.4,
                   zorder=8, alpha=0.95)
        ax.annotate("K", (kx, ky), ha="center", va="center",
                    fontsize=7, fontweight="bold", color="#3E2723",
                    zorder=9)

    # 8. RK čvor iz grafa – uvijek vidljiv (i bez blokovi CSV-a)
    if izvor_idx is not None and izvor_idx < len(cvorovi):
        rx, ry = cvorovi[izvor_idx]
        ax.scatter(rx, ry, c=C_RK, s=220, zorder=8,
                   edgecolors="#5D4037", linewidths=1.5, marker="*")
        ax.annotate(rk_label, (rx, ry),
                    xytext=(8, 8), textcoords="offset points",
                    fontsize=12, fontweight="bold",
                    color="#FFF9C4", zorder=9)

    # 9. Blokovi i razvodna kutija (preciznije pozicije iz CSV-a)
    if not blokovi.empty:
        mask   = blokovi["Circuit_Label"].astype(str) == rk_label
        df_sk  = blokovi[~mask]
        df_rk  = blokovi[mask]

        if not df_sk.empty:
            ax.scatter(df_sk["X"].astype(float),
                       df_sk["Y"].astype(float),
                       c=C_BLOK, s=90, zorder=7,
                       edgecolors="white", linewidths=1.1, marker="s")
            for _, row in df_sk.iterrows():
                ax.annotate(str(row["Circuit_Label"]),
                            (float(row["X"]), float(row["Y"])),
                            xytext=(5, 5), textcoords="offset points",
                            fontsize=11, fontweight="bold",
                            color="#FFCDD2", zorder=8)

        if not df_rk.empty:
            ax.scatter(df_rk["X"].astype(float),
                       df_rk["Y"].astype(float),
                       c=C_RK, s=220, zorder=8,
                       edgecolors="#5D4037", linewidths=1.5, marker="*")
            for _, row in df_rk.iterrows():
                ax.annotate(rk_label,
                            (float(row["X"]), float(row["Y"])),
                            xytext=(8, 8), textcoords="offset points",
                            fontsize=12, fontweight="bold",
                            color="#FFF9C4", zorder=9)

    # Naslov + osi
    n_komp   = nx.number_connected_components(G)
    uk_osnova = sum(r["duljina"] for r in rezultati if r.get("duljina"))
    uk_buffer = uk_osnova * (1.0 + buffer_pct / 100.0)
    mode_str  = ("EE – Serijski (MST/krug)"
                 if mode == MODE_EE else "EK – Zvijezda (shortest path)")

    if highlighted and not highlighted.get("greska"):
        kut_str = (f"   |   kutije: {len(kutije_hl)}"
                   if mode == MODE_EE else "")
        naslov = (f"{highlighted['label']}   →   "
                  f"{fmt(highlighted['duljina'])}{kut_str}")
        nc = C_HL_INNER
    else:
        buf_str = (f"  |  +{buffer_pct:.1f}% = {fmt(uk_buffer)}"
                   if buffer_pct > 0 else "")
        kut_str = (f"  |  Kutije: {len(kutije_sve)}"
                   if mode == MODE_EE else "")
        naslov = (f"Mode: {mode_str}  |  Osnova: {fmt(uk_osnova)}"
                  f"{buf_str}{kut_str}  |  Komp.: {n_komp}")
        nc = "#CFD8DC"

    ax.set_title(naslov, fontsize=12, fontweight="bold", color=nc, pad=9)
    ax.tick_params(colors="#D0D8E4", labelsize=11)
    for spine in ax.spines.values():
        spine.set_edgecolor("#2A4A6A")
    ax.set_xlabel("X [AutoCAD jed.]", color="#90A4AE", fontsize=11)
    ax.set_ylabel("Y [AutoCAD jed.]", color="#90A4AE", fontsize=11)
    ax.grid(True, ls="--", lw=0.35, alpha=0.22, color="#1E3A5F")


# ══════════════════════════════════════════════════════════════
#  APLIKACIJA  (CustomTkinter)
# ══════════════════════════════════════════════════════════════

class KabelskiApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("Kabelski Graf  –  MST Analizator  v3.4")
        self.geometry("1500x880")
        self.minsize(1100, 700)

        # Stanje analize
        self.G          = None
        self.cvorovi    = []
        self.blokovi    = pd.DataFrame()
        self.veze       = []
        self.rezultati  = []
        self.edge_usage = {}
        self.izvor_idx  = None
        self.kabeli     = []
        self.hmap       = []
        self._highlighted  = None
        self._zp           = None
        self._circuit_btns = []

        # Tkinter varijable
        self._kp      = ctk.StringVar()
        self._bp      = ctk.StringVar()
        self._tol     = ctk.DoubleVar(value=DEFAULT_TOL)
        self._rk      = ctk.StringVar(value=DEFAULT_RK)
        self._mode    = ctk.StringVar(value=MODE_EE)
        self._buffer  = ctk.DoubleVar(value=0.0)
        self._rezerva = ctk.StringVar(value="0")
        self._unit    = ctk.StringVar(value="jed.")

        # Vertikalni model
        self._v_tip    = ctk.StringVar(value=RAZVOD_POD)
        self._v_etaza  = ctk.StringVar(value=DEFAULT_V_ETAZA)
        self._v_rk_h   = ctk.StringVar(value=DEFAULT_V_RK_H)
        self._v_uredaj = ctk.StringVar(value=DEFAULT_V_UREDAJ)
        self._v_rk_calc  = 0.0
        self._v_ur_calc  = 0.0

        self._build_ui()
        # Fix 6: osvježi listu kad se promijeni buffer %
        self._buffer.trace_add("write", self._on_buffer_change)

    # ── GRADNJA UI ──────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        F_T   = ("Segoe UI", 15, "bold")
        F_SEC = ("Segoe UI", 10, "bold")
        F_LBL = ("Segoe UI", 12)
        F_SM  = ("Segoe UI", 10)
        C_SEC = "#10202F"   # pozadina sekcije
        C_HDR = "#6E8CA8"   # boja naslova sekcije

        # ── LIJEVI PANEL ────────────────────────────────────────
        # Raspored: naslov / postavke (scroll) / akcije / validacija.
        # Dno je fiksno pa je konzola uvijek vidljiva.
        lp = ctk.CTkFrame(self, width=300, corner_radius=0, fg_color="#0B1622")
        lp.grid(row=0, column=0, sticky="nsew")
        lp.grid_propagate(False)
        lp.grid_columnconfigure(0, weight=1)
        lp.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(lp, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text="KABELSKI GRAF", font=F_T).grid(
            row=0, column=0, sticky="w")
        ctk.CTkLabel(head, text="v3.4", font=F_SM,
                     text_color=C_HDR).grid(row=0, column=1, sticky="e")

        sf = ctk.CTkScrollableFrame(lp, fg_color="transparent")
        sf.grid(row=1, column=0, sticky="nsew", padx=2)
        sf.grid_columnconfigure(0, weight=1)

        self._sec_row = 0

        def sekcija(title):
            f = ctk.CTkFrame(sf, fg_color=C_SEC, corner_radius=8)
            f.grid(row=self._sec_row, column=0, sticky="ew",
                   padx=4, pady=(0, 6))
            f.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(f, text=title, font=F_SEC,
                         text_color=C_HDR).grid(
                row=0, column=0, columnspan=3, padx=10, pady=(6, 2),
                sticky="w")
            self._sec_row += 1
            return f

        def red(s, row, label, widget):
            ctk.CTkLabel(s, text=label, font=F_LBL).grid(
                row=row, column=0, padx=(10, 4), pady=1, sticky="w")
            widget.grid(row=row, column=2, padx=(4, 10), pady=1, sticky="e")

        # ── MOD RADA ──────────────────────────────────────────
        s = sekcija("MOD RADA")
        ctk.CTkRadioButton(s, text="EE – Serijski", variable=self._mode,
                           value=MODE_EE, font=F_LBL,
                           radiobutton_width=16, radiobutton_height=16).grid(
            row=1, column=0, padx=(10, 4), pady=(0, 8), sticky="w")
        ctk.CTkRadioButton(s, text="EK – Zvijezda", variable=self._mode,
                           value=MODE_EK, font=F_LBL,
                           radiobutton_width=16, radiobutton_height=16).grid(
            row=1, column=1, columnspan=2, padx=4, pady=(0, 8), sticky="w")

        # ── ULAZNI PODACI ─────────────────────────────────────
        s = sekcija("ULAZNI PODACI")
        self._btn_k = ctk.CTkButton(
            s, text="Kabeli_Export.csv …", height=28, font=F_SM,
            anchor="w", fg_color="#16324A", hover_color="#1E4264",
            command=self._odaberi_k)
        self._btn_k.grid(row=1, column=0, columnspan=3,
                         padx=10, pady=(0, 4), sticky="ew")
        self._btn_b = ctk.CTkButton(
            s, text="Circuit_Data_Export.csv …", height=28, font=F_SM,
            anchor="w", fg_color="#16324A", hover_color="#1E4264",
            command=self._odaberi_b)
        self._btn_b.grid(row=2, column=0, columnspan=3,
                         padx=10, pady=(0, 8), sticky="ew")

        # ── GRAF ──────────────────────────────────────────────
        s = sekcija("GRAF")
        ctk.CTkLabel(s, text="Tolerancija:", font=F_LBL).grid(
            row=1, column=0, padx=(10, 4), sticky="w")
        self._lbl_tol_v = ctk.CTkLabel(s, text=f"{DEFAULT_TOL:.0f} jed.",
                                        font=("Segoe UI", 12, "bold"),
                                        text_color="#64B5F6")
        self._lbl_tol_v.grid(row=1, column=2, padx=(0, 10), sticky="e")
        ctk.CTkSlider(s, from_=1, to=1000, variable=self._tol,
                      command=self._on_tol, height=14).grid(
            row=2, column=0, columnspan=3, padx=10, pady=2, sticky="ew")
        ctk.CTkButton(s, text="Predloži toleranciju", height=24, font=F_SM,
                      fg_color="transparent", border_width=1,
                      border_color="#2A4A6A", text_color="#90CAF9",
                      command=self._predlozi_tol).grid(
            row=3, column=0, columnspan=3, padx=10, pady=(0, 6), sticky="ew")
        ctk.CTkLabel(s, text="RK (Circuit_Label):", font=F_LBL).grid(
            row=4, column=0, padx=(10, 4), pady=(0, 8), sticky="w")
        ctk.CTkEntry(s, textvariable=self._rk, height=26, font=F_LBL).grid(
            row=4, column=1, columnspan=2, padx=(4, 10), pady=(0, 8),
            sticky="ew")

        # ── DODACI I JEDINICE ─────────────────────────────────
        s = sekcija("DODACI I JEDINICE")
        red(s, 1, "Dodatak na duljinu (%):",
            ctk.CTkEntry(s, textvariable=self._buffer, width=70,
                         height=26, font=F_LBL, justify="right"))
        red(s, 2, "Rezerva po spoju:",
            ctk.CTkEntry(s, textvariable=self._rezerva, width=70,
                         height=26, font=F_LBL, justify="right"))
        red(s, 3, "Jedinica DWG-a:",
            ctk.CTkOptionMenu(s, variable=self._unit,
                              values=["jed.", "mm", "cm", "m"],
                              width=70, height=26, font=F_SM,
                              command=lambda *_: self._on_unit_change()))
        ctk.CTkLabel(s, text="Rezerva: EE = n+1, EK = 2 terminacije",
                     font=F_SM, text_color="#546E7A").grid(
            row=4, column=0, columnspan=3, padx=10, pady=(2, 6), sticky="w")

        # ── VERTIKALNI RAZVOD ─────────────────────────────────
        s = sekcija("VERTIKALNI RAZVOD")
        vr = ctk.CTkFrame(s, fg_color="transparent")
        vr.grid(row=1, column=0, columnspan=3, padx=6, sticky="ew")
        ctk.CTkRadioButton(vr, text="Po podu", variable=self._v_tip,
                           value=RAZVOD_POD, font=F_SM,
                           radiobutton_width=15, radiobutton_height=15).grid(
            row=0, column=0, padx=4, sticky="w")
        ctk.CTkRadioButton(vr, text="Spušteni strop", variable=self._v_tip,
                           value=RAZVOD_STROP, font=F_SM,
                           radiobutton_width=15, radiobutton_height=15).grid(
            row=0, column=1, padx=4, sticky="w")
        for i, (txt, var) in enumerate(
                (("Visina etaže:",   self._v_etaza),
                 ("Visina RK:",      self._v_rk_h),
                 ("Visina uređaja:", self._v_uredaj)), start=2):
            red(s, i, txt,
                ctk.CTkEntry(s, textvariable=var, width=70, height=26,
                             font=F_LBL, justify="right"))
        ctk.CTkLabel(s, text="U istim jedinicama kao DWG", font=F_SM,
                     text_color="#546E7A").grid(
            row=5, column=0, columnspan=3, padx=10, pady=(2, 6), sticky="w")

        # ── AKCIJE + VALIDACIJA (fiksno dno) ──────────────────
        ctk.CTkButton(lp, text="▶   ANALIZIRAJ",
                      font=("Segoe UI", 13, "bold"), height=36,
                      command=self._analiziraj).grid(
            row=2, column=0, padx=10, pady=(8, 4), sticky="ew")

        btn_row = ctk.CTkFrame(lp, fg_color="transparent")
        btn_row.grid(row=3, column=0, padx=10, sticky="ew")
        btn_row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(btn_row, text="Reset (R)", height=26, font=F_SM,
                      fg_color="transparent", border_width=1,
                      border_color="#2A4A6A",
                      command=self._reset_view).grid(
            row=0, column=0, padx=(0, 3), sticky="ew")
        ctk.CTkButton(btn_row, text="Export CSV", height=26, font=F_SM,
                      fg_color="#1B5E20", hover_color="#2E7D32",
                      command=self._exportiraj).grid(
            row=0, column=1, padx=(3, 0), sticky="ew")

        ctk.CTkLabel(lp, text="VALIDACIJA", font=F_SEC,
                     text_color=C_HDR).grid(
            row=4, column=0, padx=12, pady=(8, 0), sticky="w")
        self._txt_info = ctk.CTkTextbox(lp, height=108,
                                         font=("Consolas", 10), wrap="word",
                                         fg_color="#0E1C2A")
        self._txt_info.grid(row=5, column=0, padx=8, pady=(2, 2), sticky="ew")
        self._txt_info.insert("end", "—")
        self._txt_info.configure(state="disabled")

        self._lbl_status = ctk.CTkLabel(lp, text="Spreman.", font=F_SM,
                                         text_color="#78909C",
                                         wraplength=276, anchor="w",
                                         justify="left")
        self._lbl_status.grid(row=6, column=0, padx=12,
                               pady=(0, 8), sticky="w")

        # ── DESNI DIO: Graf + Lista ──────────────────────────────
        rp = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        rp.grid(row=0, column=1, sticky="nsew", padx=2)
        rp.grid_columnconfigure(0, weight=1)
        rp.grid_rowconfigure(0, weight=1)

        pw = tk.PanedWindow(rp, orient=tk.HORIZONTAL,
                             bg="#090910", sashwidth=5)
        pw.grid(row=0, column=0, sticky="nsew")

        self._gfr = ctk.CTkFrame(pw, fg_color="#0C1A28", corner_radius=0)
        pw.add(self._gfr, minsize=630, stretch="always")

        lf = ctk.CTkFrame(pw, width=340, corner_radius=0)
        pw.add(lf, minsize=275, width=340, stretch="never")
        lf.grid_rowconfigure(1, weight=1)
        lf.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(lf, text="STRUJNI KRUGOVI / BLOKOVI",
                     font=("Segoe UI", 12, "bold"),
                     text_color="#6E8CA8").grid(
            row=0, column=0, padx=12, pady=(10, 4), sticky="w")
        self._sfr = ctk.CTkScrollableFrame(lf)
        self._sfr.grid(row=1, column=0, sticky="nsew", padx=5, pady=(0, 4))

        # Ukupno osnova + buffer
        uk_frame = ctk.CTkFrame(lf, fg_color="#0A1A0A", corner_radius=6)
        uk_frame.grid(row=2, column=0, padx=8, pady=(2, 10), sticky="ew")
        uk_frame.grid_columnconfigure(0, weight=1)
        self._lbl_uk = ctk.CTkLabel(uk_frame, text="Osnova: —",
                                     font=("Segoe UI", 13, "bold"),
                                     text_color="#80CBC4")
        self._lbl_uk.grid(row=0, column=0, padx=12, pady=(8, 2), sticky="w")
        self._lbl_uk_buf = ctk.CTkLabel(uk_frame, text="S dodatkom: —",
                                         font=("Segoe UI", 14, "bold"),
                                         text_color="#69F0AE")
        self._lbl_uk_buf.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="w")

        self._init_graf()

    def _init_graf(self):
        self._fig = Figure(figsize=(10, 7), dpi=100, facecolor="#0C1A28")
        self._ax  = self._fig.add_subplot(111)
        self._ax.set_facecolor("#0C1A28")
        self._ax.text(0.5, 0.5,
                      "Učitajte CSV datoteke  →  odaberite mod  →  ▶ ANALIZIRAJ",
                      transform=self._ax.transAxes,
                      ha="center", va="center",
                      color="#2A4A6A", fontsize=11)
        self._ax.axis("off")
        self._canvas = FigureCanvasTkAgg(self._fig, master=self._gfr)
        self._canvas.get_tk_widget().pack(fill="both", expand=True)
        self._canvas.draw()

    # ── CALLBACKS ───────────────────────────────────────────────

    def _odaberi_k(self):
        p = filedialog.askopenfilename(
            title="Odaberi Kabeli_Export.csv",
            filetypes=[("CSV", "*.csv"), ("Sve", "*.*")])
        if p:
            self._kp.set(p)
            self._btn_k.configure(text="✓  " + os.path.basename(p),
                                  fg_color="#1B4332",
                                  hover_color="#2D6A4F")

    def _odaberi_b(self):
        p = filedialog.askopenfilename(
            title="Odaberi Circuit_Data_Export.csv",
            filetypes=[("CSV", "*.csv"), ("Sve", "*.*")])
        if p:
            self._bp.set(p)
            self._btn_b.configure(text="✓  " + os.path.basename(p),
                                  fg_color="#1B4332",
                                  hover_color="#2D6A4F")

    def _on_tol(self, val):
        self._lbl_tol_v.configure(text=f"{float(val):.0f} jed.")

    def _status(self, msg, color="#546E7A"):
        self._lbl_status.configure(text=msg, text_color=color)
        self.update_idletasks()

    def _set_info(self, txt, color="#90A4AE"):
        self._txt_info.configure(state="normal")
        self._txt_info.delete("1.0", "end")
        self._txt_info.insert("end", txt)
        self._txt_info.configure(state="disabled", text_color=color)

    def _on_buffer_change(self, *args):
        """Automatski osvježi listu kad korisnik promijeni buffer %."""
        if self.rezultati:
            self._popuni_listu()

    def _unit_factor(self):
        """Množitelj DWG jed. → metri; None ako jedinica nije zadana."""
        return {"mm": 0.001, "cm": 0.01, "m": 1.0}.get(self._unit.get())

    def _fmt(self, v):
        """Formatiraj duljinu u odabranoj jedinici (metri ili 'jed.')."""
        f = self._unit_factor()
        if f is None:
            return f"{v:,.1f} jed."
        return f"{v * f:,.2f} m"

    def _on_unit_change(self):
        if self.rezultati:
            self._popuni_listu()
            self._crtaj(self._highlighted)

    def _predlozi_tol(self):
        kabeli = self.kabeli
        if not kabeli:
            kp = self._kp.get()
            if not kp:
                messagebox.showinfo("Nema podataka",
                                    "Prvo odaberi Kabeli_Export.csv.")
                return
            kabeli, _ = ucitaj_kabele(kp)
            if not kabeli:
                self._set_info("Nema valjanih kabela u odabranom CSV-u.")
                return
        rez = analiziraj_toleranciju(kabeli, self._tol.get())
        if not rez:
            self._set_info("Nema dovoljno točaka za analizu.")
            return

        lines = [f"Min. razmak krajnjih točaka: {rez['min_razmak']} jed.",
                 f"Top 10 razmaci: {rez['top10']}"]

        t_sp = rez.get("t_spojevi", 0)
        if t_sp:
            lines.append(f"\n⚡ T-spojevi pronađeni: {t_sp} kom.")
            lines.append("  (automatski se rješavaju pri analizi)")

        if rez["sve_spojeno"]:
            lines.append(f"\n✓ Tol. {self._tol.get():.0f} dovoljna — sve krajnje točke spojene.")
            color = "#A5D6A7" if not t_sp else "#FFE082"
            self._set_info("\n".join(lines), color)
        else:
            lines.append(f"\nMin. nepovezani razmak : {rez['nepov_min']} jed.")
            lines.append(f"→ Predložena tolerancija: {rez['predlozena']} jed.")
            self._set_info("\n".join(lines), "#FFCC80")
            # Automatski postavi predloženu vrijednost
            self._tol.set(rez["predlozena"])
            self._lbl_tol_v.configure(text=f"{rez['predlozena']:.0f} jed.")

    # ── ANALIZA ─────────────────────────────────────────────────

    def _analiziraj(self):
        kp = self._kp.get()
        if not kp:
            messagebox.showwarning("Nedostaje CSV",
                                   "Odaberi Kabeli_Export.csv!")
            return

        tol  = self._tol.get()
        rk   = self._rk.get().strip()
        mode = self._mode.get()
        self._status("Učitavam CSV...", "#64B5F6")

        self.kabeli, self.hmap = ucitaj_kabele(kp)
        bp = self._bp.get()
        self.blokovi = ucitaj_blokove(bp) if bp else pd.DataFrame()

        if not self.kabeli:
            self._status("Greška: nema valjanih kabela!", "#EF5350")
            return

        self._status(f"Gradim graf (tol={tol:.0f})...", "#64B5F6")
        self.G, self.cvorovi = izgradi_graf(self.kabeli, self.hmap, tol)

        self._status("Spajam blokove...", "#64B5F6")
        self.veze = povezi_blokove(self.G, self.cvorovi, self.blokovi)

        rk_v = next((v for v in self.veze if v["label"] == rk), None)
        if not rk_v:
            dostupni = sorted({v["label"] for v in self.veze})
            messagebox.showerror(
                "RK nije pronađen",
                f"Label '{rk}' nije u blokovima.\n\n"
                f"Dostupni labeli:\n" + "\n".join(dostupni))
            self._status("Greška: RK nije pronađen!", "#EF5350")
            return
        self.izvor_idx = rk_v["cvor_idx"]

        # Vertikalni parametri
        try:
            h_et = float(self._v_etaza.get())
            h_rk = float(self._v_rk_h.get())
            h_ur = float(self._v_uredaj.get())
        except (ValueError, TypeError, tk.TclError):
            h_et = float(DEFAULT_V_ETAZA)
            h_rk = float(DEFAULT_V_RK_H)
            h_ur = float(DEFAULT_V_UREDAJ)
        v_rk_calc, v_ur_calc = izracunaj_v(self._v_tip.get(), h_et, h_rk, h_ur)
        self._v_rk_calc  = v_rk_calc
        self._v_ur_calc  = v_ur_calc

        try:
            rezerva = max(0.0, float(self._rezerva.get()))
        except (ValueError, TypeError, tk.TclError):
            rezerva = 0.0

        self._status(f"Analiziram ({mode})...", "#64B5F6")
        if mode == MODE_EE:
            self.rezultati, self.edge_usage = analiziraj_ee(
                self.G, self.cvorovi, self.veze, rk,
                v_rk=v_rk_calc, v_uredaj=v_ur_calc, rezerva=rezerva)
        else:
            self.rezultati, self.edge_usage = analiziraj_ek(
                self.G, self.cvorovi, self.veze, rk,
                v_rk=v_rk_calc, v_uredaj=v_ur_calc, rezerva=rezerva)

        # Validacija
        otoci = provjeri_otoke(self.G, tol)
        n_err = sum(1 for r in self.rezultati if r.get("greska"))
        info  = []
        if otoci:
            info.append("=== OTOCI (nepovezano) ===")
            info.extend(otoci)
        else:
            info.append("✓ Graf je spojen (1 komponenta)")
        if n_err:
            info.append(f"\n⚠  {n_err} krugova/blokova bez puta")
        if mode == MODE_EE:
            kutije_sve = set()
            for r in self.rezultati:
                if not r.get("greska"):
                    kutije_sve.update(r.get("kutije") or [])
            if kutije_sve:
                info.append(f"\n◆ Predložene razdjelne kutije: "
                            f"{len(kutije_sve)} (romb na grafu)")
                info.append("  Grananje izvan trošila — bez kutije na tom"
                            " mjestu kabel mora ići lančano (dulje).")
        self._set_info("\n".join(info),
                       "#EF9A9A" if (otoci or n_err) else "#A5D6A7")

        self._highlighted = None
        self._popuni_listu()
        self._crtaj()

        uk = sum(r["duljina"] for r in self.rezultati if r.get("duljina"))
        self._status(
            f"{mode}  |  {len(self.kabeli)} kab.  |  "
            f"{len(self.rezultati)} kr.  |  uk. {self._fmt(uk)}  |  "
            f"{n_err} grešaka",
            "#81C784"
        )

    # ── LISTA KRUGOVA ───────────────────────────────────────────

    def _popuni_listu(self):
        for b in self._circuit_btns:
            b.destroy()
        self._circuit_btns.clear()

        valjani = [r for r in self.rezultati if r.get("duljina") is not None]
        uk_osnova = sum(r["duljina"] for r in valjani)
        try:
            buf = float(self._buffer.get())
        except (ValueError, TypeError, tk.TclError):
            buf = 0.0
        uk_buf = uk_osnova * (1.0 + buf / 100.0)

        self._lbl_uk.configure(text=f"Osnova: {self._fmt(uk_osnova)}")
        if buf > 0:
            self._lbl_uk_buf.configure(
                text=f"+ {buf:.1f}% = {self._fmt(uk_buf)}",
                text_color="#69F0AE")
        else:
            self._lbl_uk_buf.configure(text="S dodatkom: —",
                                        text_color="#546E7A")

        mode    = self._mode.get()
        v_rk_c  = getattr(self, "_v_rk_calc",  0.0)
        v_ur_c  = getattr(self, "_v_ur_calc",   0.0)
        has_v   = (v_rk_c + v_ur_c) > 0.0

        for r in self.rezultati:
            if r.get("greska"):
                tekst = f"{r['label']}\n⚠ {r['greska']}"
                fg, tc = "#3A1010", "#EF9A9A"
                height = 50
            else:
                vert = r.get("vertikalno", 0.0)
                rez  = r.get("rezerva",    0.0)
                fmt  = self._fmt

                line1 = f"{r['label']}   —   {fmt(r['duljina'])}"
                if mode == MODE_EE:
                    n_bl  = r.get("n_blokova", "?")
                    n_kut = len(r.get("kutije") or [])
                    kut_s = f" · {n_kut} kut." if n_kut else ""
                    line2 = (f"Trasa {fmt(r.get('mst_len', 0))}"
                             f"  +  snap {fmt(r.get('snap_extra', 0))}"
                             f"   [{n_bl} bl.{kut_s}]")
                else:
                    line2 = (f"Put {fmt(r.get('path_len', 0))}"
                             f"  +  snap "
                             f"{fmt(r.get('snap_rk', 0) + r.get('snap_blok', 0))}")
                extras = []
                if has_v:
                    extras.append(f"vert {fmt(vert)}")
                if rez > 0:
                    extras.append(f"rez {fmt(rez)}")
                line3 = "  +  ".join(extras)

                tekst  = "\n".join(x for x in (line1, line2, line3) if x)
                height = 50 + (16 if line3 else 0)
                fg, tc = "transparent", "#E3F2FD"

            btn = ctk.CTkButton(
                self._sfr, text=tekst, font=("Segoe UI", 12),
                anchor="w", fg_color=fg,
                hover_color="#1A3A5F", text_color=tc,
                height=height,
                command=lambda res=r: self._highlight(res),
            )
            btn.pack(fill="x", padx=4, pady=2)
            self._circuit_btns.append(btn)

    # ── HIGHLIGHT ───────────────────────────────────────────────

    def _highlight(self, r):
        self._highlighted = None if self._highlighted is r else r
        self._crtaj(self._highlighted)

    # ── CRTANJE ─────────────────────────────────────────────────

    def _crtaj(self, highlighted=None):
        if self.G is None:
            return
        try:
            buf = float(self._buffer.get())
        except (ValueError, TypeError, tk.TclError):
            buf = 0.0
        nacrtaj(
            self._ax, self.G, self.cvorovi, self.kabeli,
            self.blokovi, self.veze, self.rezultati, self.edge_usage,
            self.izvor_idx, self._rk.get().strip(),
            self._mode.get(), highlighted=highlighted,
            buffer_pct=buf, fmt=self._fmt,
        )
        self._fig.tight_layout(pad=0.4)
        if self._zp is None:
            self._zp = ZoomPan(self._ax)
        self._zp.save_home()
        self._canvas.draw()

    def _reset_view(self):
        if self._zp and self._zp._orig:
            self._ax.set_xlim(self._zp._orig[0])
            self._ax.set_ylim(self._zp._orig[1])
            self._canvas.draw_idle()

    # ── EXPORT ──────────────────────────────────────────────────

    def _exportiraj(self):
        if not self.rezultati:
            messagebox.showinfo("Nema rezultata",
                                "Prvo pokreni analizu.")
            return
        path = filedialog.asksaveasfilename(
            title="Spremi rezultate",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Sve", "*.*")],
            initialfile=f"Kabeli_{self._mode.get()}_Export.csv",
        )
        if not path:
            return
        try:
            try:
                buf = float(self._buffer.get())
            except (ValueError, TypeError, tk.TclError):
                buf = 0.0
            exportiraj_csv(self.rezultati, path, buffer_pct=buf,
                           unit_factor=self._unit_factor(),
                           unit_name=self._unit.get())
            messagebox.showinfo("Export gotov",
                                f"Rezultati snimljeni u:\n{path}")
        except Exception as e:
            messagebox.showerror("Greška pri exportu", str(e))


# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════

def main():
    app = KabelskiApp()
    app.mainloop()


if __name__ == "__main__":
    main()