"""
Kabelski Graf  –  AutoCAD CSV → topološki graf  v3.3
=====================================================
Modovi rada:
  EE – Serijski : MST koji spaja RK i sve blokove jednog strujnog kruga
  EK – Zvijezda : Najkraći put od RK do svakog bloka zasebno

Novo u v3.3:
  - Vertikalni model: procjena vertikalnih kabelskih hodova (po podu ili
    spuštenim stropom). Parametri: visina etaže, visina RK, visina uređaja.
    Rezultati uključuju horizontalnu + vertikalnu komponentu s rasporedom
    prikazanim u listi strujnih krugova.

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


# ══════════════════════════════════════════════════════════════
#  CSV UČITAVANJE
# ══════════════════════════════════════════════════════════════

def _parse_pts(raw):
    """'(x y z) (x y z) ...'  →  lista (x, y) tuplova."""
    pts = []
    for p in re.findall(r'\((.*?)\)', str(raw)):
        c = p.strip().split()
        if len(c) >= 2:
            try:
                pts.append((float(c[0]), float(c[1])))
            except ValueError:
                pass
    return pts


def ucitaj_kabele(path):
    """Vraca (kabeli, handle_map)."""
    if not os.path.exists(path):
        return [], []
    df = pd.read_csv(path, sep=";", dtype=str)
    kabeli, hmap = [], []
    for _, row in df.iterrows():
        pts = _parse_pts(row.get("Vertex_Coords(X,Y,Z)", ""))
        if len(pts) >= 2:
            kabeli.append(pts)
            hmap.append({
                "kabel_id": row.get("Kabel_ID", ""),
                "handle":   row.get("Handle",   ""),
                "layer":    row.get("Layer",     ""),
                "width":    row.get("Width",     ""),
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


def _pt_to_segment_dist(p, a, b):
    """Udaljenost točke p od segmenta ab + parametar t ∈ [0,1]."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    seg2 = dx * dx + dy * dy
    if seg2 < 1e-12:
        return _dist(p, a), 0.0
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / seg2
    t = max(0.0, min(1.0, t))
    return _dist(p, (a[0] + t * dx, a[1] + t * dy)), t


def _razriješi_t_spojeve(kabeli, tol_seg=2.0):
    """
    T-spoj fix: za svaki vrh kabela A koji leži NA segmentu kabela B
    (udaljenost ≤ tol_seg, ali nije blizu ni jednom vrhu segmenta),
    umetni taj vrh kao novu točku u kabel B.

    Rezultat: snap algoritam automatski poveže obje polilinije
    bez potrebe za velikim snap tolerancijama.
    """
    kabeli = [list(k) for k in kabeli]
    for j in range(len(kabeli)):
        nova = [kabeli[j][0]]
        for si in range(len(kabeli[j]) - 1):
            a, b = kabeli[j][si], kabeli[j][si + 1]
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
            for _, pt in dedup:
                nova.append(pt)
            nova.append(b)
        kabeli[j] = nova
    return kabeli


class _Snap:
    """Spaja vrhove polilinija unutar tolerancije u isti čvor."""
    def __init__(self, tol):
        self.tol = tol
        self.pts = []

    def dodaj(self, pt):
        for i, c in enumerate(self.pts):
            if _dist(pt, c) <= self.tol:
                return i
        self.pts.append(pt)
        return len(self.pts) - 1


def izgradi_graf(kabeli, hmap, tol):
    # Riješi T-spojeve prije snap-a (vrh jednog kabela na segmentu drugog)
    kabeli = _razriješi_t_spojeve(kabeli, tol_seg=2.0)
    snap = _Snap(tol)
    G = nx.Graph()
    for pi, poli in enumerate(kabeli):
        ids = [snap.dodaj(p) for p in poli]
        hi  = hmap[pi] if pi < len(hmap) else {}
        for k in range(len(ids) - 1):
            u, v = ids[k], ids[k + 1]
            if u == v:
                continue
            d  = _dist(snap.pts[u], snap.pts[v])
            ed = dict(weight=d,
                      handle=hi.get("handle", ""),
                      layer=hi.get("layer",   ""))
            if G.has_edge(u, v):
                if d < G[u][v]["weight"]:
                    G[u][v].update(**ed)
            else:
                G.add_edge(u, v, **ed)
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


