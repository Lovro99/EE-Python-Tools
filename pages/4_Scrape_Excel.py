"""
Scrape Excel – izvuci ključne podatke iz Excel projektnih datoteka.
"""

import streamlit as st

st.set_page_config(page_title='Scrape Excel', page_icon='📊', layout='wide')

st.title('📊 Scrape Excel')
st.caption('Izvuci ključne podatke iz Excel projektnih datoteka')
st.divider()

st.info('🚧 Ovaj alat je u pripremi i bit će dostupan uskoro.')

with st.expander('Što će ovaj alat raditi?'):
    st.markdown('''
- Učitaj jednu ili više Excel datoteka
- Alat automatski traži ključne podatke (proizvođač panela, model, snaga...)
- Rezultati se prikazuju u tablici
- Export u CSV ili Excel
''')
