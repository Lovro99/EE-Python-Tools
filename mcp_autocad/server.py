"""
AutoCAD MCP Server
Pokreni: python server.py
Registriraj u Claude Code settings.json pod mcpServers.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from mcp.server.fastmcp import FastMCP
from bridge import (
    execute_lisp as _exec_lisp,
    send_command as _send_cmd,
    get_drawing_info as _drawing_info,
    list_layouts as _list_layouts,
)

mcp = FastMCP(
    "autocad",
    instructions="""
AutoCAD MCP server za projekt AutoLisp.
Koristi execute_lisp za pokretanje bilo kojeg AutoLISP koda u aktivnom crtežu.

DOSTUPNE NAREDBE (definirane u ACADDOC.lsp):
  Naredba          Opis
  -------          ----
  (c:CBN)          Numerira CB (circuit breaker) tekstove — pita za tip i početni broj
  (c:sumPower)     Zbraja snage odabranih tekstova, ispisuje ukupno i korigiranu snagu
  (c:ele)          Eksportira layoute u Excel (ExportLayoutsToExcel)
  (c:AutoWireAttributeUpdate)  VDS — ažurira atribute žica po BrojPetlje i baseValue
  (c:panelRenum)   Renumerira panele
  (c:setCBelements) Postavi elemente CB-a
  (c:CountCB)      Broji CB blokove u crtežu
  (c:MTVATT)       Modify Text/Attribute Values
  (c:VDSNUMPRO)    VDS numeriranje (pro verzija)
  (c:VDSCHECKPRO)  VDS provjera (pro verzija)
  (c:mastermind)   Mastermind alat
  (c:Cleanup)      Čišćenje crteža
  (c:MM)           Makemore
  (c:panelRenum)   Renumeracija panela
  (c:rl)           Renumber Layouts
  (c:SetLayoutTitle) Postavi naslove layouta
  (c:setLayoutOrder) Postavi redoslijed layouta
  (c:tCount2)      Broji tekstove
  (c:simplecount)  Jednostavno brojanje
  (c:NumInc)       Numerički inkrement
  (c:mtv)          Modify Text Values
  (c:t2m)          Text to MText konverzija
  (c:enb)          Extract Nested Block
  (c:TabSort)      Tab Sort
  (c:pburst)/(c:nburst) Burst blokova
  (c:Steal)        Steal svojstava
  (c:CBP)/(c:CBPR) Change Block Base Point

INTERAKTIVNE vs. AUTOMATIZIRANE NAREDBE:
- Naredbe koje koriste ssget bez argumenata ili getstring/getint ČEKAJU unos u AutoCAD-u
- Korisnik mora biti u AutoCAD prozoru za interaktivni unos
- Automatizirana upotreba: proslijedi parametre direktno u LISP kodu

PRIMJERI:
  Pitanje: "koje layoute ima ovaj crtež?"
  → list_layouts() ili execute_lisp("(layoutlist)")

  Pitanje: "pokreni CBN od broja 5"
  → execute_lisp("(progn (setq option \\"All\\") (setq starting_number 5) ...)")
  → ili samo execute_lisp("(c:CBN)") i korisnik unosi u AutoCAD-u

  Pitanje: "pronađi sve blokove čije ime počinje s CB"
  → execute_lisp("(vl-remove-if-not (lambda (x) (wcmatch (car x) \\"CB*\\")) (mapcar (lambda (e) (list (cdr (assoc 2 (entget e))))) (vl-remove-if-not (lambda (e) (= (cdr (assoc 0 (entget e))) \\"INSERT\\")) (vl-list->subrs))))")
""",
)


@mcp.tool()
def execute_lisp(code: str) -> str:
    """
    Izvrši AutoLISP izraz u aktivnom AutoCAD dokumentu i vrati rezultat.

    Primjeri ne-interaktivnog koda (rezultat odmah):
      (getvar "dwgname")                  -> ime DWG datoteke
      (getvar "dwgprefix")                -> folder crteža
      (layoutlist)                        -> lista layouta kao string
      (vl-directory-files "C:/" "*.dwg" 1) -> DWG datoteke u folderu
      (+ 1 2)                             -> 3

    Primjeri interaktivnih naredbi (korisnik završava u AutoCAD-u):
      (c:CBN)                             -> CBnumbering
      (c:sumPower)                        -> zbroj snaga
      (c:ele)                             -> export layouta u Excel
      (c:AutoWireAttributeUpdate)         -> VDS ažuriranje
      (c:panelRenum)                      -> renumeracija panela

    Timeout za ne-interaktivni kod: 15 sekundi.
    Interaktivni kod čeka dok korisnik ne završi unos u AutoCAD prozoru.
    """
    try:
        return _exec_lisp(code)
    except RuntimeError as e:
        return f"GREŠKA: {e}"
    except Exception as e:
        return f"GREŠKA ({type(e).__name__}): {e}"


@mcp.tool()
def get_drawing_info() -> dict:
    """
    Vrati informacije o trenutno aktivnom AutoCAD crtežu:
    ime datoteke, puna putanja, je li spremljeno, aktivni layout, broj layouta.
    Ne zahtijeva LISP — čita direktno putem COM API-ja.
    """
    try:
        return _drawing_info()
    except RuntimeError as e:
        return {"greška": str(e)}


@mcp.tool()
def list_layouts() -> list:
    """
    Vrati sortirani popis svih layouta u aktivnom crtežu.
    Model space je isključen. Ne zahtijeva LISP.
    """
    try:
        return _list_layouts()
    except RuntimeError as e:
        return [f"GREŠKA: {e}"]


@mcp.tool()
def send_autocad_command(command: str) -> str:
    """
    Pošalji AutoCAD naredbu kao da je korisnik tipka u command line.
    Nema povratne vrijednosti (fire-and-forget).
    Za LISP kod koristi execute_lisp.

    Primjeri: ZOOM, REGEN, QSAVE, UNDO, REDO, LAYER, ZOOM E
    """
    try:
        _send_cmd(command)
        return f"Naredba poslana: '{command}'"
    except RuntimeError as e:
        return f"GREŠKA: {e}"


if __name__ == "__main__":
    mcp.run()
