"""
syncDwgFast.py — Brzi DWG property synchronizer (bez AutoCAD-a)

Čita ključ-vrijednost parove iz Excel lista 'Podaci' i upisuje ih kao
custom document properties u DWG datoteke koristeći ACadSharp .NET library
— bez pokretanja AutoCAD-a (~0.3s/datoteci umjesto ~3-8s via COM).

Za svaku datoteku se pravi kopija s vremenskim žigom ako je opcija uključena.

Zahtjevi:
  - Python 3.10+  (pip: openpyxl customtkinter)
  - dwg_props_helper.exe  (kompajlira se jednom: dotnet publish -c Release -r win-x64 --self-contained)

Veza s ostalim programima:
  - syncProperties.py  — ostaje nepromijenjen, koristi AutoCAD COM za DWG
  - ovaj program  — brža alternativa, ne treba AutoCAD
"""

import json
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime

import openpyxl
import customtkinter as ctk
from tkinter import filedialog, messagebox

# ── Putanja do C# helpera ──────────────────────────────────────────────────────
# Traži exe na dvije moguće lokacije (uz .py ili u publish/ folderu)
_HELPER_PATHS = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "dwg_props_helper", "dwg_props_helper.exe"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "dwg_props_helper", "bin", "Release", "net8.0",
                 "win-x64", "publish", "dwg_props_helper.exe"),
]
_HELPER = next((p for p in _HELPER_PATHS if os.path.exists(p)), _HELPER_PATHS[0])

# ── Google Material Design paleta ─────────────────────────────────────────────
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

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


# ── Excel ─────────────────────────────────────────────────────────────────────

def read_excel_properties(path: str, sheet: str = "Podaci") -> dict[str, str]:
    """Vrati {naziv: vrijednost} iz stupaca A i B danog lista."""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[sheet]
    props: dict[str, str] = {}
    for row in ws.iter_rows(min_row=1, max_col=2, values_only=True):
        name, value = row
        if name:
            props[str(name).strip()] = str(value).strip() if value is not None else ""
    wb.close()
    return props


# ── DWG helper (ACadSharp via subprocess) ─────────────────────────────────────

def _strip_kopija_suffix(base: str) -> str:
    """Ukloni _Nova_kopija_DD_MM_YY--HH_MM sufiks ako postoji."""
    return re.sub(r"_Nova_kopija_\d{2}_\d{2}_\d{2}--\d{2}_\d{2}$", "", base)


def check_helper() -> str | None:
    """Vrati putanju do helpera ako postoji na bilo kojoj poznatoj lokaciji, inače None."""
    return next((p for p in _HELPER_PATHS if os.path.exists(p)), None)


