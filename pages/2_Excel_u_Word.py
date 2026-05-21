"""
Excel u Word – automatski popuni Word predložak podacima iz Excela.
"""

import streamlit as st

st.set_page_config(page_title='Excel → Word', page_icon='📄', layout='wide')

st.title('📄 Excel → Word')
st.caption('Automatski popuni Word predložak podacima iz Excel tablice')
st.divider()

st.info('🚧 Ovaj alat je u pripremi i bit će dostupan uskoro.')

with st.expander('Što će ovaj alat raditi?'):
    st.markdown('''
- Učitaj Excel datoteku s listom **Podaci**
- Učitaj Word predložak (`.docx`)
- Alat automatski popuni sve oznake u predlošku s vrijednostima iz Excela
- Preuzmi ispunjeni Word dokument
''')
