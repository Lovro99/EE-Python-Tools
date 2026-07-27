# Plan: uračunavanje kabela za sklopke rasvjete u Kabelski graf

Status: **prijedlog, prije implementacije.** Odnosi se na
`crtanjekabel.py` (v3.4) i `AutoLisp/ExportCSVdata.lsp` (v3.1).

---

## 1. Problem

Kod zbrajanja kabela za rasvjetu trenutni model ne zna za sklopke.
Sklopka nije trošilo — ona je prekid u fazi, sjedi na slijepom ogranku i
traži drugačiji kabel od napojnog. Danas se to nigdje ne modelira.

## 2. Zašto sadašnji model to ne može

Šest konkretnih razloga, svaki traži svoju izmjenu:

**2.1 Sklopka bi postala običan terminal u MST-u.**
`analiziraj_ee` (linija 504) uzima *sve* blokove istog `Circuit_Label` kao
terminale jednog Steiner MST-a. Da sklopke uđu u CSV takve kakve jesu,
MST bi ih tretirao kao trošila i lanac bi mogao ići
`svjetlo → sklopka → svjetlo`. Fizički to ne postoji: kabel ne prolazi
kroz sklopku i nastavlja dalje s istim žilama.

**2.2 Izmjenična i križna traže vezu koju MST nikad neće napraviti.**
Spoj `SW1 ↔ SW2` (par vodiča, 4×1,5) je *zahtjev*, a ne optimizacija. MST
minimizira ukupnu duljinu i spojit će svaku sklopku zasebno na najbližu
točku trase. Ta veza se mora dodati eksplicitno, izvan MST-a.

**2.3 Rezultat je jedan broj po krugu, bez tipa kabela.**
`exportiraj_csv` (linija 685) piše `Duljina_Kabela` kao jednu vrijednost.
Za troškovnik trebaju **metri po tipu kabela** — 3×1,5 i 4×1,5 se kupuju
odvojeno.

**2.4 Dedup bridova postaje netočan.**
Danas je `trasa` = unija *jedinstvenih* bridova MST putanja (linije
573–587). To je ispravno dok je krug jedan lančani kabel — zajedničkom
dionicom kabel fizički prolazi jednom. Čim se doda ogranak do sklopke,
taj ogranak dijeli koridor s napojnim vodom, a to su **dva odvojena
kabela u istoj trasi**. Ne smiju se dedupirati. Dedup mora prijeći s
"po krugu" na **"po logičkom kabelu"** — unutar jednog kabela da, između
različitih kabela nikad.

**2.5 Vertikale su računate samo za trošila.**
`vert = v_rk + (2·n − 1) · v_uredaj` (linija 569) pretpostavlja da su svi
uređaji na istoj visini. Sklopka je na ~110 cm, svjetiljka na stropu —
to je posve druga vertikala. Kod razvoda spuštenim stropom svaki spust do
sklopke je ~1,7 m, a izmjenična se penje i spušta dvaput. Na desetak
sklopki to su lako 30+ m koje sada nedostaju.

**2.6 Sklopke uopće nisu u CSV-u.**
`KBL:export-blokovi` (`ExportCSVdata.lsp:301`) uzima **samo** blokove koji
imaju atribut `CIRCUIT_LABEL`. Blokovi sklopki nemaju atribute, pa ih
export preskače. Bez toga nema ni koordinata ni imena — nema se s čim
računati.

## 3. Dodatno ograničenje: imena blokova nisu poznata repozitoriju

Pretraga oba repozitorija: **ne postoji nijedan blok zidne sklopke ni
svjetiljke.** Pojmovi "sklopka"/"prekidač" u kodu znače isključivo
zaštitnu opremu u ormaru:

| Blok | Značenje | Nije |
|---|---|---|
| `FID-sklopka` | fidovka / RCD u ormaru | zidna sklopka |
| `PREKIDAC` | minijaturni zaštitni prekidač (MCB) | zidni prekidač |
| `RASTALNI_OSIGURAC` | rastalni rastavljač | — |
| `Oznaka_SK` | *generička* oznaka trošila na tlocrtu | ne razlikuje tip trošila |

Imena blokova rasvjete žive u vanjskoj DWG biblioteci (spomenutoj u
`AutoLisp/PLAN_BlokBatch.md`) koja nije dio ovih repozitorija.

**Posljedica: imena blokova se ne smiju hardkodirati.** Mapiranje
`ime bloka → uloga / tip sklopke` mora biti konfigurabilno, a program ga
mora naučiti iz samog crteža.

Također: nigdje u kodu ne postoji parsiranje zapisa `3x1,5` — `TIP_KABELA`
se svugdje tretira kao neproziran string. Broj žila je novi koncept.

