"""
Excel PDF Placer – postavi podatke iz Excela na točne pozicije u PDF-u.
"""

import streamlit as st

st.set_page_config(page_title='Excel PDF Placer', page_icon='📌', layout='wide')

st.title('📌 Excel PDF Placer')
st.caption('Postavi podatke iz Excela na točne pozicije u PDF predlošku')
st.divider()

st.info('🚧 Ovaj alat je u pripremi i bit će dostupan uskoro.')

with st.expander('Što će ovaj alat raditi?'):
    st.markdown('''
- Učitaj Excel s podacima i PDF predložak
- Vizualno označi gdje idu koji podaci (klik na PDF)
- Alat spremi pozicije i automatski ispunjava buduće PDF-ove
- Podrška za više setova lokacija (Zahtjev 1.2.1, 1.6.1...)
''')
