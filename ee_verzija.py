"""
Verzija alata u naslovu prozora
===============================
Launcher (EE Alati) pri pokretanju alata postavi varijablu okoline
EE_VERZIJA, npr. "v3.4 · master · 943ce9a" ili "v3.5 · TEST claude/x · ab12cd3".
Alat je samo doda u naslov prozora:

    from ee_verzija import naslov
    root.title(naslov("Sync Properties"))

Kad se alat pokrene bez launchera, naslov ostaje nepromijenjen.
"""

import os


def verzija():
    """Tekst verzije koji je postavio launcher, ili '' ako ga nema."""
    return os.environ.get("EE_VERZIJA", "").strip()


def naslov(ime):
    v = verzija()
    return f"{ime}   [{v}]" if v else ime
