# EE-Python-Tools — upute za Claude

Python alati za elektroprojektiranje (AutoCAD, Excel, Word, PDF). Korisnik
komunicira na hrvatskom; poruke, komentari i UI tekst su na hrvatskom.

## Kako se alati pokreću i verzioniraju

- Jedini ulaz je launcher **EE Alati** (`launcher.py` + `tools.json`).
  NE raditi prečace ni `.bat` po alatu (to je namjerno uklonjeno).
- Korisnik testira promjene tako da u launcheru odabere granu (izbornik
  „Verzija”), pa nakon merge-a klikne „Ažuriraj”. Stabilna verzija za kolege
  = `origin/master`, objavljuje se preko `deploy.ps1`.
- Glavna grana je `master`.

## Pravila kod promjena

- **Svaka promjena alata → povećaj njegov `"verzija"` u `tools.json`** u
  istom commitu (popravak/manja značajka: 1.2 → 1.3; veliki preradak: 1.x → 2.0).
- Novi alat → novi unos u `tools.json` (s `"verzija": "1.0"`), a naslov GUI
  prozora preko `from ee_verzija import naslov` → `root.title(naslov("Ime"))`.
- Novi vanjski paket → dodaj u `requirements.txt` (launcher ga sam
  doinstalira korisniku).
- Poruka commita kratko kaže što se promijenilo za korisnika — prikazuje se u
  launcheru kao „zadnja promjena” alata (npr. `Sync DWG Fast: backup prije upisa`).
- `.ps1` datoteke pisati samo u ASCII (Windows PowerShell 5.1 bez BOM-a krivo
  čita UTF-8).
- Alati se pokreću na Windowsima (pywin32/COM, AutoCAD, Word); u cloud
  sesiji se ne mogu stvarno isprobati — reci korisniku što treba provjeriti.