def povezi_blokove(cvorovi, blokovi):
    veze = []
    if blokovi.empty:
        return veze
    for _, row in blokovi.iterrows():
        bx, by   = float(row["X"]), float(row["Y"])
        idx, d   = _najblizi(cvorovi, (bx, by))
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
                    if d <= 2.0 and 0.001 < t < 0.999:
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

def analiziraj_ee(G, cvorovi, veze, rk_label, v_rk=0.0, v_uredaj=0.0):
    """
    Za svaki Circuit_Label gradi metric-closure auxiliary graf
    ({RK čvor} ∪ {čvorovi svih blokova tog kruga}), iz njega
    izvlači MST i ukupnu duljinu kabela.

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
        mst_len = sum(d["weight"] for _, _, d in MST.edges(data=True))
        snap_e  = izvor_snap + sum(b["snap_d"] for b in blokovi_k)
        n_bl    = len(blokovi_k)
        # Vertikale: jedan izlaz iz RK + po jedan ulaz u svaki uređaj
        vert    = v_rk + n_bl * v_uredaj

        putanje = []
        for ti, tj in MST.edges():
            put = paths.get((ti, tj)) or paths.get((tj, ti))
            if put:
                putanje.append(put)
                for k in range(len(put) - 1):
                    e = (min(put[k], put[k+1]), max(put[k], put[k+1]))
                    edge_usage[e] = edge_usage.get(e, 0) + 1

        rezultati.append({
            "label":      label,
            "tip":        "EE",
            "duljina":    mst_len + snap_e + vert,
            "mst_len":    mst_len,
            "snap_extra": snap_e,
            "vertikalno": vert,
            "v_rk":       v_rk,
            "v_uredaj":   v_uredaj,
            "greska":     None,
            "putanje":    putanje,
            "n_blokova":  n_bl,
        })

    rezultati.sort(key=lambda r: r["duljina"] or float("inf"))
    return rezultati, edge_usage


# ══════════════════════════════════════════════════════════════
#  EK  –  ZVIJEZDASTA INSTALACIJA  (shortest_path po bloku)
# ══════════════════════════════════════════════════════════════

def analiziraj_ek(G, cvorovi, veze, rk_label, v_rk=0.0, v_uredaj=0.0):
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
            ukupno = izvor_snap + plen + cilj_snap + vert

            for k in range(len(put) - 1):
                e = (min(put[k], put[k+1]), max(put[k], put[k+1]))
                edge_usage[e] = edge_usage.get(e, 0) + 1

            rezultati.append({
                "label":      oznaka,  "tip":        "EK",
                "duljina":    ukupno,  "path_len":   plen,
                "snap_rk":    izvor_snap, "snap_blok": cilj_snap,
                "vertikalno": vert,    "v_rk":       v_rk,
                "v_uredaj":   v_uredaj,
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

def exportiraj_csv(rezultati, path, buffer_pct=0.0):
    has_vert = any(r.get("vertikalno", 0.0) > 0
                   for r in rezultati if not r.get("greska"))
    has_buf  = buffer_pct > 0

    header = ["Oznaka", "Tip_Instalacije",
              "Horizontalno", "Vertikalno", "Duljina_Kabela"]
    if has_buf:
        header.append(f"S_bufferom_{buffer_pct:.1f}%")

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(header)
        ukupno = 0.0
        for r in rezultati:
            d    = r.get("duljina")
            vert = r.get("vertikalno", 0.0) if not r.get("greska") else 0.0
            horiz = (d - vert) if d is not None else None
            row = [
                r["label"],
                r["tip"],
                f"{horiz:.2f}" if horiz is not None else "GREŠKA",
                f"{vert:.2f}"  if d    is not None else "GREŠKA",
                f"{d:.2f}"     if d    is not None else "GREŠKA",
            ]
            if has_buf:
                row.append(f"{d * (1 + buffer_pct / 100):.2f}"
                           if d is not None else "GREŠKA")
            w.writerow(row)
            if d:
                ukupno += d

        uk_row = ["UKUPNO", "", "", "", f"{ukupno:.2f}"]
        if has_buf:
            uk_row.append(f"{ukupno * (1 + buffer_pct / 100):.2f}")
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
            mode, highlighted=None, buffer_pct=0.0):
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
        naslov = (f"{highlighted['label']}   →   "
                  f"{highlighted['duljina']:,.1f} jed.")
        nc = C_HL_INNER
    else:
        buf_str = (f"  |  +{buffer_pct:.1f}% = {uk_buffer:,.1f} jed."
                   if buffer_pct > 0 else "")
        naslov = (f"Mode: {mode_str}  |  Osnova: {uk_osnova:,.1f} jed."
                  f"{buf_str}  |  Čvorovi: {G.number_of_nodes()}  |  Komp.: {n_komp}")
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
        self.title("Kabelski Graf  –  MST Analizator  v3.3")
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
        self._kp     = ctk.StringVar()
        self._bp     = ctk.StringVar()
        self._tol    = ctk.DoubleVar(value=DEFAULT_TOL)
        self._rk     = ctk.StringVar(value=DEFAULT_RK)
        self._mode   = ctk.StringVar(value=MODE_EE)
        self._buffer = ctk.DoubleVar(value=0.0)

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

        # ── LIJEVI PANEL ────────────────────────────────────────
        lp = ctk.CTkFrame(self, width=298, corner_radius=0)
        lp.grid(row=0, column=0, sticky="nsew")
        lp.grid_propagate(False)
        lp.grid_columnconfigure(0, weight=1)

        F_LBL  = ("Arial", 12)
        F_BOLD = ("Arial", 12, "bold")
        F_SM   = ("Arial", 10)

        def lbl(text, row, bold=False, pady=(4, 0)):
            ctk.CTkLabel(lp, text=text,
                         font=F_BOLD if bold else F_LBL).grid(
                row=row, column=0, padx=14, pady=pady, sticky="w")

        lbl("KABELSKI GRAF  v3.3", 0, bold=True, pady=(14, 6))

        # ── MOD RADA ──────────────────────────────────────────
        mf = ctk.CTkFrame(lp, fg_color="#0F2030", corner_radius=8)
        mf.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="ew")
        mf.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkLabel(mf, text="MOD RADA", font=F_SM).grid(
            row=0, column=0, columnspan=2, pady=(7, 3))
        ctk.CTkRadioButton(mf, text="EE – Serijski",
                           variable=self._mode, value=MODE_EE,
                           font=F_BOLD).grid(
            row=1, column=0, padx=10, pady=(0, 8), sticky="w")
        ctk.CTkRadioButton(mf, text="EK – Zvijezda",
                           variable=self._mode, value=MODE_EK,
                           font=F_BOLD).grid(
            row=1, column=1, padx=10, pady=(0, 8), sticky="w")

        # ── CSV ─────────────────────────────────────────────────
        lbl("Kabeli_Export.csv:", 2)
        ctk.CTkButton(lp, text="Odaberi...", width=112, font=F_SM,
                      command=self._odaberi_k).grid(
            row=3, column=0, padx=14, pady=(2, 0), sticky="w")
        self._lbl_k = ctk.CTkLabel(lp, text="—", font=F_SM,
                                    text_color="#78909C", wraplength=258)
        self._lbl_k.grid(row=4, column=0, padx=14, sticky="w")

        lbl("Circuit_Data_Export.csv:", 5, pady=(6, 0))
        ctk.CTkButton(lp, text="Odaberi...", width=112, font=F_SM,
                      command=self._odaberi_b).grid(
            row=6, column=0, padx=14, pady=(2, 0), sticky="w")
        self._lbl_b = ctk.CTkLabel(lp, text="—", font=F_SM,
                                    text_color="#78909C", wraplength=258)
        self._lbl_b.grid(row=7, column=0, padx=14, sticky="w")

        # ── TOLERANCIJA ─────────────────────────────────────────
        tf = ctk.CTkFrame(lp, fg_color="transparent")
        tf.grid(row=8, column=0, padx=0, pady=(8, 0), sticky="ew")
        tf.grid_columnconfigure(0, weight=1)

        r_tf = ctk.CTkFrame(tf, fg_color="transparent")
        r_tf.grid(row=0, column=0, padx=14, sticky="ew")
        r_tf.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(r_tf, text="Tolerancija spajanja:", font=F_LBL).grid(
            row=0, column=0, sticky="w")
        self._lbl_tol_v = ctk.CTkLabel(r_tf,
                                        text=f"{DEFAULT_TOL:.0f} jed.",
                                        font=F_BOLD, text_color="#64B5F6")
        self._lbl_tol_v.grid(row=0, column=1, sticky="e")

        ctk.CTkSlider(tf, from_=1, to=1000, variable=self._tol,
                      command=self._on_tol, width=262).grid(
            row=1, column=0, padx=14, pady=(3, 0), sticky="ew")

        ctk.CTkButton(tf, text="⚙  Predloži toleranciju", height=30,
                      font=F_SM, fg_color="transparent", border_width=1,
                      command=self._predlozi_tol).grid(
            row=2, column=0, padx=14, pady=(5, 0), sticky="ew")

        # ── RK LABEL ────────────────────────────────────────────
        lbl("Razvodna kutija (Circuit_Label):", 9, pady=(8, 0))
        ctk.CTkEntry(lp, textvariable=self._rk, width=200,
                     height=30, font=F_LBL).grid(
            row=10, column=0, padx=14, pady=(2, 0), sticky="w")

        # ── BUFFER % ────────────────────────────────────────────
        bf_frame = ctk.CTkFrame(lp, fg_color="#0F2030", corner_radius=8)
        bf_frame.grid(row=11, column=0, padx=10, pady=(8, 0), sticky="ew")
        bf_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(bf_frame, text="Dodatak na duljinu (%):",
                     font=F_LBL).grid(
            row=0, column=0, padx=12, pady=(8, 2), sticky="w")
        buf_row = ctk.CTkFrame(bf_frame, fg_color="transparent")
        buf_row.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")
        buf_row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(buf_row, textvariable=self._buffer,
                     width=90, height=30, font=F_LBL).grid(
            row=0, column=0, sticky="w")
        ctk.CTkLabel(buf_row, text="%", font=F_LBL,
                     text_color="#78909C").grid(
            row=0, column=1, padx=(6, 0), sticky="w")

        # ── VERTIKALNI MODEL ────────────────────────────────────
        vf = ctk.CTkFrame(lp, fg_color="#0A1E10", corner_radius=8)
        vf.grid(row=12, column=0, padx=10, pady=(8, 0), sticky="ew")
        vf.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(vf, text="VERTIKALNI RAZVOD",
                     font=("Arial", 10, "bold"),
                     text_color="#81C784").grid(
            row=0, column=0, padx=12, pady=(7, 3), sticky="w")

        # Radio: tip razvoda
        vr = ctk.CTkFrame(vf, fg_color="transparent")
        vr.grid(row=1, column=0, padx=8, pady=(0, 4), sticky="ew")
        vr.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkRadioButton(vr, text="Po podu",
                           variable=self._v_tip, value=RAZVOD_POD,
                           font=F_SM).grid(row=0, column=0, padx=4, sticky="w")
        ctk.CTkRadioButton(vr, text="Spušteni strop",
                           variable=self._v_tip, value=RAZVOD_STROP,
                           font=F_SM).grid(row=0, column=1, padx=4, sticky="w")

        def _v_row(parent, row, label, var, tooltip=""):
            r = ctk.CTkFrame(parent, fg_color="transparent")
            r.grid(row=row, column=0, padx=10, pady=1, sticky="ew")
            r.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(r, text=label, font=F_SM,
                         text_color="#A5D6A7", width=100, anchor="w").grid(
                row=0, column=0, sticky="w")
            ctk.CTkEntry(r, textvariable=var, width=72,
                         height=26, font=F_SM).grid(
                row=0, column=1, padx=(4, 0), sticky="w")
            ctk.CTkLabel(r, text="jed.", font=F_SM,
                         text_color="#546E7A").grid(
                row=0, column=2, padx=(4, 0), sticky="w")

        _v_row(vf, 2, "Vis. etaže:",  self._v_etaza)
        _v_row(vf, 3, "Vis. RK:",     self._v_rk_h)
        _v_row(vf, 4, "Vis. uređaja:", self._v_uredaj)

        ctk.CTkLabel(vf,
                     text="Vrijednosti u istim jedinicama kao DWG",
                     font=("Arial", 9), text_color="#37474F").grid(
            row=5, column=0, padx=12, pady=(2, 6), sticky="w")

        # ── GUMBI ───────────────────────────────────────────────
        ctk.CTkButton(lp, text="▶  ANALIZIRAJ",
                      font=("Arial", 13, "bold"), height=40,
                      command=self._analiziraj).grid(
            row=13, column=0, padx=14, pady=10, sticky="ew")

        btn_row = ctk.CTkFrame(lp, fg_color="transparent")
        btn_row.grid(row=14, column=0, padx=14, sticky="ew")
        btn_row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(btn_row, text="Reset  (R)", height=30, font=F_SM,
                      fg_color="transparent", border_width=1,
                      command=self._reset_view).grid(
            row=0, column=0, padx=(0, 3), sticky="ew")
        ctk.CTkButton(btn_row, text="Export CSV", height=30, font=F_SM,
                      fg_color="#1B5E20",
                      command=self._exportiraj).grid(
            row=0, column=1, padx=(3, 0), sticky="ew")

        # ── INFO / UPOZORENJA ───────────────────────────────────
        lbl("Tolerancija / Validacija:", 15, pady=(10, 2))
        self._txt_info = ctk.CTkTextbox(lp, height=120,
                                         font=("Courier", 10), wrap="word")
        self._txt_info.grid(row=16, column=0, padx=8, pady=(0, 4), sticky="ew")
        self._txt_info.insert("end", "—")
        self._txt_info.configure(state="disabled")

        self._lbl_status = ctk.CTkLabel(lp, text="Spreman.",
                                         font=F_SM, text_color="#78909C",
                                         wraplength=270)
        self._lbl_status.grid(row=17, column=0, padx=12,
                               pady=(0, 12), sticky="w")

        # ── DESNI DIO: Graf + Lista ──────────────────────────────
        rp = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        rp.grid(row=0, column=1, sticky="nsew", padx=2)
        rp.grid_columnconfigure(0, weight=1)
        rp.grid_rowconfigure(0, weight=1)

        pw = tk.PanedWindow(rp, orient=tk.HORIZONTAL,
                             bg="#090910", sashwidth=5)
        pw.grid(row=0, column=0, sticky="nsew")

        self._gfr = ctk.CTkFrame(pw, fg_color="#0C1A28", corner_radius=0)
        pw.add(self._gfr, minsize=630)

        lf = ctk.CTkFrame(pw, width=320, corner_radius=0)
        pw.add(lf, minsize=275)
        lf.grid_rowconfigure(1, weight=1)
        lf.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(lf, text="Strujni krugovi / Blokovi",
                     font=("Arial", 15, "bold")).grid(
            row=0, column=0, padx=12, pady=(10, 4), sticky="w")
        self._sfr = ctk.CTkScrollableFrame(lf)
        self._sfr.grid(row=1, column=0, sticky="nsew", padx=5, pady=(0, 4))

        # Ukupno osnova + buffer
        uk_frame = ctk.CTkFrame(lf, fg_color="#0A1A0A", corner_radius=6)
        uk_frame.grid(row=2, column=0, padx=8, pady=(2, 10), sticky="ew")
        uk_frame.grid_columnconfigure(0, weight=1)
        self._lbl_uk = ctk.CTkLabel(uk_frame, text="Osnova: —",
                                     font=("Arial", 14, "bold"),
                                     text_color="#80CBC4")
        self._lbl_uk.grid(row=0, column=0, padx=12, pady=(8, 2), sticky="w")
        self._lbl_uk_buf = ctk.CTkLabel(uk_frame, text="S dodatkom: —",
                                         font=("Arial", 15, "bold"),
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
            self._lbl_k.configure(text=os.path.basename(p),
                                   text_color="#81C784")

    def _odaberi_b(self):
        p = filedialog.askopenfilename(
            title="Odaberi Circuit_Data_Export.csv",
            filetypes=[("CSV", "*.csv"), ("Sve", "*.*")])
        if p:
            self._bp.set(p)
            self._lbl_b.configure(text=os.path.basename(p),
                                   text_color="#81C784")

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
        self.veze = povezi_blokove(self.cvorovi, self.blokovi)

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

        self._status(f"Analiziram ({mode})...", "#64B5F6")
        if mode == MODE_EE:
            self.rezultati, self.edge_usage = analiziraj_ee(
                self.G, self.cvorovi, self.veze, rk,
                v_rk=v_rk_calc, v_uredaj=v_ur_calc)
        else:
            self.rezultati, self.edge_usage = analiziraj_ek(
                self.G, self.cvorovi, self.veze, rk,
                v_rk=v_rk_calc, v_uredaj=v_ur_calc)

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
        self._set_info("\n".join(info),
                       "#EF9A9A" if (otoci or n_err) else "#A5D6A7")

        self._highlighted = None
        self._popuni_listu()
        self._crtaj()

        uk = sum(r["duljina"] for r in self.rezultati if r.get("duljina"))
        self._status(
            f"{mode}  |  {len(self.kabeli)} kab.  |  "
            f"{len(self.rezultati)} kr.  |  uk. {uk:,.1f} jed.  |  "
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

        self._lbl_uk.configure(text=f"Osnova: {uk_osnova:,.1f} jed.")
        if buf > 0:
            self._lbl_uk_buf.configure(
                text=f"+ {buf:.1f}% = {uk_buf:,.1f} jed.",
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
                tekst = f"  {r['label']}\n  ⚠ {r['greska']}"
                fg, tc = "#3A1010", "#EF9A9A"
                height = 54
            else:
                vert = r.get("vertikalno", 0.0)
                horiz = r["duljina"] - vert

                if mode == MODE_EE:
                    n_bl  = r.get("n_blokova", "?")
                    mst_l = r.get("mst_len", 0)
                    snap  = r.get("snap_extra", 0)
                    line2 = (f"  MST: {mst_l:,.1f}  +  snap: {snap:,.1f}"
                             f"  [{n_bl} bl.]")
                    if has_v:
                        line3 = (f"  Vert: +{vert:,.1f}"
                                 f"  (↑RK {v_rk_c:.0f}"
                                 f" + {n_bl}×↕{v_ur_c:.0f})")
                    else:
                        line3 = ""
                else:
                    pl  = r.get("path_len", 0)
                    srk = r.get("snap_rk", 0)
                    sbl = r.get("snap_blok", 0)
                    line2 = f"  Put: {pl:,.1f}  +  snap: {srk+sbl:,.1f}"
                    if has_v:
                        line3 = (f"  Vert: +{vert:,.1f}"
                                 f"  (↑RK {v_rk_c:.0f}"
                                 f" + ↕ur {v_ur_c:.0f})")
                    else:
                        line3 = ""

                if has_v:
                    line1 = (f"  {r['label']}\n"
                             f"  Horiz: {horiz:,.1f}  +  vert: {vert:,.1f}"
                             f"  =  {r['duljina']:,.1f} jed.")
                    tekst  = f"{line1}\n{line2}\n{line3}"
                    height = 86
                else:
                    tekst  = (f"  {r['label']}\n"
                              f"  Ukupno: {r['duljina']:,.1f} jed.\n"
                              f"{line2}")
                    height = 68
                fg, tc = "transparent", "#E3F2FD"

            btn = ctk.CTkButton(
                self._sfr, text=tekst, font=("Arial", 13),
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
            buffer_pct=buf,
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
            exportiraj_csv(self.rezultati, path, buffer_pct=buf)
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