## 4. Donesene odluke

| Pitanje | Odluka |
|---|---|
| Veza sklopka → svjetiljke | Hibrid: eksplicitni override ako postoji, inače automatski po blizini + popis upozorenja |
| Broj žila | Klasično: isključna 3×1,5 · serijska 4×1,5 · izmjenična 3×1,5 dovod + 4×1,5 između para · križna 4×1,5 obostrano |
| Topologija | Slijepi ogranak iz najbliže točke trase kruga; MST ide samo kroz RK i svjetiljke |
| Podaci | Sklopke nemaju atribute — treba proširiti LISP export |

### 4.1 Korekcija hibridnog pristupa

Hibrid je izabran uz pretpostavku atributa `GRUPA` na bloku. Budući da
sklopke **nemaju nikakve atribute**, atributna grana hibrida trenutno ne
postoji — sve bi palo na automatiku. Dodavanje atributa traži izmjenu
definicija blokova u vanjskoj biblioteci (ATTDEF), što je zaseban i
neugodan zahvat.

Prijedlog koji to zaobilazi: **override po `Handle`-u.** `Handle` je već u
CSV-u (`ExportCSVdata.lsp:305`), stabilan je unutar jednog DWG-a i ništa
ne traži od crteža. Ručne ispravke se spremaju u projektni JSON pokraj
DWG-a i preživljavaju ponovni export.

Tako hibrid dobiva obje grane bez diranja blokova:

1. `Handle` u override datoteci → koristi to
2. inače → automatski po blizini, uz upozorenje

Atributi (`GRUPA`, `TIP_SKLOPKE`) ostaju kao kasnija nadogradnja ako se
biblioteka blokova ionako bude dirala — tada veza preživljava i kopiranje
među crtežima, što override po `Handle`-u ne može.

---

## 5. Plan izvedbe

### Faza 0 — LISP: dovesti sklopke u CSV

`ExportCSVdata.lsp`, `KBL:export-blokovi`:

- Uz postojeći kriterij (`ima CIRCUIT_LABEL`) prihvati i blokove **bez
  atributa** čije `EffectiveName` odgovara korisnički zadanoj listi
  uzoraka (wildcard, npr. `*SKLOP*,*PREKID*,*SW*`). Uzorak se pamti u
  postojećoj `%APPDATA%` datoteci, kao `*KBL-DEFAULT-LAYER*` sada.
- Alternativa bez ikakvog uzorka: pusti da korisnik u koraku [2/2] doda
  sklopke u istu selekciju — filter `(0 . "INSERT")` bez `(66 . 1)`.
- Novi stupci u `Circuit_Data_Export.csv`: `Uloga`, `Tip_Sklopke`, `Grupa`
  (prazni kad se ne znaju). Postojeći stupci ostaju na istom mjestu —
  `ucitaj_blokove` čita `dtype=str` i tolerira nove stupce, pa su stari
  CSV-i i dalje ispravni.

Registracija naredbi ostaje ista (nema nove `c:` komande), pa
`ACADDOC.lsp` / `ACADLT.lsp` ne treba dirati.

### Faza 1 — Python: klasifikacija po imenu bloka

Nova konfiguracija uz `crtanjekabel.py` (JSON, npr. `sklopke_config.json`):

```
ime bloka (regex/wildcard) → uloga: RK | SVJETILJKA | SKLOPKA
                           → tip:   ISKLJUCNA | SERIJSKA | IZMJENICNA | KRIZNA
```

Zadani uzorci pokrivaju uobičajena hrvatska imena, ali **ključni je korak
učenje iz crteža**: nakon učitavanja CSV-a GUI izlista sve različite
`Block_Name` vrijednosti koje nisu prepoznate i traži da im se jednom
dodijeli uloga. Mapiranje se sprema i sljedeći put je crtež prepoznat sam.
Time nijedno ime bloka ne ulazi u kod.

Tablica žila (iz odluke 4) također ide u konfiguraciju, ne u kod:

| Tip sklopke | Dovod | Veza među sklopkama |
|---|---|---|
| Isključna | 3×1,5 | — |
| Serijska | 4×1,5 | — |
| Izmjenična | 3×1,5 | 4×1,5 |
| Križna | — | 4×1,5 (obostrano) |

### Faza 2 — Python: grupiranje sklopki

Sklopke nemaju `Circuit_Label`, pa se **i krug i grupa** izvode iz istog
koraka — pripadnosti najbližoj svjetiljci:

