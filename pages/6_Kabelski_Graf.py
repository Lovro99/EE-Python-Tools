"""
Kabelski Graf – AutoCAD CSV → topološki graf, MST analiza duljine kabela.
"""

import io
import csv
import math
import re
from collections import defaultdict

import streamlit as st
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx

# ── Konstante ─────────────────────────────────────────────────────────────────

MODE_EE     = "EE – Serijski (MST)"
MODE_EK     = "EK – Zvijezda (shortest path)"
C_BG        = "#0C1A28"
C_EE        = "#1E88E5"
C_EK        = "#43A047"
C_HL_OUTER  = "#FF6F00"
C_HL_INNER  = "#FFD600"
C_KRAJ      = "#66BB6A"
C_TRAN      = "#FFA726"
C_CVOR      = "#EF5350"
C_BLOK      = "#E53935"
C_RK        = "#FFD600"
C_VEZA      = "#9C27B0"

# ── Parsiranje CSV ────────────────────────────────────────────────────────────

def _parse_pts(raw):
    pts = []
    for p in re.findall(r'\((.*?)\)', str(raw)):
        c = p.strip().split()
        if len(c) >= 2:
            try:
                pts.append((float(c[0]), float(c[1])))
            except ValueError:
                pass
    return pts


def ucitaj_kabele(file_bytes):
    df = pd.read_csv(io.BytesIO(file_bytes), sep=";", dtype=str)
    kabeli, hmap = [], []
    for _, row in df.iterrows():
        pts = _parse_pts(row.get("Vertex_Coords(X,Y,Z)", ""))
        if len(pts) >= 2:
            kabeli.append(pts)
            hmap.append({
                "kabel_id": row.get("Kabel_ID", ""),
                "handle":   row.get("Handle",   ""),
                "layer":    row.get("Layer",     ""),
            })
    return kabeli, hmap


