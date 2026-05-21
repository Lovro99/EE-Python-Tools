"""
Glavni hub – AutoLisp alati.
Pokretanje: streamlit run web_app.py --server.address 0.0.0.0 --server.port 8501
"""

import streamlit as st

st.set_page_config(
    page_title='AutoLisp Alati',
    page_icon='⚡',
    layout='wide',
    initial_sidebar_state='expanded',
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown('''
<style>
/* Font */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: "Inter", sans-serif; }

/* Pozadina */
.stApp { background: #f8f9fa; }

/* Sakrij default Streamlit header */
header[data-testid="stHeader"] { background: transparent; }

/* Hero sekcija */
.hero {
    text-align: center;
    padding: 3.5rem 1rem 2rem;
}
.hero h1 {
    font-size: 2.8rem;
    font-weight: 700;
    color: #1a1a2e;
    margin-bottom: 0.4rem;
    letter-spacing: -0.5px;
}
.hero p {
    font-size: 1.1rem;
    color: #6b7280;
    margin-top: 0;
}

/* Search bar dekoracija */
.search-bar {
    display: flex;
    justify-content: center;
    margin: 1.5rem auto 2.5rem;
}
.search-fake {
    display: flex;
    align-items: center;
    gap: 10px;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 50px;
    padding: 0.65rem 1.4rem;
    box-shadow: 0 1px 6px rgba(0,0,0,0.08);
    width: 100%;
    max-width: 520px;
    color: #9ca3af;
    font-size: 0.95rem;
    cursor: default;
}

/* Kartice */
.card {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    padding: 1.5rem 1.4rem;
    height: 180px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    transition: box-shadow 0.2s, transform 0.2s;
    cursor: pointer;
    text-decoration: none;
}
.card:hover {
    box-shadow: 0 4px 20px rgba(0,0,0,0.10);
    transform: translateY(-3px);
}
.card-icon { font-size: 2rem; margin-bottom: 0.4rem; }
.card-title { font-size: 1rem; font-weight: 600; color: #111827; margin: 0; }
.card-desc  { font-size: 0.82rem; color: #6b7280; margin: 0.2rem 0 0; line-height: 1.4; }
.card-badge {
    display: inline-block;
    font-size: 0.7rem;
    font-weight: 600;
    padding: 2px 10px;
    border-radius: 20px;
    margin-top: 0.6rem;
    width: fit-content;
}
.badge-live    { background: #dcfce7; color: #16a34a; }
.badge-soon    { background: #f3f4f6; color: #9ca3af; }

/* Sekcija naslov */
.section-label {
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #9ca3af;
    margin: 2rem 0 0.8rem;
}

/* Footer */
.footer {
    text-align: center;
    color: #d1d5db;
    font-size: 0.78rem;
    padding: 3rem 0 1.5rem;
}
</style>
''', unsafe_allow_html=True)

# ── Hero ──────────────────────────────────────────────────────────────────────
st.markdown('''
<div class="hero">
    <h1>⚡ AutoLisp Alati</h1>
    <p>Svi interni alati na jednom mjestu</p>
</div>
<div class="search-bar">
    <div class="search-fake">
        <span>🔍</span> Odaberi alat iz izbornika lijevo...
    </div>
</div>
''', unsafe_allow_html=True)

# ── Dostupni alati ────────────────────────────────────────────────────────────
st.markdown('<div class="section-label">Dostupni alati</div>', unsafe_allow_html=True)

cols = st.columns(4)

LIVE = [
    ('🖨️', 'Print Organizer', 'Razvrstaj PDF stranice na kopirka i ploter', '1_Print_Organizer'),
]

for i, (icon, title, desc, _) in enumerate(LIVE):
    with cols[i % 4]:
        st.markdown(f'''
        <div class="card">
            <div>
                <div class="card-icon">{icon}</div>
                <p class="card-title">{title}</p>
                <p class="card-desc">{desc}</p>
            </div>
            <span class="card-badge badge-live">● Dostupno</span>
        </div>
        ''', unsafe_allow_html=True)

# ── U pripremi ────────────────────────────────────────────────────────────────
st.markdown('<div class="section-label">U pripremi</div>', unsafe_allow_html=True)

SOON = [
    ('📄', 'Excel → Word',        'Popuni Word predložak podacima iz Excela'),
    ('📋', 'HEPA Form Filler',    'Ispuni HEPA PDF obrasce iz Excel dokumentacije'),
    ('📊', 'Scrape Excel',        'Izvuci ključne podatke iz Excel projektnih datoteka'),
    ('🔍', 'Pretraga Word',       'Pretraži sadržaj svih Word dokumenata u mapi'),
    ('⚡', 'Duljina Kabela',      'Izračun i vizualizacija kabela u razvodnoj mreži'),
    ('📌', 'Excel PDF Placer',    'Postavi Excel podatke na točne pozicije u PDF-u'),
]

rows = [SOON[i:i+4] for i in range(0, len(SOON), 4)]
for row in rows:
    cols = st.columns(4)
    for i, (icon, title, desc) in enumerate(row):
        with cols[i]:
            st.markdown(f'''
            <div class="card" style="cursor:default; opacity:0.75;">
                <div>
                    <div class="card-icon">{icon}</div>
                    <p class="card-title">{title}</p>
                    <p class="card-desc">{desc}</p>
                </div>
                <span class="card-badge badge-soon">Uskoro</span>
            </div>
            ''', unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown('<div class="footer">AutoLisp Alati · interni sustav</div>', unsafe_allow_html=True)
