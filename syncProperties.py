"""
syncProperties.py - Unified Excel -> Word / DWG property synchronizer

Reads key-value pairs from an Excel "Podaci" sheet (col A = name, col B = value)
and pushes them as custom properties into any number of Word and/or DWG files.

Word:  direct ZIP/XML manipulation - no Word application required (~0.5s per file
       vs ~10-15s with win32com). DOCPROPERTY fields refresh automatically when
       the document is opened in Word.

DWG:   AutoCAD COM via win32com - mirrors SetFieldsValue.lsp exactly, but driven
       from Python so no manual LSP execution is needed.
"""

import os
import re
import shutil
import threading
import time
import zipfile
from datetime import datetime

import openpyxl
import customtkinter as ctk
from tkinter import filedialog, messagebox
from lxml import etree

# ── XML constants ─────────────────────────────────────────────────────────────
_PROPS_NS = "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
_VT_NS    = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
_PKG_NS   = "http://schemas.openxmlformats.org/package/2006/relationships"
_CT_NS    = "http://schemas.openxmlformats.org/package/2006/content-types"
_FMTID    = "{D5CDD505-2E9C-101B-9397-08002B2CF9AE}"
_CUSTOM_CT    = "application/vnd.openxmlformats-officedocument.custom-properties+xml"
_CUSTOM_REL_T = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties"
)


# ── Excel ─────────────────────────────────────────────────────────────────────

def read_excel_properties(path: str, sheet: str = "Podaci") -> dict[str, str]:
    """Return {name: value} from columns A and B of the given sheet."""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[sheet]
    props: dict[str, str] = {}
    for row in ws.iter_rows(min_row=1, max_col=2, values_only=True):
        name, value = row
        if name:
            props[str(name).strip()] = str(value).strip() if value is not None else ""
    wb.close()
    return props


# ── Word (direct ZIP/XML, no Word app needed) ─────────────────────────────────

def _load_zip(path: str) -> tuple[dict[str, bytes], dict]:
    data: dict[str, bytes] = {}
    info: dict = {}
    with zipfile.ZipFile(path, "r") as zf:
        for zi in zf.infolist():
            data[zi.filename] = zf.read(zi.filename)
            info[zi.filename] = zi
    return data, info


def _save_zip(path: str, data: dict[str, bytes], info: dict):
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in data.items():
            zi = info.get(name)
            compress = zi.compress_type if zi else zipfile.ZIP_DEFLATED
            zf.writestr(name, content, compress_type=compress)


def _ensure_custom_props_wired(data: dict[str, bytes]):
    """Register docProps/custom.xml in [Content_Types].xml and _rels/.rels if absent.

    Uses string injection instead of full XML re-serialisation so that the
    original namespace declarations and attribute order in those two files are
    preserved exactly as Word wrote them.  Re-serialising with lxml changes
    namespace prefixes and quote styles in a way that causes Word to report
    the document as corrupt.
    """
    # ── [Content_Types].xml ───────────────────────────────────────────────────
    ct_key = next((k for k in data if k.lower() == "[content_types].xml"), None)
    if ct_key:
        ct_text = data[ct_key].decode("utf-8-sig")  # strip BOM if present
        if "/docprops/custom.xml" not in ct_text.lower():
            override = (
                f'<Override PartName="/docProps/custom.xml"'
                f' ContentType="{_CUSTOM_CT}"/>'
            )
            ct_text = re.sub(r'(</Types\s*>)', f'  {override}\n\\1', ct_text)
            data[ct_key] = ct_text.encode("utf-8")

    # ── _rels/.rels ───────────────────────────────────────────────────────────
    rels_key = next((k for k in data if k.lower() == "_rels/.rels"), None)
    if rels_key:
        rels_text = data[rels_key].decode("utf-8-sig")
        if _CUSTOM_REL_T not in rels_text:
            existing_ids = set(re.findall(r'Id="(rId\d+)"', rels_text, re.IGNORECASE))
            n = 1
            while f"rId{n}" in existing_ids:
                n += 1
            rel = (
                f'<Relationship Id="rId{n}"'
                f' Type="{_CUSTOM_REL_T}"'
                f' Target="docProps/custom.xml"/>'
            )
            rels_text = re.sub(r'(</Relationships\s*>)', f'  {rel}\n\\1', rels_text)
            data[rels_key] = rels_text.encode("utf-8")