def update_dwg_properties_fast(
    dwg_path: str,
    properties: dict[str, str],
    make_copy: bool = True,
    log_fn=None,
) -> str:
    """
    Upiši custom properties u DWG datoteku koristeći ACadSharp (bez AutoCAD-a).

    Ako make_copy=True, pravi se kopija s vremenskim žigom — original ostaje netaknut.
    Vraća putanju modificirane datoteke.
    """
    def _log(msg: str, level: str = "info"):
        print(f"  [DWG-fast] {msg}")
        if log_fn:
            log_fn(msg, level)

    helper = check_helper()
    if not helper:
        raise FileNotFoundError(
            f"dwg_props_helper.exe nije pronađen:\n{_HELPER}\n\n"
            "Kompajliraj helper jednom:\n"
            "  cd python/dwg_props_helper\n"
            "  dotnet publish -c Release -r win-x64 --self-contained"
        )

    # Napravi kopiju ako je traženo
    if make_copy:
        base, ext = os.path.splitext(dwg_path)
        base = _strip_kopija_suffix(base)
        ts = datetime.now().strftime("%d_%m_%y--%H_%M")
        out_path = f"{base}_Nova_kopija_{ts}{ext}"
        shutil.copy2(dwg_path, out_path)
        _log(f"Kopija: {os.path.basename(out_path)}", "info")
    else:
        out_path = dwg_path

    # Pozovi C# helper
    result = subprocess.run(
        [helper, os.path.abspath(out_path), json.dumps(properties, ensure_ascii=False)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )

    # Parsiraj stdout — redovi INFO|..., OK|..., WARN|...
    for line in result.stdout.splitlines():
        if line.startswith("OK|"):
            _log(line[3:], "ok")
        elif line.startswith("WARN|"):
            _log(line[5:], "warn")
        elif line.startswith("INFO|"):
            _log(line[5:], "info")

    if result.returncode != 0:
        err = result.stderr.strip() or "Nepoznata greška u dwg_props_helper"
        raise RuntimeError(err)

    return out_path


# ── GUI widgets ───────────────────────────────────────────────────────────────

def _card(parent, **kw) -> ctk.CTkFrame:
    return ctk.CTkFrame(
        parent, fg_color=_CARD, corner_radius=8,
        border_width=1, border_color=_BORDER, **kw,
    )


class _FileChip:
    """Red s datotekom: status ikona · naziv · [kopija checkbox] · ▶ sync · ✕ ukloni."""

    _ICONS = {
        "pending": ("—", _TEXT2, _BLUE_LT),
        "running": ("⠋", _BLUE,  "#DBEAFE"),
        "ok":      ("✓", _GREEN, "#D7F3E3"),
        "error":   ("✗", _RED,   "#FDECEA"),
    }

    def __init__(self, parent, path: str, on_remove, on_sync=None):
        self.path = path
        self._spin_idx = 0
        self._status = "pending"
        self.copy_var = ctk.BooleanVar(value=True)

        self._frame = ctk.CTkFrame(parent, fg_color=_BLUE_LT, corner_radius=6)
        self._frame.pack(fill="x", pady=2, padx=2)

        self._icon_lbl = ctk.CTkLabel(
            self._frame, text="—", width=22, font=(_FONT, 12, "bold"), text_color=_TEXT2,
        )
        self._icon_lbl.pack(side="left", padx=(8, 2), pady=4)

        self._name_lbl = ctk.CTkLabel(
            self._frame, text=os.path.basename(path), anchor="w",
            font=(_FONT, 11), text_color=_TEXT,
        )
        self._name_lbl.pack(side="left", fill="x", expand=True, pady=4)

        # Desni gumbi (redoslijed: kopija | sync | ukloni)
        ctk.CTkButton(
            self._frame, text="✕", width=24, height=24, corner_radius=12,
            fg_color=_RED, hover_color=_RED_H, text_color="white",
            font=(_FONT, 10, "bold"),
            command=lambda: on_remove(self),
        ).pack(side="right", padx=(0, 6))

        if on_sync is not None:
            ctk.CTkButton(
                self._frame, text="▶", width=28, height=24, corner_radius=4,
                fg_color=_GREEN, hover_color="#2D8F46", text_color="white",
                font=(_FONT, 10, "bold"),
                command=lambda: on_sync(self.path, self.copy_var.get()),
            ).pack(side="right", padx=(0, 4))

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
    def __init__(self, master, on_sync=None, **kw):
        super().__init__(
            master, height=90, fg_color=_CARD,
            scrollbar_button_color=_BORDER,
            scrollbar_button_hover_color=_BLUE, **kw,
        )
        self._chips: list[_FileChip] = []
        self._on_sync = on_sync

    def add(self, path: str):
        if any(c.path == path for c in self._chips):
            return
        chip = _FileChip(self, path, self._remove, on_sync=self._on_sync)
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
        return True

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


# ── Glavni prozor ─────────────────────────────────────────────────────────────

class SyncDwgFastApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Sync DWG Fast")
        self.geometry("620x700")
        self.resizable(False, False)
        self.configure(fg_color=_BG)

        self._excel_path = ""
        self._syncing = False
        self._spin_step = 0
        self._build_ui()

    # ── Izgradnja UI ──────────────────────────────────────────────────────────

    def _build_ui(self):
        # Top bar
        bar = ctk.CTkFrame(self, fg_color=_BLUE, corner_radius=0, height=52)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        ctk.CTkLabel(bar, text="Sync DWG Fast", font=(_FONT, 15, "bold"),
                     text_color="white").pack(side="left", padx=20)
        ctk.CTkLabel(bar, text="Excel  →  DWG  (ACadSharp, bez AutoCAD-a)",
                     font=(_FONT, 11), text_color="#a8c7fa").pack(side="right", padx=20)

        # Loading bar
        self._top_bar = ctk.CTkProgressBar(
            self, fg_color=_BLUE, progress_color=_BLUE_LT, height=3, corner_radius=0,
        )
        self._top_bar.pack(fill="x")
        self._top_bar.set(0)

        # Scrollable tijelo
        body = ctk.CTkScrollableFrame(
            self, fg_color=_BG,
            scrollbar_button_color=_BORDER, scrollbar_button_hover_color=_BLUE,
        )
        body.pack(fill="both", expand=True)

        # ── Helper status ─────────────────────────────────────────────────────
        self._make_section_label(body, "Helper status")
        hc = _card(body)
        hc.pack(fill="x", padx=16, pady=(0, 10))
        self._helper_lbl = ctk.CTkLabel(
            hc, text="Provjeravam...", font=(_FONT, 11), text_color=_TEXT2,
            anchor="w",
        )
        self._helper_lbl.pack(fill="x", padx=14, pady=(10, 4))

        build_row = ctk.CTkFrame(hc, fg_color="transparent")
        build_row.pack(fill="x", padx=14, pady=(0, 10))
        ctk.CTkLabel(
            build_row,
            text="Ako .exe ne postoji, pokreni jednom u terminalu:",
            font=(_FONT, 9), text_color=_TEXT2,
        ).pack(side="left")
        ctk.CTkButton(
            build_row, text="📋 Kopiraj naredbu", width=130, height=24,
            corner_radius=4, fg_color=_BORDER, hover_color=_TEXT2, text_color=_TEXT,
            font=(_FONT, 9),
            command=self._copy_build_cmd,
        ).pack(side="right")

        # Ažuriraj helper status
        self.after(100, self._refresh_helper_status)

        # ── 1 — Excel ─────────────────────────────────────────────────────────
        self._make_section_label(body, "1  —  Izvor podataka (Excel)")
        ec = _card(body)
        ec.pack(fill="x", padx=16, pady=(0, 10))

        self._info_panel(ec,
            "Čita ključ-vrijednost parove iz lista 'Podaci'  "
            "(stupac A = naziv,  stupac B = vrijednost).\n"
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

        # ── 2 — DWG datoteke ──────────────────────────────────────────────────
        self._make_section_label(body, "2  —  DWG datoteke")
        dc = _card(body)
        dc.pack(fill="x", padx=16, pady=(0, 10))

        self._info_panel(dc,
            "ACadSharp .NET library — AutoCAD ne mora biti instaliran  (~0.3 s/datoteci).\n"
            "Nazivi svojstava su case-insensitivni:  'Snaga' i 'snaga' tretiraju se kao jedno.\n"
            "☑ kopija  =  napravi kopiju s vremenskim žigom, original ostaje netaknut.",
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
            on_sync=lambda path, copy: self._start_one(path, copy),
        )
        self._dwg_list.pack(fill="x", padx=10, pady=(2, 10))

        # ── Status i log ──────────────────────────────────────────────────────
        self._make_section_label(body, "Status i poruke")
        sc = _card(body)
        sc.pack(fill="x", padx=16, pady=(0, 16))

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

        self._progress = ctk.CTkProgressBar(
            sc, fg_color=_BORDER, progress_color=_BLUE, height=4, corner_radius=2,
        )
        self._progress.pack(fill="x", padx=14, pady=(4, 4))
        self._progress.set(0)

        self._status_lbl = ctk.CTkLabel(
            sc, text="Čeka na pokretanje...", font=(_FONT, 10),
            text_color=_TEXT2, anchor="w",
        )
        self._status_lbl.pack(fill="x", padx=14, pady=(0, 4))

        self._log_box = ctk.CTkTextbox(
            sc, height=160, font=(_FONT, 10), state="disabled",
            fg_color="#F1F3F4", text_color=_TEXT,
            border_width=1, border_color=_BORDER, corner_radius=6,
        )
        self._log_box.pack(fill="x", padx=14, pady=(0, 12))

        tb = self._log_box._textbox
        tb.tag_config("ok",    foreground=_GREEN)
        tb.tag_config("error", foreground=_RED)
        tb.tag_config("warn",  foreground=_ORANGE)
        tb.tag_config("info",  foreground=_BLUE)
        tb.tag_config("dim",   foreground=_TEXT2)

        # Bottom action bar
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
        bg = {_BLUE: _BLUE_LT, _ORANGE: "#FFF3E0", _GREEN: "#E8F5E9"}.get(color, _BLUE_LT)
        f = ctk.CTkFrame(parent, fg_color=bg, corner_radius=4)
        f.pack(fill="x", padx=14, pady=(8, 2))
        ctk.CTkLabel(
            f, text=text,
            font=(_FONT, 10), text_color=color,
            anchor="w", justify="left", wraplength=550,
        ).pack(anchor="w", padx=10, pady=6)

    # ── Helper status ─────────────────────────────────────────────────────────

    def _refresh_helper_status(self):
        if check_helper():
            self._helper_lbl.configure(
                text=f"✓  dwg_props_helper.exe pronađen  —  {_HELPER}",
                text_color=_GREEN,
            )
        else:
            self._helper_lbl.configure(
                text="✗  dwg_props_helper.exe nije pronađen  —  potrebno kompajlirati (vidi uputu ispod)",
                text_color=_RED,
            )

    def _copy_build_cmd(self):
        helper_dir = os.path.dirname(_HELPER)
        cmd = f"cd \"{helper_dir}\" && dotnet publish -c Release -r win-x64 --self-contained"
        self.clipboard_clear()
        self.clipboard_append(cmd)
        messagebox.showinfo(
            "Naredba kopirana",
            f"Zalijepi i pokreni u CMD/PowerShell:\n\n{cmd}",
        )

    # ── Pickers ───────────────────────────────────────────────────────────────

    def _pick_excel(self):
        p = filedialog.askopenfilename(
            title="Odaberi Excel datoteku",
            filetypes=[("Excel", "*.xlsx *.xlsm *.xls"), ("Sve", "*.*")],
        )
        if p:
            self._excel_path = p
            self._excel_lbl.configure(text=os.path.basename(p), text_color=_TEXT)

    def _add_dwg(self):
        for p in filedialog.askopenfilenames(
            title="Odaberi DWG datoteke",
            filetypes=[("AutoCAD DWG", "*.dwg"), ("Sve", "*.*")],
        ):
            self._dwg_list.add(p)

    # ── Log ───────────────────────────────────────────────────────────────────

    def _ui(self, fn):
        self.after(0, fn)

    def _log(self, msg: str, level: str = "info"):
        ts = datetime.now().strftime("%H:%M:%S")
        icons = {"ok": "✓", "error": "✗", "warn": "⚠", "info": "·", "dim": "·"}
        line = f"[{ts}]  {icons.get(level, '·')}  {msg.strip()}\n"
        self._log_box.configure(state="normal")
        self._log_box.insert("end", line, level)
        self._log_box.configure(state="disabled")
        self._log_box.see("end")

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("0.0", "end")
        self._log_box.configure(state="disabled")

    def _make_log_fn(self):
        def log_fn(msg: str, level: str = "info"):
            self._ui(lambda m=msg, l=level: self._log(m, l))
        return log_fn

    def _set_status(self, msg: str, pct: float | None = None):
        self._ui(lambda: self._status_lbl.configure(text=msg))
        if pct is not None:
            self._ui(lambda: self._progress.set(pct))

    # ── Spinner ───────────────────────────────────────────────────────────────

    def _tick(self):
        if self._syncing:
            self._dwg_list.tick_spinners()
            self._spin_step = (self._spin_step + 1) % 100
            v = abs(50 - self._spin_step) / 50
            self._top_bar.set(v)
            self.after(80, self._tick)

    # ── Sync — jedna datoteka (▶ gumb) ────────────────────────────────────────

    def _start_one(self, path: str, make_copy: bool):
        if not self._validate():
            return
        self._ui(lambda p=path: self._dwg_list.set_status(p, "running"))
        threading.Thread(
            target=self._sync_one_worker,
            args=(path, make_copy),
            daemon=True,
        ).start()

    def _sync_one_worker(self, path: str, make_copy: bool):
        name = os.path.basename(path)
        log = self._make_log_fn()
        self._set_status(f"Sinkroniziram: {name}...")
        log(f"── Pokrenuto: {name}", "dim")
        try:
            props = read_excel_properties(self._excel_path)
            log(f"Učitano {len(props)} svojstava iz Excela.", "info")
            out = update_dwg_properties_fast(path, props, make_copy=make_copy, log_fn=log)
            self._ui(lambda p=path: self._dwg_list.set_status(p, "ok"))
            ts = datetime.now().strftime("%H:%M:%S")
            self._set_status(f"Gotovo: {name}  ✓")
            self._ui(lambda s=f"{ts}  ·  {name}  ✓":
                     self._last_sync_lbl.configure(text=s, text_color=_GREEN))
            # Osvježi helper status (exe je možda kompajliran međuvremenom)
            self._ui(self._refresh_helper_status)
        except Exception as exc:
            self._ui(lambda p=path: self._dwg_list.set_status(p, "error"))
            self._set_status(f"Greška: {name}")
            log(f"GREŠKA — {exc}", "error")
            self._ui(lambda e=str(exc): messagebox.showerror("Greška", e))

    # ── Sync — sve datoteke ───────────────────────────────────────────────────

    def _validate(self) -> bool:
        if not self._excel_path:
            messagebox.showwarning("Greška", "Odaberi Excel datoteku!")
            return False
        if not check_helper():
            messagebox.showerror(
                "Helper nije pronađen",
                f"dwg_props_helper.exe nije pronađen.\n\n"
                f"Kompajliraj jednom:\n"
                f"  cd python/dwg_props_helper\n"
                f"  dotnet publish -c Release -r win-x64 --self-contained\n\n"
                f"Očekivana putanja:\n{_HELPER}",
            )
            return False
        return True

    def _start(self):
        if not self._validate():
            return
        if not self._dwg_list.paths:
            messagebox.showwarning("Greška", "Dodaj barem jednu DWG datoteku!")
            return
        self._syncing = True
        self._run_btn.configure(state="disabled", fg_color=_TEXT2)
        self._dwg_list.reset_all()
        self._progress.set(0)
        self.after(0, self._tick)
        threading.Thread(target=self._sync_all, daemon=True).start()

    def _sync_all(self):
        errors: list[str] = []
        ok_count = 0
        log = self._make_log_fn()
        try:
            log("── Sinkronizacija pokrenuta ──", "dim")
            self._set_status("Čitam Excel datoteku...", 0.0)
            props = read_excel_properties(self._excel_path)
            n_props = len(props)
            log(f"Učitano {n_props} svojstava iz Excela.", "info")

            paths = self._dwg_list.paths
            total = len(paths)

            for i, path in enumerate(paths):
                name = os.path.basename(path)
                make_copy = self._dwg_list.get_copy(path)
                self._ui(lambda p=path: self._dwg_list.set_status(p, "running"))
                self._set_status(f"DWG: {name}")
                log(f"DWG → {name}", "info")
                try:
                    out = update_dwg_properties_fast(
                        path, props, make_copy=make_copy, log_fn=log
                    )
                    self._ui(lambda p=path: self._dwg_list.set_status(p, "ok"))
                    ok_count += 1
                    log(f"DWG ✓  {name}  →  {os.path.basename(out)}", "ok")
                except Exception as exc:
                    self._ui(lambda p=path: self._dwg_list.set_status(p, "error"))
                    log(f"DWG GREŠKA  {name}: {exc}", "error")
                    errors.append(f"'{name}': {exc}")
                self._set_status(f"DWG: {name}  ✓", (i + 1) / total)

            # Završni status
            ts = datetime.now().strftime("%H:%M:%S")
            if errors:
                summary = f"{ok_count}/{total} datoteka  •  {len(errors)} grešaka"
                self._set_status(f"Završeno s greškama — {summary}", 1.0)
                log(f"── Završeno s greškama: {summary} ──", "error")
                self._ui(lambda s=f"{ts}  ·  {summary}":
                         self._last_sync_lbl.configure(text=s, text_color=_RED))
                self._ui(lambda: messagebox.showerror(
                    "Greške pri sinkronizaciji",
                    "\n".join(errors) + "\n\nDetalji su vidljivi u log panelu.",
                ))
            else:
                summary = f"{total} datoteka  •  {n_props} svojstava"
                self._set_status(f"Sinkronizacija završena — {summary}", 1.0)
                log(f"── Sinkronizacija završena: {summary} ──", "ok")
                self._ui(lambda s=f"{ts}  ·  {summary}  ✓":
                         self._last_sync_lbl.configure(text=s, text_color=_GREEN))
                copies = sum(1 for p in paths if self._dwg_list.get_copy(p))
                note = f"\n{copies} kopija je spremljeno uz originale." if copies else ""
                self._ui(lambda: messagebox.showinfo(
                    "Gotovo",
                    f"Sinkronizirano {total} DWG datoteka!\n{n_props} svojstava prebačeno.{note}",
                ))

        except Exception as exc:
            self._set_status(f"Greška: {exc}")
            log(f"KRITIČNA GREŠKA: {exc}", "error")
            self._ui(lambda: messagebox.showerror("Greška", str(exc)))
        finally:
            self._syncing = False
            self._ui(lambda: self._top_bar.set(0))
            self._ui(lambda: self._run_btn.configure(state="normal", fg_color=_BLUE))
            self._ui(self._refresh_helper_status)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = SyncDwgFastApp()
    app.mainloop()
