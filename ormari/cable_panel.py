"""Lijevi panel — baza podataka kabela s pregledom i uredivačem."""
from __future__ import annotations
from typing import Callable, Optional, List
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

try:
    from .cable_db import (
        get_cable_types, get_sections, get_families,
        get_configs_for_family, get_full_key,
        get_effective_ampacity, load_db, save_db,
    )
except ImportError:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from ormari.cable_db import (
        get_cable_types, get_sections, get_families,
        get_configs_for_family, get_full_key,
        get_effective_ampacity, load_db, save_db,
    )

C_BG    = "#0C1A28"
C_PANEL = "#071420"
C_HEAD  = "#1E88E5"
C_LBL   = "#90A4AE"
C_VAL   = "#B0BEC5"
C_OK    = "#4CAF50"
C_SEL   = "#1E3A5F"

ROW_EVEN = "#0A1520"
ROW_ODD  = "#0D1B2A"
ROW_SEL  = "#1C3250"


class CablePanel(ctk.CTkFrame):
    """
    Lijevi panel s bazom kabela.
    on_apply(cable_type_full, section_mm2) — poziva se kad korisnik klikne 'Primijeni'.
    """

    def __init__(
        self,
        parent,
        cable_db: dict,
        on_apply: Callable[[str, float], None],
        on_db_changed: Callable[[], None],
    ) -> None:
        super().__init__(parent, fg_color=C_PANEL, corner_radius=0)
        self.cable_db    = cable_db
        self.on_apply    = on_apply
        self.on_db_changed = on_db_changed

        self._selected_section: Optional[float] = None
        self._selected_row: Optional[int] = None

        self._build_ui()
        self._init_selectors()

    # ── Javno sučelje ──────────────────────────────────────────

    def refresh(self) -> None:
        """Osvježi prikaz kad se cable_db promijeni."""
        cur_family = self._var_family.get()
        cur_config = self._var_config.get()
        self._init_selectors()
        # Pokušaj zadržati prethodnu selekciju
        families = get_families(self.cable_db)
        if cur_family in families:
            self._var_family.set(cur_family)
            self._on_family_change()
            configs = get_configs_for_family(self.cable_db, cur_family)
            if cur_config in configs:
                self._var_config.set(cur_config)
        self._refresh_table()

    def highlight_cable(self, cable_type_full: str, section_mm2: float) -> None:
        """Selektira kabel iz ormara na shemi (kad se klikne ormar)."""
        from .cable_db import parse_cable_name
        family, config = parse_cable_name(cable_type_full) if '.' not in cable_type_full \
            else (cable_type_full, "")
        try:
            from .cable_db import parse_cable_name as pcn
            family, config = pcn(cable_type_full)
        except Exception:
            pass
        families = get_families(self.cable_db)
        if family in families:
            self._var_family.set(family)
            self._on_family_change()
            configs = get_configs_for_family(self.cable_db, family)
            if config in configs:
                self._var_config.set(config)
        self._refresh_table()
        self._selected_section = section_mm2

    # ── Izgradnja UI ────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        r = 0

        ctk.CTkLabel(
            self, text="BAZA KABELA",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#E3F2FD",
        ).grid(row=r, column=0, sticky="ew", padx=8, pady=(10, 4))
        r += 1

        # ── Obitelj kabela ────────────────────────────────────
        ctk.CTkLabel(self, text="Vrsta kabela:",
                     text_color=C_LBL, font=ctk.CTkFont(size=10), anchor="w") \
            .grid(row=r, column=0, sticky="w", padx=8)
        r += 1

        self._var_family = ctk.StringVar()
        self._om_family = ctk.CTkOptionMenu(
            self, variable=self._var_family, values=["—"],
            command=lambda _: self._on_family_change(), width=200,
        )
        self._om_family.grid(row=r, column=0, sticky="ew", padx=8, pady=(0, 4))
        r += 1

        # ── Konfiguracija žila ────────────────────────────────
        ctk.CTkLabel(self, text="Broj žila / konfiguracija:",
                     text_color=C_LBL, font=ctk.CTkFont(size=10), anchor="w") \
            .grid(row=r, column=0, sticky="w", padx=8)
        r += 1

        self._var_config = ctk.StringVar()
        self._om_config = ctk.CTkOptionMenu(
            self, variable=self._var_config, values=["—"],
            command=lambda _: self._refresh_table(), width=200,
        )
        self._om_config.grid(row=r, column=0, sticky="ew", padx=8, pady=(0, 2))
        r += 1

        # Opis kabela
        self._lbl_opis = ctk.CTkLabel(
            self, text="", text_color=C_LBL,
            font=ctk.CTkFont(size=9), wraplength=190, justify="left",
        )
        self._lbl_opis.grid(row=r, column=0, sticky="ew", padx=8, pady=(0, 6))
        r += 1

        # ── Header tablice ────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="#0F2030", corner_radius=4)
        hdr.grid(row=r, column=0, sticky="ew", padx=6, pady=(0, 1))
        hdr.grid_columnconfigure((0, 1, 2), weight=1)
        for col, txt in enumerate(["mm²", "Zrak (A)", "Zemlja (A)"]):
            ctk.CTkLabel(
                hdr, text=txt,
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=C_HEAD,
            ).grid(row=0, column=col, padx=4, pady=4)
        r += 1

        # ── Scrollable tablica ────────────────────────────────
        self._table_frame = ctk.CTkScrollableFrame(
            self, fg_color="#080F18", corner_radius=4,
        )
        self._table_frame.grid(row=r, column=0, sticky="nsew", padx=6, pady=2)
        self._table_frame.grid_columnconfigure((0, 1, 2), weight=1)
        self.grid_rowconfigure(r, weight=1)
        r += 1

        # ── Gumbi ─────────────────────────────────────────────
        ctk.CTkButton(
            self, text="Primijeni na spoj",
            command=self._apply_to_board,
            fg_color="#1B3A1B", hover_color="#388E3C",
            font=ctk.CTkFont(size=11),
        ).grid(row=r, column=0, sticky="ew", padx=8, pady=(6, 2))
        r += 1

        ctk.CTkButton(
            self, text="Uredi bazu kabela",
            command=self._open_editor,
            fg_color="#1A2A3A", hover_color="#546E7A",
            font=ctk.CTkFont(size=11),
        ).grid(row=r, column=0, sticky="ew", padx=8, pady=(2, 8))

    # ── Inicijalizacija selectora ──────────────────────────────

    def _init_selectors(self) -> None:
        families = get_families(self.cable_db)
        if not families:
            families = ["—"]
        self._om_family.configure(values=families)
        if self._var_family.get() not in families:
            self._var_family.set(families[0])
        self._on_family_change()

    def _on_family_change(self) -> None:
        family = self._var_family.get()
        configs = get_configs_for_family(self.cable_db, family)
        if not configs:
            configs = ["—"]
        self._om_config.configure(values=configs)
        if self._var_config.get() not in configs:
            self._var_config.set(configs[0])
        self._refresh_table()

    # ── Refresh tablice ────────────────────────────────────────

    def _refresh_table(self) -> None:
        for w in self._table_frame.winfo_children():
            w.destroy()
        self._selected_section = None
        self._selected_row = None

        family = self._var_family.get()
        config = self._var_config.get()
        if config == "—":
            config = ""
        full_key = get_full_key(family, config)

        info = self.cable_db.get(full_key, {})
        self._lbl_opis.configure(text=info.get("opis", ""))

        sections = get_sections(self.cable_db, full_key)
        for i, p in enumerate(sections):
            mm2  = p["mm2"]
            zrak = p.get("zrak", 0) or 0
            zem  = p.get("zemlja", 0) or 0
            bg   = ROW_EVEN if i % 2 == 0 else ROW_ODD

            for col, val in enumerate([
                f"{mm2:g}",
                f"{zrak:.0f}" if zrak else "—",
                f"{zem:.0f}"  if zem  else "—",
            ]):
                lbl = ctk.CTkLabel(
                    self._table_frame, text=val,
                    fg_color=bg, text_color=C_VAL,
                    font=ctk.CTkFont(size=11),
                    corner_radius=0,
                )
                lbl.grid(row=i, column=col, padx=1, pady=0, sticky="ew")
                lbl.bind("<Button-1>", lambda e, idx=i, s=mm2: self._select_row(idx, s))

    def _select_row(self, idx: int, section: float) -> None:
        self._selected_section = section
        self._selected_row = idx
        # Vizualni highlight
        for widget in self._table_frame.winfo_children():
            info = widget.grid_info()
            row_idx = int(info.get("row", -1))
            if row_idx == idx:
                widget.configure(fg_color=ROW_SEL)
            else:
                widget.configure(fg_color=ROW_EVEN if row_idx % 2 == 0 else ROW_ODD)

    def _apply_to_board(self) -> None:
        family = self._var_family.get()
        config = self._var_config.get()
        if family == "—":
            messagebox.showinfo("Nema selekcije", "Odaberi vrstu kabela.")
            return
        if self._selected_section is None:
            messagebox.showinfo("Nema selekcije", "Klikni na redak u tablici za odabir presjeka.")
            return
        config_clean = "" if config == "—" else config
        full_key = get_full_key(family, config_clean)
        self.on_apply(full_key, self._selected_section)

    def _open_editor(self) -> None:
        editor = CableDBEditor(self, self.cable_db, self._on_db_saved)
        editor.grab_set()

    def _on_db_saved(self) -> None:
        save_db(self.cable_db)
        self.refresh()
        self.on_db_changed()


