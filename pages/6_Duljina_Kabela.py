"""
Duljina kabela – izračun duljine kabela u razvodnoj mreži.
"""

import streamlit as st

st.set_page_config(page_title='Duljina Kabela', page_icon='⚡', layout='wide')

st.title('⚡ Duljina Kabela')
st.caption('Izračun i vizualizacija duljine kabela u razvodnoj mreži')
st.divider()

st.info('🚧 Ovaj alat je u pripremi i bit će dostupan uskoro.')

with st.expander('Što će ovaj alat raditi?'):
    st.markdown('''
- Unesi raspored razvodnih ormara i potrošača
- Alat izračunava optimalnu duljinu kabela
- Vizualizacija mreže s grafom
- Export rezultata u Excel
''')
