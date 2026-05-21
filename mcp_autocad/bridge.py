"""
AutoCAD COM bridge — spaja Python MCP server s pokrenutim AutoCAD-om.
Koristi pywin32 za COM vezu i File IPC za čitanje rezultata LISP izraza.
"""
import os
import time
import tempfile
import win32com.client

RESULT_FILE = os.path.join(tempfile.gettempdir(), "mcp_autocad_result.txt")
TIMEOUT = 15  # sekundi za ne-interaktivni LISP


def get_autocad():
    try:
        return win32com.client.GetActiveObject("AutoCAD.Application")
    except Exception:
        raise RuntimeError(
            "AutoCAD nije pokrenut ili nema otvorenog crteža. "
            "Pokrenite AutoCAD i otvorite DWG datoteku."
        )


def execute_lisp(code: str) -> str:
    """
    Izvrši LISP izraz, vrati rezultat kao string.
    Rezultat se prenosi preko privremene datoteke (File IPC).
    Timeout: 15s — interaktivne naredbe čekaju korisnikov unos u AutoCAD-u.
    """
    acad = get_autocad()
    doc = acad.ActiveDocument

    if os.path.exists(RESULT_FILE):
        os.remove(RESULT_FILE)

    rp = RESULT_FILE.replace("\\", "/")

    # Wrap: izvrši kod, spremi rezultat u datoteku
    wrapped = (
        f'(progn'
        f' (setq *mcp-res* (progn {code}))'
        f' (setq *mcp-f* (open "{rp}" "w"))'
        f' (write-line (vl-prin1-to-string *mcp-res*) *mcp-f*)'
        f' (close *mcp-f*)'
        f' *mcp-res*'
        f') '
    )
    doc.SendCommand(wrapped + "\n")

    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        if os.path.exists(RESULT_FILE):
            time.sleep(0.15)  # pričekaj da LISP završi pisanje
            try:
                with open(RESULT_FILE, "r", encoding="utf-8", errors="replace") as f:
                    result = f.read().strip()
                try:
                    os.remove(RESULT_FILE)
                except OSError:
                    pass
                return result if result else "nil"
            except OSError:
                pass
        time.sleep(0.2)

    return (
        "timeout (15s) — AutoCAD možda čeka korisnički unos. "
        "Pogledaj AutoCAD prozor i završi interakciju."
    )


def send_command(cmd: str) -> None:
    """Pošalji AutoCAD naredbu (kao tipkanje u command line), bez čekanja na rezultat."""
    acad = get_autocad()
    acad.ActiveDocument.SendCommand(cmd + "\n")


def get_drawing_info() -> dict:
    """Vrati osnovne podatke o aktivnom crtežu putem COM API-ja (bez LISP-a)."""
    acad = get_autocad()
    doc = acad.ActiveDocument
    return {
        "ime": doc.Name,
        "putanja": doc.FullName,
        "spremljeno": bool(doc.Saved),
        "aktivni_layout": doc.ActiveLayout.Name,
        "broj_layouta": doc.Layouts.Count - 1,  # ne broji Model space
    }


def list_layouts() -> list:
    """Vrati sortirani popis layouta (bez Model spacea) putem COM API-ja."""
    acad = get_autocad()
    doc = acad.ActiveDocument
    result = []
    for i in range(doc.Layouts.Count):
        layout = doc.Layouts.Item(i)
        if layout.Name.lower() != "model":
            result.append(layout.Name)
    return sorted(result)
