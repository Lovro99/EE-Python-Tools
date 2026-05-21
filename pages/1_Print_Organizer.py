"""
Print Organizer – razvrstaj PDF stranice na kopirka vs. ploter.
"""

import io
import streamlit as st

MM_TO_PT = 72.0 / 25.4
TOLERANCE_PT = 14

STANDARD_SIZES = {
    'A4': (210, 297),
    'A3': (297, 420),
    'A2': (420, 594),
    'A1': (594, 841),
    'A0': (841, 1189),
}
KOPIRKA_FORMATS = {'A4', 'A3'}


def detect_paper_size(width_pt, height_pt):
    w, h = min(width_pt, height_pt), max(width_pt, height_pt)
    for name, (pw_mm, ph_mm) in STANDARD_SIZES.items():
        pw, ph = pw_mm * MM_TO_PT, ph_mm * MM_TO_PT
        if abs(w - pw) <= TOLERANCE_PT and abs(h - ph) <= TOLERANCE_PT:
            return name, 'Portret' if width_pt <= height_pt else 'Pejzaž'
    return f'Nestandardni ({width_pt/MM_TO_PT:.0f}×{height_pt/MM_TO_PT:.0f} mm)', 'Nestandardni'


def pages_to_range_string(pages):
    if not pages:
        return ''
    pages = sorted(set(pages))
    ranges, start, end = [], pages[0], pages[0]
    for p in pages[1:]:
        if p == end + 1:
            end = p
        else:
            ranges.append(str(start) if start == end else f'{start}-{end}')
            start = end = p
    ranges.append(str(start) if start == end else f'{start}-{end}')
    return ', '.join(ranges)


def analyze_pdf(file_bytes):
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            st.error('Nedostaje pypdf. Pokreni: pip install pypdf')
            return []
    reader = PdfReader(io.BytesIO(file_bytes))
    return [{
        'page': i + 1,
        'size': (s := detect_paper_size(float(p.mediabox.width), float(p.mediabox.height)))[0],
        'orientation': s[1],
        'kopirka': detect_paper_size(float(p.mediabox.width), float(p.mediabox.height))[0] in KOPIRKA_FORMATS,
    } for i, p in enumerate(reader.pages)]


# ── UI ────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title='Print Organizer', page_icon='🖨️', layout='wide')

st.title('🖨️ Print Organizer')
st.caption('Razvrstaj stranice projekta – kopirka (A4/A3) vs. ploter (A2–A0)')
st.divider()

uploaded = st.file_uploader('Učitaj PDF datoteku', type='pdf')

if uploaded is None:
    st.info('Učitaj PDF datoteku za analizu.')
    st.stop()

with st.spinner('Analiziram PDF...'):
    pages_info = analyze_pdf(uploaded.read())

if not pages_info:
    st.stop()

kopirka = [p for p in pages_info if p['kopirka']]
ploter  = [p for p in pages_info if not p['kopirka']]

col1, col2, col3 = st.columns(3)
col1.metric('Ukupno stranica', len(pages_info))
col2.metric('Kopirka (A4/A3)', len(kopirka))
col3.metric('Ploter (A2–A0+)', len(ploter))

st.divider()

k_range = pages_to_range_string([p['page'] for p in kopirka]) or '(nema)'
p_range = pages_to_range_string([p['page'] for p in ploter])  or '(nema)'

c1, c2 = st.columns(2)
with c1:
    st.markdown('**Kopirka – stranice:**')
    st.code(k_range)
with c2:
    st.markdown('**Ploter – stranice:**')
    st.code(p_range)

st.divider()
st.subheader('Popis stranica')

import pandas as pd
df = pd.DataFrame([{
    'Stranica': p['page'],
    'Format': p['size'],
    'Orijentacija': p['orientation'],
    'Uređaj': 'Kopirka' if p['kopirka'] else 'Ploter',
} for p in pages_info])

st.dataframe(df, use_container_width=True, hide_index=True)