def _empty_custom_xml() -> bytes:
    root = etree.Element(
        f"{{{_PROPS_NS}}}Properties", nsmap={"": _PROPS_NS, "vt": _VT_NS}
    )
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _apply_props(xml_bytes: bytes, properties: dict[str, str], log_fn=None) -> bytes:
    """Upiši properties u docProps/custom.xml.

    Uspoređuje nazive svojstava case-insensitively:
    ako Word ima 'Snaga invertera' a Excel šalje 'snaga invertera',
    ažurira se POSTOJEĆI element (ne dodaje duplikat).
    Originalnog Word naziva se ne mijenja — samo vrijednost.
    """
    root = etree.fromstring(xml_bytes)

    # Indeks postojećih: original_name -> element
    existing_els: dict[str, etree._Element] = {
        prop.get("name", ""): prop
        for prop in root.findall(f"{{{_PROPS_NS}}}property")
    }
    # Case-insensitivni indeks: lowercase_name -> original_name
    existing_lower: dict[str, str] = {k.lower(): k for k in existing_els}

    pids = [int(p.get("pid", 2)) for p in root.findall(f"{{{_PROPS_NS}}}property")]
    next_pid = max(pids, default=1) + 1  # OOXML: PID mora biti >= 2

    for name, value in properties.items():
        orig_name = existing_lower.get(name.lower())  # case-insensitive lookup
        if orig_name is not None:
            # Ažuriraj postojeći element (zadrži originalni naziv iz Worda)
            if orig_name != name:
                _msg = (f"Naziv '{name}' (Excel) ≠ '{orig_name}' (Word) — ažuriram '{orig_name}'")
                print(f"  [Word] Upozorenje: {_msg}")
                if log_fn:
                    log_fn(_msg, "warn")
            prop = existing_els[orig_name]
            vt = prop.find(f"{{{_VT_NS}}}lpwstr")
            if vt is None:
                for child in list(prop):
                    prop.remove(child)
                vt = etree.SubElement(prop, f"{{{_VT_NS}}}lpwstr")
            vt.text = value
        else:
            # Novi property — dodaj ga
            prop = etree.SubElement(root, f"{{{_PROPS_NS}}}property")
            prop.set("fmtid", _FMTID)
            prop.set("pid", str(next_pid))
            prop.set("name", name)
            vt = etree.SubElement(prop, f"{{{_VT_NS}}}lpwstr")
            vt.text = value
            next_pid += 1
            # Dodaj u lookup da ne dupliramo ako Excel sam ima duplikate
            existing_lower[name.lower()] = name
            existing_els[name] = prop

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _strip_kopija_suffix(base: str) -> str:
    """Ukloni _Nova_kopija_DD_MM_YY--HH_MM sufiks ako postoji (izbjegava lančanje kopija)."""
    return re.sub(r'_Nova_kopija_\d{2}_\d{2}_\d{2}--\d{2}_\d{2}$', '', base)


def update_word_properties(
    word_path: str, properties: dict[str, str], make_copy: bool = True, log_fn=None
) -> str:
    """
    Write custom document properties into a Word file without opening Word.

    Returns the path of the modified file (copy or in-place).
    DOCPROPERTY fields refresh automatically when the document is opened in Word.
    """
    if make_copy:
        base, ext = os.path.splitext(word_path)
        base = _strip_kopija_suffix(base)   # izbjegni lančanje: file_Nova_kopija_..._Nova_kopija_...
        ts = datetime.now().strftime("%d_%m_%y--%H_%M")
        out = f"{base}_Nova_kopija_{ts}{ext}"
        shutil.copy2(word_path, out)
    else:
        out = word_path

    data, info = _load_zip(out)

    custom_key = next((k for k in data if k.lower() == "docprops/custom.xml"), None)
    if custom_key is None:
        custom_key = "docProps/custom.xml"
        data[custom_key] = _empty_custom_xml()
        info[custom_key] = None  # new entry, no original ZipInfo
        _ensure_custom_props_wired(data)

    data[custom_key] = _apply_props(data[custom_key], properties, log_fn=log_fn)
    _save_zip(out, data, info)
    return out


# ── DWG (AutoCAD COM, mirrors SetFieldsValue.lsp) ─────────────────────────────

# HRESULT kodovi koji znače "AutoCAD je zauzet, pokušaj opet"
_COM_BUSY_CODES = {
    -2147418111,  # RPC_E_CALL_REJECTED       (0x80010001)
    -2147417846,  # RPC_E_SERVERCALL_RETRYLATER(0x8001010A)
    -2147417848,  # RPC_E_SERVER_BUSY          (0x80010008)
}
_COM_RETRIES = 8
_COM_DELAY   = 1.5   # sekundi između pokušaja po property-u