1. Ako `Handle` postoji u override datoteci → uzmi zadanu grupu.
2. Inače: nađi najbližu svjetiljku (po duljini puta u grafu, ne zračno) i
   preuzmi njezin `Circuit_Label`; ta svjetiljka definira grupu.
3. Uparivanje izmjeničnih: unutar grupe/kruga, dvije izmjenične koje su
   najbliže jedna drugoj po grafu čine par. Križne koje pripadaju istoj
   grupi umeću se u lanac između njih, poredane po udaljenosti od dovoda.
4. Sve što je riješeno automatikom ide u popis upozorenja u GUI-ju, s
   mogućnošću da se klikom pretvori u override.

Rubni slučajevi koji moraju dati jasno upozorenje, a ne tihu krivu brojku:
grupa s jednom izmjeničnom (nepotpun par), grupa s više od dvije,
križna bez para izmjeničnih, sklopka bez ijedne svjetiljke u dosegu.

### Faza 3 — Python: novi proračun

`analiziraj_ee` se razdvaja na dva sloja.

**Sloj A — trasa (nepromijenjeno, samo suženi terminali).**
Steiner MST nad `{RK} ∪ {svjetiljke}`. Sklopke se **izbacuju** iz skupa
terminala. Dedup unije bridova ostaje — to je i dalje jedan lančani kabel.

**Sloj B — logički kabeli sklopki (novo).**
Za svaku grupu se generira lista logičkih kabela, svaki sa svojim tipom:

- **dovod**: najbliža točka trase → SW1 (ili → sklopka, kod isključne i
  serijske)
- **veza**: SW1 → (križne po redu) → SW2, svaka dionica 4×1,5
- **povrat** (samo izmjenična/križna): SW2 → svjetiljka grupe, 3×1,5

Duljina svakog logičkog kabela = najkraći put u grafu `G`, plus `snap_d`
na oba kraja, plus vertikale (Faza 5).

**Zbrajanje.** Umjesto jedne `duljina` po krugu, rezultat nosi
`{tip_kabela: duljina}`. Dedup se radi **unutar** logičkog kabela, nikad
između njih — dva kabela u istom koridoru su dva kabela.

### Faza 4 — Vertikale

Novi parametar **visina sklopke** (zadano 110 cm) uz postojeće u GUI-ju
(`crtanjekabel.py:1163–1165`). `izracunaj_v` dobiva treći povratni član
`v_sklopka`:

- razvod po podu: `v_sklopka = h_sklopka`
- spušteni strop: `v_sklopka = h_etaza − h_sklopka`

Primjena: dovod = 1× `v_sklopka`; veza SW↔SW = 2× `v_sklopka` (gore pa
dolje), osim ako se ne uvede opcija "veza se vodi u zidu" gdje otpada.

### Faza 5 — Izlaz

- **CSV**: redak po krugu, stupci po tipu kabela (`3×1,5`, `4×1,5`, …) +
  ukupno. Rekapitulacija po tipu na dnu — to je ono što ide u troškovnik.
- **GUI**: u listi krugova razlomak po tipu kabela; upozorenja iz Faze 2 u
  postojećem info panelu.
- **Graf**: sklopke drugim simbolom od trošila, veze SW↔SW posebnom bojom
  (dodati uz `C_BLOK` / `C_RK` u paleti, linije 66–78).

---

## 6. Redoslijed i rizik

| Faza | Repozitorij | Rizik |
|---|---|---|
| 0 — export sklopki | AutoLisp | nizak, aditivno |
| 1 — klasifikacija | EE-Python-Tools | nizak, nova datoteka |
| 2 — grupiranje | EE-Python-Tools | **visok** — heuristika, treba provjera na stvarnom projektu |
| 3 — proračun | EE-Python-Tools | srednji, dira postojeći `analiziraj_ee` |
| 4 — vertikale | EE-Python-Tools | nizak |
| 5 — izlaz | EE-Python-Tools | nizak |

Faza 2 je jedina koja može tiho dati krivi rezultat. Zato: svako
automatsko pripisivanje mora biti vidljivo u izvještaju, a ne
pretpostavljeno točno.

## 7. Provjera

Nema automatskih testova ni na jednoj strani (AutoLISP traži AutoCAD).
Predlaže se ručna provjera na jednom stvarnom projektu:

1. Krug s 3 svjetiljke i jednom isključnom sklopkom — ručno izmjeriti i
   usporediti.
2. Hodnik s izmjeničnim parom — provjeriti da veza SW↔SW postoji i da je
   4×1,5.
3. Slučaj s križnom — provjeriti redoslijed u lancu.
4. Usporediti ukupne metre prije i poslije: razlika mora biti objašnjiva
   zbrojem ogranaka i vertikala sklopki, ne "otprilike".