# ══════════════════════════════════════════════════════════════
#  Editor baze kabela (popup)
# ══════════════════════════════════════════════════════════════

class CableDBEditor(ctk.CTkToplevel):
    """Popup dialog za uređivanje baze kabela."""

    def __init__(self, parent, cable_db: dict, on_save: Callable) -> None:
        super().__init__(parent)
        self.title("Uredi bazu kabela")
        self.geometry("740x560")
        self.resizable(True, True)
        self.configure(fg_color="#0C1A28")

        self.cable_db = cable_db
        self.on_save  = on_save
        self._sel_type: Optional[str] = None
        self._sec_vars: list = []
        self._sel_sec_idx: Optional[int] = None

        self._build_ui()
        types = get_cable_types(cable_db)
        if types:
            self._sel_type = types[0]
            self._refresh_type_list()
            self._load_sections(types[0])

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1, minsize=200)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)

        # ── Lijevo: lista tipova ──────────────────────────────
        left = ctk.CTkFrame(self, fg_color="#071420", corner_radius=8)
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 4), pady=10)
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(left, text="Tipovi kabela",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#E3F2FD") \
            .grid(row=0, column=0, padx=8, pady=(8, 4), sticky="w")

        self._type_list = ctk.CTkScrollableFrame(left, fg_color="#050E18")
        self._type_list.grid(row=1, column=0, sticky="nsew", padx=6, pady=4)
        self._type_list.grid_columnconfigure(0, weight=1)

        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew", padx=6, pady=6)
        btn_row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(btn_row, text="+ Novi", command=self._add_type,
                      fg_color="#1B3A1B", hover_color="#388E3C", width=0) \
            .grid(row=0, column=0, padx=(0, 2), sticky="ew")
        ctk.CTkButton(btn_row, text="Obriši", command=self._del_type,
                      fg_color="#3E1414", hover_color="#C62828", width=0) \
            .grid(row=0, column=1, padx=(2, 0), sticky="ew")

        # ── Desno: presjeci ───────────────────────────────────
        right = ctk.CTkFrame(self, fg_color="#071420", corner_radius=8)
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 10), pady=10)
        right.grid_rowconfigure(3, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self._lbl_cur_type = ctk.CTkLabel(right, text="—",
                                           font=ctk.CTkFont(size=12, weight="bold"),
                                           text_color="#1E88E5")
        self._lbl_cur_type.grid(row=0, column=0, padx=8, pady=(8, 2), sticky="w")

        self._var_opis = tk.StringVar()
        ctk.CTkEntry(right, textvariable=self._var_opis, placeholder_text="Opis kabela...") \
            .grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))

        # Header
        hdr = ctk.CTkFrame(right, fg_color="#0F2030")
        hdr.grid(row=2, column=0, sticky="ew", padx=8)
        for col, txt in enumerate(["mm²", "Zrak (A)", "Zemlja (A)"]):
            hdr.grid_columnconfigure(col, weight=1)
            ctk.CTkLabel(hdr, text=txt, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#1E88E5") \
                .grid(row=0, column=col, padx=4, pady=3)

        self._sec_frame = ctk.CTkScrollableFrame(right, fg_color="#050E18")
        self._sec_frame.grid(row=3, column=0, sticky="nsew", padx=8, pady=4)
        self._sec_frame.grid_columnconfigure((0, 1, 2), weight=1)

        sec_btn = ctk.CTkFrame(right, fg_color="transparent")
        sec_btn.grid(row=4, column=0, sticky="ew", padx=8, pady=4)
        sec_btn.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(sec_btn, text="+ Dodaj presjek", command=self._add_section,
                      fg_color="#1B3A1B", hover_color="#388E3C", width=0) \
            .grid(row=0, column=0, padx=(0, 2), sticky="ew")
        ctk.CTkButton(sec_btn, text="Obriši označeni", command=self._del_section,
                      fg_color="#3E1414", hover_color="#C62828", width=0) \
            .grid(row=0, column=1, padx=(2, 0), sticky="ew")

        # ── Dno ──────────────────────────────────────────────
        bot = ctk.CTkFrame(self, fg_color="transparent")
        bot.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        ctk.CTkButton(bot, text="Spremi i zatvori", command=self._save,
                      fg_color="#1565C0", hover_color="#1E88E5") \
            .pack(side="right", padx=(4, 0))
        ctk.CTkButton(bot, text="Odustani", command=self.destroy,
                      fg_color="#263238", hover_color="#455A64") \
            .pack(side="right")

    def _refresh_type_list(self) -> None:
        for w in self._type_list.winfo_children():
            w.destroy()
        for t in get_cable_types(self.cable_db):
            is_sel = t == self._sel_type
            ctk.CTkButton(
                self._type_list, text=t, anchor="w",
                fg_color=C_SEL if is_sel else "transparent",
                hover_color="#1E3A5F",
                font=ctk.CTkFont(size=11),
                command=lambda name=t: self._select_type(name),
            ).pack(fill="x", padx=2, pady=1)

    def _select_type(self, name: str) -> None:
        self._save_current_sections()
        self._sel_type = name
        self._refresh_type_list()
        self._load_sections(name)

    def _load_sections(self, cable_type: str) -> None:
        for w in self._sec_frame.winfo_children():
            w.destroy()
        self._sec_vars.clear()
        self._sel_sec_idx = None
        info = self.cable_db.get(cable_type, {})
        self._lbl_cur_type.configure(text=cable_type)
        self._var_opis.set(info.get("opis", ""))
        for i, p in enumerate(info.get("presjeci", [])):
            self._add_section_row(i, p["mm2"], p.get("zrak", 0) or 0, p.get("zemlja", 0) or 0)

    def _add_section_row(self, idx: int, mm2=0, zrak=0, zemlja=0) -> None:
        v_mm2    = tk.StringVar(value=str(mm2))
        v_zrak   = tk.StringVar(value=str(int(zrak)) if zrak else "0")
        v_zemlja = tk.StringVar(value=str(int(zemlja)) if zemlja else "0")
        self._sec_vars.append((v_mm2, v_zrak, v_zemlja))
        for col, (var, w) in enumerate([(v_mm2, 60), (v_zrak, 70), (v_zemlja, 70)]):
            ent = ctk.CTkEntry(self._sec_frame, textvariable=var, width=w)
            ent.grid(row=idx, column=col, padx=3, pady=2, sticky="ew")
            ent.bind("<Button-1>", lambda e, i=idx: self._sel_row(i))

    def _sel_row(self, idx: int) -> None:
        self._sel_sec_idx = idx

    def _add_section(self) -> None:
        if self._sel_type:
            self._add_section_row(len(self._sec_vars))

    def _del_section(self) -> None:
        if self._sel_sec_idx is None or not self._sel_type:
            messagebox.showinfo("Nema selekcije", "Klikni na redak za odabir.")
            return
        del self._sec_vars[self._sel_sec_idx]
        self._sel_sec_idx = None
        ct = self._sel_type
        self._save_current_sections()
        self._load_sections(ct)

    def _add_type(self) -> None:
        dialog = ctk.CTkInputDialog(text="Naziv novog kabela (npr. NYY-J 3G):", title="Novi kabel")
        name = dialog.get_input()
        if name and name.strip():
            name = name.strip()
            if name not in self.cable_db:
                self.cable_db[name] = {"naziv": name, "opis": "", "presjeci": []}
            self._sel_type = name
            self._refresh_type_list()
            self._load_sections(name)

    def _del_type(self) -> None:
        if not self._sel_type:
            return
        if messagebox.askyesno("Brisanje", f"Obrisati '{self._sel_type}'?"):
            del self.cable_db[self._sel_type]
            self._sel_type = None
            types = get_cable_types(self.cable_db)
            if types:
                self._sel_type = types[0]
            self._refresh_type_list()
            if self._sel_type:
                self._load_sections(self._sel_type)
            else:
                self._lbl_cur_type.configure(text="—")

    def _save_current_sections(self) -> None:
        if not self._sel_type:
            return
        presjeci = []
        for v_mm2, v_zrak, v_zemlja in self._sec_vars:
            try:
                presjeci.append({
                    "mm2":    float(v_mm2.get()),
                    "zrak":   float(v_zrak.get() or 0),
                    "zemlja": float(v_zemlja.get() or 0),
                })
            except ValueError:
                pass
        presjeci.sort(key=lambda x: x["mm2"])
        if self._sel_type not in self.cable_db:
            self.cable_db[self._sel_type] = {}
        self.cable_db[self._sel_type]["presjeci"] = presjeci
        self.cable_db[self._sel_type]["opis"]     = self._var_opis.get()
        self.cable_db[self._sel_type]["naziv"]    = self._sel_type

    def _save(self) -> None:
        self._save_current_sections()
        self.on_save()
        self.destroy()