def _com_retry(fn, retries: int = _COM_RETRIES, delay: float = _COM_DELAY):
    """Pozovi fn(), ponavljaj ako AutoCAD vrati 'busy' HRESULT."""
    for i in range(retries):
        try:
            return fn()
        except Exception as exc:
            hr = getattr(exc, "hresult", None)
            is_busy = hr in _COM_BUSY_CODES or any(str(c) in str(exc) for c in _COM_BUSY_CODES)
            if is_busy and i < retries - 1:
                time.sleep(delay)
                continue
            raise


def _dwg_existing_keys(summary) -> dict[str, str]:
    """Vrati {lowercase_naziv: originalni_naziv} za sve custom properties u dokumentu.

    Case-insensitivni lookup — AutoCAD ne dopušta dvije property s istim nazivom
    bez obzira na velika/mala slova ('Snaga' i 'snaga' su duplikat za AutoCAD).
    """
    keys: dict[str, str] = {}
    try:
        n = _com_retry(lambda: summary.NumCustomInfo())
    except Exception:
        return keys
    for i in range(n):
        try:
            k, _ = _com_retry(lambda i=i: summary.GetCustomByIndex(i))
            keys[k.lower()] = k   # lowercase → originalni naziv iz DWG-a
        except Exception:
            pass
    return keys


def update_dwg_properties(dwg_path: str, properties: dict[str, str], log_fn=None):
    """
    Set SummaryInfo custom properties in a DWG file via AutoCAD COM.
    Requires AutoCAD to be installed. Equivalent to SetFieldsValue.lsp.

    Strategy:
    - Reads existing custom-property keys FIRST so we never mix up
      SetCustomByKey (key must exist) and AddCustomInfo (key must NOT exist).
    - Every COM call is wrapped in _com_retry() which waits and retries
      when AutoCAD returns RPC_E_CALL_REJECTED / SERVER_BUSY.
    - CoInitialize/CoUninitialize because this runs in a background thread.
    """
    import pythoncom
    import win32com.client as win32

    def _log(msg: str, level: str = "info"):
        print(f"  [DWG] {msg}")
        if log_fn:
            log_fn(msg, level)

    pythoncom.CoInitialize()
    try:
        try:
            acad = _com_retry(lambda: win32.GetActiveObject("AutoCAD.Application"))
            _log("Spojen na postojeću instancu AutoCAD-a.", "info")
        except Exception:
            acad = _com_retry(lambda: win32.Dispatch("AutoCAD.Application"))
            _log("Pokrenuta nova instanca AutoCAD-a.", "info")

        _log(f"Otvoram: {os.path.basename(dwg_path)}", "info")
        doc = _com_retry(lambda: acad.Documents.Open(os.path.abspath(dwg_path)))

        # Kratko čekanje — AutoCAD treba "slegnut" nakon otvaranja dokumenta
        time.sleep(1.5)

        summary = doc.SummaryInfo
        existing = _dwg_existing_keys(summary)
        _log(f"Pronađeno {len(existing)} postojećih custom properties.", "info")

        ok_n, warn_n, err_n = 0, 0, 0
        for name, value in properties.items():
            v = str(value)
            lower = name.lower()
            try:
                if lower in existing:
                    orig_key = existing[lower]
                    if orig_key != name:
                        _log(f"Naziv '{name}' (Excel) ≠ '{orig_key}' (DWG) — ažuriram '{orig_key}'", "warn")
                        warn_n += 1
                    _com_retry(lambda k=orig_key, v=v: summary.SetCustomByKey(k, v))
                else:
                    _com_retry(lambda n=name, v=v: summary.AddCustomInfo(n, v))
                    existing[lower] = name
                ok_n += 1
            except Exception as exc:
                _log(f"Ne mogu postaviti '{name}': {exc}", "error")
                err_n += 1

        _com_retry(lambda: doc.Save())
        _com_retry(lambda: doc.Close())
        _log(f"Spremljeno — {ok_n} OK, {warn_n} upozorenja, {err_n} grešaka.", "ok" if err_n == 0 else "warn")

    finally:
        pythoncom.CoUninitialize()


# ── GUI — Google Material Design ──────────────────────────────────────────────

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

# Google colour palette
_BG      = "#F8F9FA"
_CARD    = "#FFFFFF"
_BLUE    = "#1a73e8"
_BLUE_H  = "#1557b0"
_BLUE_LT = "#E8F0FE"
_RED     = "#EA4335"
_RED_H   = "#C5221F"
_TEXT    = "#202124"
_TEXT2   = "#5f6368"
_BORDER  = "#DADCE0"
_GREEN   = "#34A853"
_ORANGE  = "#F9AB00"
_FONT    = "Segoe UI"

_SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


def _card(parent, **kw) -> ctk.CTkFrame:
    return ctk.CTkFrame(
        parent, fg_color=_CARD, corner_radius=8,
        border_width=1, border_color=_BORDER, **kw,
    )


