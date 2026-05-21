"""
Pretraga Word – pretraži sadržaj svih Word dokumenata u mapi.
"""

import streamlit as st

st.set_page_config(page_title='Pretraga Word', page_icon='🔍', layout='wide')

st.title('🔍 Pretraga Word dokumenata')
st.caption('Pretraži sadržaj svih .docx datoteka u odabranoj mapi')
st.divider()

st.info('🚧 Ovaj alat je u pripremi i bit će dostupan uskoro.')

with st.expander('Što će ovaj alat raditi?'):
    st.markdown('''
- Indeksira sve `.docx` i `.docm` datoteke u odabranoj mapi
- Brza pretraga po ključnoj riječi
- Prikazuje kontekst (odlomak) u kojem je pronađena riječ
- Klik otvara dokument
''')