def ucitaj_blokove(file_bytes):
    df = pd.read_csv(io.BytesIO(file_bytes), sep=";", dtype=str)
    for col in ("X", "Y", "Z"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df


# ── Graf ──────────────────────────────────────────────────────────────────────

def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _pt_to_segment_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    seg2 = dx * dx + dy * dy
    if seg2 < 1e-12:
        return _dist(p, a), 0.0
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / seg2
    t = max(0.0, min(1.0, t))
    return _dist(p, (a[0] + t * dx, a[1] + t * dy)), t


def _razrijesi_t_spojeve(kabeli, tol_seg=2.0):
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
                    if _dist(pt, a) <= tol_seg or _dist(pt, b) <= tol_seg:
                        continue
                    d, t = _pt_to_segment_dist(pt, a, b)
                    if d <= tol_seg and 0.001 < t < 0.999:
                        ubaci.append((t, pt))
            ubaci.sort(key=lambda x: x[0])
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
    kabeli = _razrijesi_t_spojeve(kabeli, tol_seg=2.0)
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
            ed = dict(weight=d, handle=hi.get("handle", ""), layer=hi.get("layer", ""))
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


def povezi_blokove(cvorovi, blokovi):
    veze = []
    if blokovi.empty:
        return veze
    for _, row in blokovi.iterrows():
        bx, by = float(row["X"]), float(row["Y"])
        best_i, best_d = 0, float("inf")
        for i, c in enumerate(cvorovi):
            d = _dist((bx, by), c)
            if d < best_d:
                best_d, best_i = d, i
        veze.append({
            "label":   str(row.get("Circuit_Label", "")),
            "blok_xy": (bx, by),
            "cvor_idx": best_i,
            "snap_d":   best_d,
            "handle":   str(row.get("Handle", "")),
            "block_name": str(row.get("Block_Name", "")),
        })
    return veze


# ── Analiza ───────────────────────────────────────────────────────────────────

def analiziraj_ee(G, cvorovi, veze, rk_label):
    rk_v = next((v for v in veze if v["label"] == rk_label), None)
    if not rk_v:
        return [], {}
    izvor = rk_v["cvor_idx"]
    grupe = defaultdict(list)
    for v in veze:
        if v["label"] != rk_label:
            grupe[v["label"]].append(v)
    edge_usage, rezultati = {}, []
    for label, blokovi_k in grupe.items():
        terminali = list({izvor} | {b["cvor_idx"] for b in blokovi_k})
        aux = nx.Graph()
        aux.add_nodes_from(terminali)
        paths = {}
        for i, ti in enumerate(terminali):
            for tj in terminali[i + 1:]:
                try:
                    put = nx.shortest_path(G, ti, tj, weight="weight")
                    d   = sum(G[put[k]][put[k+1]]["weight"] for k in range(len(put) - 1))
                    aux.add_edge(ti, tj, weight=d)
                    paths[(ti, tj)] = put
                    paths[(tj, ti)] = put[::-1]
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    pass
        if not nx.is_connected(aux):
            rezultati.append({"label": label, "tip": "EE", "duljina": None, "greska": "Nepovezani čvorovi", "putanje": [], "n_blokova": len(blokovi_k)})
            continue
        MST     = nx.minimum_spanning_tree(aux, weight="weight")
        mst_len = sum(d["weight"] for _, _, d in MST.edges(data=True))
        snap_e  = rk_v["snap_d"] + sum(b["snap_d"] for b in blokovi_k)
        putanje = []
        for ti, tj in MST.edges():
            put = paths.get((ti, tj)) or paths.get((tj, ti))
            if put:
                putanje.append(put)
                for k in range(len(put) - 1):
                    e = (min(put[k], put[k+1]), max(put[k], put[k+1]))
                    edge_usage[e] = edge_usage.get(e, 0) + 1
        rezultati.append({"label": label, "tip": "EE", "duljina": mst_len + snap_e, "mst_len": mst_len, "snap_extra": snap_e, "greska": None, "putanje": putanje, "n_blokova": len(blokovi_k)})
    rezultati.sort(key=lambda r: r["duljina"] or float("inf"))
    return rezultati, edge_usage


def analiziraj_ek(G, cvorovi, veze, rk_label):
    rk_v = next((v for v in veze if v["label"] == rk_label), None)
    if not rk_v:
        return [], {}
    izvor = rk_v["cvor_idx"]
    edge_usage, rezultati = {}, []
    for i, veza in enumerate(veze):
        if veza["label"] == rk_label:
            continue
        cilj  = veza["cvor_idx"]
        oznaka = veza["label"] or veza.get("block_name", "") or f"Blok_{i+1}"
        try:
            put   = nx.shortest_path(G, izvor, cilj, weight="weight")
            plen  = sum(G[put[k]][put[k+1]]["weight"] for k in range(len(put) - 1))
            ukupno = rk_v["snap_d"] + plen + veza["snap_d"]
            for k in range(len(put) - 1):
                e = (min(put[k], put[k+1]), max(put[k], put[k+1]))
                edge_usage[e] = edge_usage.get(e, 0) + 1
            rezultati.append({"label": oznaka, "tip": "EK", "duljina": ukupno, "path_len": plen, "snap_rk": rk_v["snap_d"], "snap_blok": veza["snap_d"], "greska": None, "putanje": [put], "blok_xy": veza["blok_xy"]})
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            rezultati.append({"label": oznaka, "tip": "EK", "duljina": None, "greska": "Nema puta u grafu", "putanje": [], "blok_xy": veza["blok_xy"]})
    rezultati.sort(key=lambda r: r["duljina"] or float("inf"))
    return rezultati, edge_usage


def analiziraj_toleranciju(kabeli, tol_tren):
    krajevi = [pt for poli in kabeli for pt in (poli[0], poli[-1])]
    razmaci = sorted(
        _dist(krajevi[i], krajevi[j])
        for i in range(len(krajevi))
        for j in range(i + 1, len(krajevi))
        if _dist(krajevi[i], krajevi[j]) > 0.001
    )
    if not razmaci:
        return None
    nepov = [d for d in razmaci if d > tol_tren]
    return {
        "min_razmak": round(razmaci[0], 2),
        "top10":      [round(d, 2) for d in razmaci[:10]],
        "nepov_min":  round(nepov[0], 2) if nepov else None,
        "predlozena": round(nepov[0] * 1.15, 1) if nepov else tol_tren,
        "sve_spojeno": len(nepov) == 0,
    }


# ── Vizualizacija ─────────────────────────────────────────────────────────────

def nacrtaj(G, cvorovi, kabeli_raw, blokovi, veze, rezultati,
            edge_usage, izvor_idx, rk_label, mode, highlighted=None, buffer_pct=0.0):
    fig, ax = plt.subplots(figsize=(12, 8))
    ax.set_facecolor(C_BG)
    fig.patch.set_facecolor(C_BG)
    ax.set_aspect("equal")

    if not cvorovi:
        ax.text(0.5, 0.5, "Nema podataka", transform=ax.transAxes,
                ha="center", va="center", color="#444", fontsize=13)
        return fig

    for poli in kabeli_raw:
        ax.plot([p[0] for p in poli], [p[1] for p in poli],
                color="#2E6FA3", lw=1.5, alpha=0.7, zorder=1, solid_capstyle="round")

    sve_e, hl_e = set(), set()
    for r in rezultati:
        if not r.get("greska"):
            for put in r.get("putanje", []):
                for k in range(len(put) - 1):
                    sve_e.add((min(put[k], put[k+1]), max(put[k], put[k+1])))

    if highlighted and not highlighted.get("greska"):
        for put in highlighted.get("putanje", []):
            for k in range(len(put) - 1):
                hl_e.add((min(put[k], put[k+1]), max(put[k], put[k+1])))

    boja = C_EE if "EE" in mode else C_EK
    for u, v in G.edges():
        e = (min(u, v), max(u, v))
        if e not in sve_e or e in hl_e:
            continue
        x1, y1 = cvorovi[u]; x2, y2 = cvorovi[v]
        cnt = edge_usage.get(e, 0)
        ax.plot([x1, x2], [y1, y2], color=boja, lw=2.5 + min(cnt, 8) * 0.4,
                alpha=0.95, zorder=3, solid_capstyle="round")

    for u, v in G.edges():
        e = (min(u, v), max(u, v))
        if e not in hl_e:
            continue
        x1, y1 = cvorovi[u]; x2, y2 = cvorovi[v]
        ax.plot([x1, x2], [y1, y2], color=C_HL_OUTER, lw=6.0, alpha=0.4, zorder=4)
        ax.plot([x1, x2], [y1, y2], color=C_HL_INNER, lw=2.5, alpha=1.0, zorder=5)

    for e, cnt in edge_usage.items():
        if cnt < 2 or e[0] >= len(cvorovi) or e[1] >= len(cvorovi):
            continue
        mx = (cvorovi[e[0]][0] + cvorovi[e[1]][0]) / 2
        my = (cvorovi[e[0]][1] + cvorovi[e[1]][1]) / 2
        ax.text(mx, my, str(cnt), fontsize=8, fontweight="bold", color="white",
                ha="center", va="center", zorder=9,
                bbox=dict(boxstyle="round,pad=0.2", fc="#0A2A50", ec="#42A5F5", alpha=0.9))

    for i, (cx, cy) in enumerate(cvorovi):
        if i == izvor_idx:
            continue
        deg = G.degree(i) if i in G else 0
        bc  = C_KRAJ if deg == 1 else (C_CVOR if deg >= 3 else C_TRAN)
        ax.scatter(cx, cy, s=20, c=bc, zorder=6, edgecolors="none", alpha=0.8)

    for veza in veze:
        bx, by = veza["blok_xy"]
        cx, cy = cvorovi[veza["cvor_idx"]]
        ax.plot([bx, cx], [by, cy], color=C_VEZA, lw=0.6, ls="--", alpha=0.4, zorder=5)

    if not blokovi.empty:
        mask  = blokovi["Circuit_Label"].astype(str) == rk_label
        df_sk = blokovi[~mask]
        df_rk = blokovi[mask]
        if not df_sk.empty:
            ax.scatter(df_sk["X"].astype(float), df_sk["Y"].astype(float),
                       c=C_BLOK, s=80, zorder=7, edgecolors="white", lw=1.0, marker="s")
            for _, row in df_sk.iterrows():
                ax.annotate(str(row["Circuit_Label"]),
                            (float(row["X"]), float(row["Y"])),
                            xytext=(5, 5), textcoords="offset points",
                            fontsize=8, fontweight="bold", color="#FFCDD2", zorder=8)
        if not df_rk.empty:
            ax.scatter(df_rk["X"].astype(float), df_rk["Y"].astype(float),
                       c=C_RK, s=200, zorder=8, edgecolors="#5D4037", lw=1.5, marker="*")

    uk = sum(r["duljina"] for r in rezultati if r.get("duljina"))
    buf_str = f"  |  +{buffer_pct:.1f}% = {uk*(1+buffer_pct/100):,.1f}" if buffer_pct > 0 else ""
    if highlighted and not highlighted.get("greska"):
        naslov = f"{highlighted['label']}  →  {highlighted['duljina']:,.1f} jed."
        nc = C_HL_INNER
    else:
        naslov = f"{mode}  |  Osnova: {uk:,.1f} jed.{buf_str}  |  Čvorovi: {G.number_of_nodes()}"
        nc = "#CFD8DC"

    ax.set_title(naslov, fontsize=10, fontweight="bold", color=nc, pad=8)
    ax.tick_params(colors="#D0D8E4", labelsize=9)
    for spine in ax.spines.values():
        spine.set_edgecolor("#2A4A6A")
    ax.set_xlabel("X [AutoCAD jed.]", color="#90A4AE", fontsize=9)
    ax.set_ylabel("Y [AutoCAD jed.]", color="#90A4AE", fontsize=9)
    ax.grid(True, ls="--", lw=0.3, alpha=0.2, color="#1E3A5F")
    fig.tight_layout()
    return fig


# ── UI ────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title='Kabelski Graf', page_icon='⚡', layout='wide')
st.title('⚡ Kabelski Graf')
st.caption('AutoCAD CSV → topološki graf | MST analiza duljine kabela')
st.divider()

# ── Sidebar / postavke ────────────────────────────────────────────────────────
with st.sidebar:
    st.header('Postavke')
    mode      = st.radio('Mod rada', [MODE_EE, MODE_EK])
    rk_label  = st.text_input('Razvodna kutija (Circuit_Label)', value='RK-1')
    tol       = st.slider('Tolerancija spajanja (jed.)', 1.0, 1000.0, 100.0, step=1.0)
    buffer_pct = st.number_input('Dodatak na duljinu (%)', min_value=0.0, value=0.0, step=0.5)

# ── Upload CSV ────────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    kabel_file = st.file_uploader('Kabeli_Export.csv', type='csv')
with col2:
    blok_file  = st.file_uploader('Circuit_Data_Export.csv (opcionalno)', type='csv')

if not kabel_file:
    st.info('Učitaj Kabeli_Export.csv za nastavak.')
    st.stop()

# ── Analiza ───────────────────────────────────────────────────────────────────
if st.button('▶ Analiziraj', type='primary'):
    with st.spinner('Gradim graf...'):
        kabeli, hmap = ucitaj_kabele(kabel_file.read())
        blokovi = ucitaj_blokove(blok_file.read()) if blok_file else pd.DataFrame()

        if not kabeli:
            st.error('Nema valjanih kabela u CSV-u!')
            st.stop()

        G, cvorovi = izgradi_graf(kabeli, hmap, tol)
        veze = povezi_blokove(cvorovi, blokovi)

        rk_v = next((v for v in veze if v["label"] == rk_label), None)
        if not rk_v:
            dostupni = sorted({v["label"] for v in veze})
            st.error(f'RK label **{rk_label}** nije pronađen.\n\nDostupni labeli: {", ".join(dostupni)}')
            st.stop()

        izvor_idx = rk_v["cvor_idx"]

        if "EE" in mode:
            rezultati, edge_usage = analiziraj_ee(G, cvorovi, veze, rk_label)
        else:
            rezultati, edge_usage = analiziraj_ek(G, cvorovi, veze, rk_label)

        st.session_state.update({
            'kg_G': G, 'kg_cvorovi': cvorovi, 'kg_kabeli': kabeli,
            'kg_blokovi': blokovi, 'kg_veze': veze, 'kg_rezultati': rezultati,
            'kg_edge_usage': edge_usage, 'kg_izvor_idx': izvor_idx,
            'kg_rk': rk_label, 'kg_mode': mode, 'kg_buffer': buffer_pct,
        })
        st.rerun()

# ── Prikaz rezultata ──────────────────────────────────────────────────────────
if 'kg_rezultati' not in st.session_state:
    st.stop()

rezultati  = st.session_state.kg_rezultati
G          = st.session_state.kg_G
cvorovi    = st.session_state.kg_cvorovi
kabeli     = st.session_state.kg_kabeli
blokovi    = st.session_state.kg_blokovi
veze       = st.session_state.kg_veze
edge_usage = st.session_state.kg_edge_usage
izvor_idx  = st.session_state.kg_izvor_idx
rk_lbl     = st.session_state.kg_rk
s_mode     = st.session_state.kg_mode
s_buffer   = st.session_state.kg_buffer

# Metrike
valjani = [r for r in rezultati if r.get("duljina")]
uk_osnova = sum(r["duljina"] for r in valjani)
uk_buf    = uk_osnova * (1 + s_buffer / 100)
n_err     = sum(1 for r in rezultati if r.get("greska"))
n_komp    = nx.number_connected_components(G)

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric('Kabela', len(kabeli))
m2.metric('Čvorova grafa', G.number_of_nodes())
m3.metric('Krugova/blokova', len(rezultati))
m4.metric('Ukupno (osnova)', f'{uk_osnova:,.1f} jed.')
m5.metric('S dodatkom', f'{uk_buf:,.1f} jed.' if s_buffer > 0 else '—')

if n_komp > 1:
    st.warning(f'Graf ima **{n_komp} nepovezanih komponenti** (otoka)! Povećaj toleranciju.')
if n_err:
    st.warning(f'**{n_err}** krugova/blokova bez puta u grafu.')

st.divider()

# Graf + highlight
col_graf, col_lista = st.columns([2, 1])

with col_lista:
    st.subheader('Strujni krugovi / Blokovi')
    highlight_options = ['— Prikaži sve —'] + [r["label"] for r in rezultati]
    sel = st.selectbox('Highlight strujni krug:', highlight_options)
    highlighted = next((r for r in rezultati if r["label"] == sel), None)

    df_res = pd.DataFrame([{
        'Oznaka': r['label'],
        'Duljina (jed.)': f'{r["duljina"]:,.1f}' if r.get('duljina') else 'GREŠKA',
        'Greška': r.get('greska', ''),
    } for r in rezultati])
    st.dataframe(df_res, use_container_width=True, hide_index=True, height=400)

    # Export CSV
    csv_buf = io.StringIO()
    writer = csv.writer(csv_buf, delimiter=';')
    writer.writerow(['Oznaka', 'Tip_Instalacije', 'Duljina_Kabela'])
    for r in rezultati:
        d = r.get('duljina')
        writer.writerow([r['label'], r['tip'], f'{d:.2f}' if d else 'GREŠKA'])
    writer.writerow(['UKUPNO', '', f'{uk_osnova:.2f}'])
    st.download_button('⬇ Export CSV', data=csv_buf.getvalue(),
                       file_name='Kabeli_Export_rezultati.csv', mime='text/csv')

with col_graf:
    with st.spinner('Crtam graf...'):
        fig = nacrtaj(G, cvorovi, kabeli, blokovi, veze, rezultati,
                      edge_usage, izvor_idx, rk_lbl, s_mode,
                      highlighted=highlighted, buffer_pct=s_buffer)
        st.pyplot(fig, use_container_width=True)
        plt.close(fig)