class _FileChip:
    """One file row: spinner/check/cross  •  filename  •  [copy checkbox]  •  sync  •  remove."""

    _ICONS = {
        "pending": ("—", _TEXT2,  _BLUE_LT),
        "running": ("⠋", _BLUE,   "#DBEAFE"),
        "ok":      ("✓", _GREEN,  "#D7F3E3"),
        "error":   ("✗", _RED,    "#FDECEA"),
    }

    def __init__(self, parent, path: str, on_remove, on_sync=None, show_copy_opt: bool = False):
        self.path = path
        self._spin_idx = 0
        self._status = "pending"
        self.copy_var = ctk.BooleanVar(value=True)

        self._frame = ctk.CTkFrame(parent, fg_color=_BLUE_LT, corner_radius=6)
        self._frame.pack(fill="x", pady=2, padx=2)

        # status icon
        self._icon_lbl = ctk.CTkLabel(
            self._frame, text="—", width=22, font=(_FONT, 12, "bold"), text_color=_TEXT2
        )
        self._icon_lbl.pack(side="left", padx=(8, 2), pady=4)

        # filename
        self._name_lbl = ctk.CTkLabel(
            self._frame, text=os.path.basename(path), anchor="w",
            font=(_FONT, 11), text_color=_TEXT,
        )
        self._name_lbl.pack(side="left", fill="x", expand=True, pady=4)

        # remove (pack right-to-left so order stays: copy | sync | remove)
        ctk.CTkButton(
            self._frame, text="✕", width=24, height=24, corner_radius=12,
            fg_color=_RED, hover_color=_RED_H, text_color="white",
            font=(_FONT, 10, "bold"),
            command=lambda: on_remove(self),
        ).pack(side="right", padx=(0, 6))

        # individual sync button
        if on_sync is not None:
            ctk.CTkButton(
                self._frame, text="▶", width=28, height=24, corner_radius=4,
                fg_color=_GREEN, hover_color="#2D8F46", text_color="white",
                font=(_FONT, 10, "bold"),
                command=lambda: on_sync(self.path, self.copy_var.get()),
            ).pack(side="right", padx=(0, 4))

        # copy checkbox (Word files only)
        if show_copy_opt:
            ctk.CTkCheckBox(
                self._frame, text="kopija", variable=self.copy_var,
                font=(_FONT, 10), text_color=_TEXT2,
                fg_color=_BLUE, hover_color=_BLUE_H,
                checkmark_color="white", border_color=_BORDER,
                width=16, height=16,
            ).pack(side="right", padx=(0, 8))

    def set_status(self, status: str):
        self._status = status
        icon, color, bg = self._ICONS.get(status, self._ICONS["pending"])
        self._icon_lbl.configure(text=icon, text_color=color)
        self._frame.configure(fg_color=bg)

    def tick_spinner(self):
        if self._status == "running":
            self._spin_idx = (self._spin_idx + 1) % len(_SPINNER)
            self._icon_lbl.configure(text=_SPINNER[self._spin_idx])

    def destroy(self):
        self._frame.destroy()


class _FileListFrame(ctk.CTkScrollableFrame):
    def __init__(self, master, show_copy_opt: bool = False, on_sync=None, **kw):
        super().__init__(
            master, height=80, fg_color=_CARD,
            scrollbar_button_color=_BORDER,
            scrollbar_button_hover_color=_BLUE, **kw,
        )
        self._chips: list[_FileChip] = []
        self._show_copy_opt = show_copy_opt
        self._on_sync = on_sync

    def add(self, path: str):
        if any(c.path == path for c in self._chips):
            return
        chip = _FileChip(self, path, self._remove,
                         on_sync=self._on_sync,
                         show_copy_opt=self._show_copy_opt)
        self._chips.append(chip)

    def _remove(self, chip: _FileChip):
        self._chips.remove(chip)
        chip.destroy()

    @property
    def paths(self) -> list[str]:
        return [c.path for c in self._chips]

    def get_copy(self, path: str) -> bool:
        for c in self._chips:
            if c.path == path:
                return c.copy_var.get()
        return False

    def set_status(self, path: str, status: str):
        for c in self._chips:
            if c.path == path:
                c.set_status(status)
                return

    def tick_spinners(self):
        for c in self._chips:
            c.tick_spinner()

    def reset_all(self):
        for c in self._chips:
            c.set_status("pending")


class SyncApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Sync Properties")
        self.geometry("620x820")
        self.resizable(False, False)
        self.configure(fg_color=_BG)

        self._excel_path = ""
        self._syncing = False
        self._spin_step = 0
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top bar ───────────────────────────────────────────────────────────
        bar = ctk.CTkFrame(self, fg_color=_BLUE, corner_radius=0, height=52)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        ctk.CTkLabel(bar, text="Sync Properties", font=(_FONT, 15, "bold"),
                     text_color="white").pack(side="left", padx=20)
        ctk.CTkLabel(bar, text="Excel  →  Word / DWG", font=(_FONT, 11),
                     text_color="#a8c7fa").pack(side="right", padx=20)

        # ── Top loading bar ────────────────────────────────────────────────────
        self._top_bar = ctk.CTkProgressBar(
            self, fg_color=_BLUE, progress_color=_BLUE_LT, height=3, corner_radius=0,
        )
        self._top_bar.pack(fill="x")
        self._top_bar.set(0)

        # ── Scrollable body ───────────────────────────────────────────────────
        body = ctk.CTkScrollableFrame(
            self, fg_color=_BG,
            scrollbar_button_color=_BORDER, scrollbar_button_hover_color=_BLUE,
        )
        body.pack(fill="both", expand=True)

        # ── 1 — Excel ─────────────────────────────────────────────────────────
        self._make_section_label(body, "1  —  Izvor podataka")
        ec = _card(body)
        ec.pack(fill="x", padx=16, pady=(0, 10))

        self._info_panel(ec,
            "Čita ključ-vrijednost parove iz lista  'Podaci'  "
            "(stupac A = naziv svojstva,  stupac B = vrijednost).\n"
            "Podržani formati:  .xlsx  •  .xlsm  •  .xls")

        ctk.CTkLabel(ec, text="Excel datoteka", font=(_FONT, 10),
                     text_color=_BLUE).pack(anchor="w", padx=14, pady=(8, 2))
        er = ctk.CTkFrame(ec, fg_color="transparent")
        er.pack(fill="x", padx=14, pady=(0, 10))
        self._excel_lbl = ctk.CTkLabel(
            er, text="Nijedna datoteka nije odabrana", anchor="w",
            font=(_FONT, 12), text_color=_TEXT2,
        )
        self._excel_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            er, text="ODABERI", width=90, height=32, corner_radius=4,
            fg_color=_BLUE, hover_color=_BLUE_H, text_color="white",
            font=(_FONT, 11, "bold"), command=self._pick_excel,
        ).pack(side="right")

        # ── 2 — Word ──────────────────────────────────────────────────────────
        self._make_section_label(body, "2  —  Word datoteke  (.docx / .docm)")
        wc = _card(body)
        wc.pack(fill="x", padx=16, pady=(0, 10))

        self._info_panel(wc,
            "Direktna ZIP/XML promjena — Word ne mora biti otvoren  (~0.5 s/datoteci).\n"
            "DOCPROPERTY polja osvježavaju se automatski pri sljedećem otvaranju u Wordu.\n"
            "Nazivi svojstava su case-insensitivni:  'Snaga' i 'snaga' tretiraju se kao jedno.")

        wh = ctk.CTkFrame(wc, fg_color="transparent")
        wh.pack(fill="x", padx=14, pady=(6, 2))
        ctk.CTkLabel(wh, text="Odabrane datoteke", font=(_FONT, 10),
                     text_color=_BLUE).pack(side="left")
        ctk.CTkLabel(wh, text="☑ kopija  =  spremi kopiju s vremenskim žigom (original ostaje nepromijenjen)",
                     font=(_FONT, 9), text_color=_TEXT2).pack(side="left", padx=8)
        ctk.CTkButton(
            wh, text="+ DODAJ", width=72, height=28, corner_radius=4,
            fg_color=_BLUE, hover_color=_BLUE_H, text_color="white",
            font=(_FONT, 10, "bold"), command=self._add_word,
        ).pack(side="right")

        self._word_list = _FileListFrame(
            wc,
            show_copy_opt=True,
            on_sync=lambda path, make_copy: self._start_one("word", path, make_copy),
        )
        self._word_list.pack(fill="x", padx=10, pady=(2, 10))

        # ── 3 — DWG ───────────────────────────────────────────────────────────
        self._make_section_label(body, "3  —  AutoCAD DWG datoteke")
        dc = _card(body)
        dc.pack(fill="x", padx=16, pady=(0, 10))

        self._info_panel(dc,
            "AutoCAD COM sučelje — AutoCAD mora biti instaliran (2020+).\n"
            "Ekvivalentno SetFieldsValue.lsp, ali pokrenuto automatski iz Pythona.\n"
            "Nazivi su case-insensitivni — 'Snaga invertera' i 'snaga invertera' su isti ključ.\n"
            "AutoCAD se otvara automatski ako nije pokrenut.",
            color=_ORANGE)

        dh = ctk.CTkFrame(dc, fg_color="transparent")
        dh.pack(fill="x", padx=14, pady=(6, 2))
        ctk.CTkLabel(dh, text="Odabrane datoteke", font=(_FONT, 10),
                     text_color=_BLUE).pack(side="left")
        ctk.CTkButton(
            dh, text="+ DODAJ", width=72, height=28, corner_radius=4,
            fg_color=_BLUE, hover_color=_BLUE_H, text_color="white",
            font=(_FONT, 10, "bold"), command=self._add_dwg,
        ).pack(side="right")

        self._dwg_list = _FileListFrame(
            dc,
            on_sync=lambda path, _: self._start_one("dwg", path, False),
        )
        self._dwg_list.pack(fill="x", padx=10, pady=(2, 10))

        # ── Status + Log ───────────────────────────────────────────────────────
        self._make_section_label(body, "Status i poruke")
        sc = _card(body)
        sc.pack(fill="x", padx=16, pady=(0, 16))

        # Gornji red: zadnja sync + clear gumb
        ls_row = ctk.CTkFrame(sc, fg_color="transparent")
        ls_row.pack(fill="x", padx=14, pady=(10, 2))
        ctk.CTkLabel(ls_row, text="Zadnja sinkronizacija:", font=(_FONT, 10),
                     text_color=_TEXT2).pack(side="left")
        self._last_sync_lbl = ctk.CTkLabel(
            ls_row, text="—", font=(_FONT, 10, "bold"), text_color=_TEXT2,
        )
        self._last_sync_lbl.pack(side="left", padx=6)
        ctk.CTkButton(
            ls_row, text="Očisti log", width=80, height=24, corner_radius=4,
            fg_color=_BORDER, hover_color=_TEXT2, text_color=_TEXT,
            font=(_FONT, 9), command=self._clear_log,
        ).pack(side="right")

        # Progress bar
        self._progress = ctk.CTkProgressBar(
            sc, fg_color=_BORDER, progress_color=_BLUE, height=4, corner_radius=2,
        )
        self._progress.pack(fill="x", padx=14, pady=(4, 4))
        self._progress.set(0)

        # Kratki status (jedna linija)
        self._status_lbl = ctk.CTkLabel(
            sc, text="Čeka na pokretanje...", font=(_FONT, 10),
            text_color=_TEXT2, anchor="w",
        )
        self._status_lbl.pack(fill="x", padx=14, pady=(0, 4))

        # ── Log textbox ────────────────────────────────────────────────────────
        self._log_box = ctk.CTkTextbox(
            sc, height=180, font=(_FONT, 10), state="disabled",
            fg_color="#F1F3F4", text_color=_TEXT,
            border_width=1, border_color=_BORDER,
            corner_radius=6,
        )
        self._log_box.pack(fill="x", padx=14, pady=(0, 12))

        # Boje po razini poruke (koristi se underlying tk.Text widget)
        tb = self._log_box._textbox
        tb.tag_config("ok",    foreground=_GREEN)
        tb.tag_config("error", foreground=_RED)
        tb.tag_config("warn",  foreground=_ORANGE)
        tb.tag_config("info",  foreground=_BLUE)
        tb.tag_config("dim",   foreground=_TEXT2)

        # ── Bottom action bar ──────────────────────────────────────────────────
        action = ctk.CTkFrame(
            self, fg_color=_CARD, corner_radius=0, height=64,
            border_width=1, border_color=_BORDER,
        )
        action.pack(fill="x", side="bottom")
        action.pack_propagate(False)

        self._run_btn = ctk.CTkButton(
            action, text="SINKRONIZIRAJ SVE", width=210, height=40, corner_radius=20,
            fg_color=_BLUE, hover_color=_BLUE_H, text_color="white",
            font=(_FONT, 13, "bold"), command=self._start,
        )
        self._run_btn.pack(side="right", padx=20, pady=12)

    @staticmethod
    def _make_section_label(parent, text: str):
        ctk.CTkLabel(
            parent, text=text.upper(), font=(_FONT, 9, "bold"), text_color=_TEXT2,
        ).pack(anchor="w", padx=20, pady=(12, 3))

    @staticmethod
    def _info_panel(parent, text: str, color: str = _BLUE):
        """Kompaktna obojena info traka s uputama."""
        bg = {_BLUE: _BLUE_LT, _ORANGE: "#FFF3E0", _GREEN: "#E8F5E9"}.get(color, _BLUE_LT)
        f = ctk.CTkFrame(parent, fg_color=bg, corner_radius=4)
        f.pack(fill="x", padx=14, pady=(8, 2))
        ctk.CTkLabel(
            f, text=text,
            font=(_FONT, 10), text_color=color,
            anchor="w", justify="left", wraplength=540,
        ).pack(anchor="w", padx=10, pady=6)

    # ── pickers ───────────────────────────────────────────────────────────────

    def _pick_excel(self):
        p = filedialog.askopenfilename(
            title="Odaberi Excel datoteku",
            filetypes=[("Excel", "*.xlsx *.xlsm *.xls"), ("Sve", "*.*")],
        )
        if p:
            self._excel_path = p
            self._excel_lbl.configure(text=os.path.basename(p), text_color=_TEXT)

    def _add_word(self):
        for p in filedialog.askopenfilenames(
            title="Odaberi Word datoteke",
            filetypes=[("Word", "*.docx *.docm"), ("Sve", "*.*")],
        ):
            self._word_list.add(p)

    def _add_dwg(self):
        for p in filedialog.askopenfilenames(
            title="Odaberi DWG datoteke",
            filetypes=[("AutoCAD DWG", "*.dwg"), ("Sve", "*.*")],
        ):
            self._dwg_list.add(p)

    # ── spinner animation (runs in GUI thread via after()) ────────────────────

    def _tick(self):
        if self._syncing:
            self._word_list.tick_spinners()
            self._dwg_list.tick_spinners()
            # Animate top loading bar (bounce effect)
            self._spin_step = (self._spin_step + 1) % 100
            v = abs(50 - self._spin_step) / 50
            self._top_bar.set(v)
            self.after(80, self._tick)

    # ── sync ──────────────────────────────────────────────────────────────────

    def _start(self):
        if not self._excel_path:
            messagebox.showwarning("Greška", "Odaberi Excel datoteku!")
            return
        if not self._word_list.paths and not self._dwg_list.paths:
            messagebox.showwarning("Greška", "Dodaj barem jednu Word ili DWG datoteku!")
            return
        self._syncing = True
        self._run_btn.configure(state="disabled", fg_color=_TEXT2)
        self._word_list.reset_all()
        self._dwg_list.reset_all()
        self._progress.set(0)
        self.after(0, self._tick)
        threading.Thread(target=self._sync, daemon=True).start()

    def _start_one(self, file_type: str, path: str, make_copy: bool):
        if not self._excel_path:
            messagebox.showwarning("Greška", "Odaberi Excel datoteku!")
            return
        file_list = self._word_list if file_type == "word" else self._dwg_list
        self._ui(lambda p=path: file_list.set_status(p, "running"))
        threading.Thread(
            target=self._sync_one_worker,
            args=(file_type, path, make_copy, file_list),
            daemon=True,
        ).start()

    def _sync_one_worker(self, file_type: str, path: str, make_copy: bool, file_list):
        name = os.path.basename(path)
        log = self._make_log_fn()
        self._set_status(f"Sinkroniziram: {name}...")
        log(f"── Pokrenuto: {name}", "dim")
        try:
            props = read_excel_properties(self._excel_path)
            log(f"Učitano {len(props)} svojstava iz Excela.", "info")
            if file_type == "word":
                out = update_word_properties(path, props, make_copy=make_copy, log_fn=log)
                log(f"Word ✓  {name}  →  {os.path.basename(out)}", "ok")
            else:
                update_dwg_properties(path, props, log_fn=log)
                log(f"DWG ✓  {name}", "ok")
            self._ui(lambda p=path: file_list.set_status(p, "ok"))
            ts = datetime.now().strftime("%H:%M:%S")
            self._set_status(f"Gotovo: {name}  ✓", None)
            self._ui(lambda s=f"{ts}  ·  {name}  ✓":
                     self._last_sync_lbl.configure(text=s, text_color=_GREEN))
        except Exception as exc:
            self._ui(lambda p=path: file_list.set_status(p, "error"))
            self._set_status(f"Greška: {name}")
            log(f"GREŠKA — {exc}", "error")
            self._ui(lambda e=str(exc): messagebox.showerror("Greška", e))

    def _ui(self, fn):
        """Schedule fn on the GUI thread."""
        self.after(0, fn)

    def _set_status(self, msg: str, pct: float | None = None):
        self._ui(lambda: self._status_lbl.configure(text=msg))
        if pct is not None:
            self._ui(lambda: self._progress.set(pct))

    def _log(self, msg: str, level: str = "info"):
        """Dodaj obojenu poruku u log widget (mora biti pozvano iz GUI threada)."""
        ts = datetime.now().strftime("%H:%M:%S")
        icons = {"ok": "✓", "error": "✗", "warn": "⚠", "info": "·", "dim": "·"}
        icon = icons.get(level, "·")
        line = f"[{ts}]  {icon}  {msg.strip()}\n"
        self._log_box.configure(state="normal")
        self._log_box.insert("end", line, level)
        self._log_box.configure(state="disabled")
        self._log_box.see("end")

    def _clear_log(self):
        """Očisti sve poruke iz log widgeta."""
        self._log_box.configure(state="normal")
        self._log_box.delete("0.0", "end")
        self._log_box.configure(state="disabled")

    def _make_log_fn(self):
        """Vrati thread-safe callback koji upisuje u log widget."""
        def log_fn(msg: str, level: str = "info"):
            self._ui(lambda m=msg, l=level: self._log(m, l))
        return log_fn

    def _sync(self):
        errors: list[str] = []
        ok_count = 0
        log = self._make_log_fn()
        try:
            self._set_status("Čitam Excel datoteku...", 0.0)
            log("── Sinkronizacija pokrenuta ──", "dim")
            props = read_excel_properties(self._excel_path)
            n_props = len(props)
            log(f"Učitano {n_props} svojstava iz Excela.", "info")

            word_paths = self._word_list.paths
            dwg_paths  = self._dwg_list.paths
            total = len(word_paths) + len(dwg_paths)
            done  = 0

            for path in word_paths:
                name = os.path.basename(path)
                make_copy = self._word_list.get_copy(path)
                self._ui(lambda p=path: self._word_list.set_status(p, "running"))
                self._set_status(f"Word: {name}")
                log(f"Word → {name}", "info")
                try:
                    out = update_word_properties(path, props, make_copy=make_copy, log_fn=log)
                    self._ui(lambda p=path: self._word_list.set_status(p, "ok"))
                    ok_count += 1
                    log(f"Word ✓  {name}  →  {os.path.basename(out)}", "ok")
                except Exception as exc:
                    self._ui(lambda p=path: self._word_list.set_status(p, "error"))
                    log(f"Word GREŠKA  {name}: {exc}", "error")
                    errors.append(f"Word '{name}': {exc}")
                done += 1
                self._set_status(f"Word: {name}  ✓", done / total)

            for path in dwg_paths:
                name = os.path.basename(path)
                self._ui(lambda p=path: self._dwg_list.set_status(p, "running"))
                self._set_status(f"DWG: {name}")
                log(f"DWG → {name}", "info")
                try:
                    update_dwg_properties(path, props, log_fn=log)
                    self._ui(lambda p=path: self._dwg_list.set_status(p, "ok"))
                    ok_count += 1
                    log(f"DWG ✓  {name}", "ok")
                except Exception as exc:
                    self._ui(lambda p=path: self._dwg_list.set_status(p, "error"))
                    log(f"DWG GREŠKA  {name}: {exc}", "error")
                    errors.append(f"DWG '{name}': {exc}")
                done += 1
                self._set_status(f"DWG: {name}  ✓", done / total)

            # ── Završni status ────────────────────────────────────────────────
            ts = datetime.now().strftime("%H:%M:%S")
            if errors:
                summary = f"{ok_count}/{total} datoteka  •  {len(errors)} grešaka"
                self._set_status(f"Završeno s greškama — {summary}", 1.0)
                log(f"── Završeno s greškama: {summary} ──", "error")
                self._ui(lambda s=f"{ts}  ·  {summary}":
                         self._last_sync_lbl.configure(text=s, text_color=_RED))
                self._ui(lambda: messagebox.showerror(
                    "Greške pri sinkronizaciji",
                    "\n".join(errors) + "\n\nDetalji su vidljivi u log panelu."
                ))
            else:
                summary = f"{total} datoteka  •  {n_props} svojstava"
                self._set_status(f"Sinkronizacija završena — {summary}", 1.0)
                log(f"── Sinkronizacija završena: {summary} ──", "ok")
                self._ui(lambda s=f"{ts}  ·  {summary}  ✓":
                         self._last_sync_lbl.configure(text=s, text_color=_GREEN))
                copies_made = any(self._word_list.get_copy(p) for p in word_paths)
                note = "\nKopije su spremljene uz originale." if copies_made else ""
                self._ui(lambda: messagebox.showinfo(
                    "Gotovo", f"Sinkronizirano {total} datoteka!\n{n_props} svojstava prebačeno.{note}"
                ))

        except Exception as exc:
            self._set_status(f"Greška: {exc}")
            log(f"KRITIČNA GREŠKA: {exc}", "error")
            self._ui(lambda: messagebox.showerror("Greška", str(exc)))
        finally:
            self._syncing = False
            self._ui(lambda: self._top_bar.set(0))
            self._ui(lambda: self._run_btn.configure(state="normal", fg_color=_BLUE))


if __name__ == "__main__":
    app = SyncApp()
    app.mainloop()
