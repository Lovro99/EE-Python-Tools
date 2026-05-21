from __future__ import annotations
from typing import Callable, Optional, List, TYPE_CHECKING

import customtkinter as ctk
import tkinter as tk

if TYPE_CHECKING:
    from .models import DistributionBoard

from .models import (
    PROTECTION_TYPES, STANDARD_CABLE_SECTIONS,
    STANDARD_FUSE_RATINGS, FID_SENSITIVITIES,
)

LABEL_COLOR   = "#90A4AE"
CALC_COLOR    = "#4CAF50"
CALC_WARN     = "#FF8C00"
CALC_OVL      = "#F44336"
SECTION_COLOR = "#1E88E5"
BG_COLOR      = "#0F2030"


def _fmt(val: float, d: int = 2) -> str:
    return f"{val:.{d}f}"


class PropertiesPanel(ctk.CTkScrollableFrame):
    """Desni panel za uređivanje odabranog ormara."""

    def __init__(
        self,
        parent,
        on_change: Callable[[], None],
        get_cable_types: Callable[[], List[str]] = None,
    ) -> None:
        super().__init__(parent, width=300, fg_color=BG_COLOR, corner_radius=0)
        self.on_change       = on_change
        self._get_cable_types = get_cable_types or (lambda: [])
        self._board: Optional["DistributionBoard"] = None
        self._cable_db: dict = {}
        self._updating = False

        self._build_ui()
        self._show_empty()

    # ── Javno sučelje ─────────────────────────────────────────

    def load_board(self, board: "DistributionBoard") -> None:
        self._board = board
        self._updating = True
        try:
            self._var_name.set(board.name)
            self._seg_phase.set(board.phase)
            self._seg_voltage.set(str(board.voltage))
            self._var_power.set(_fmt(board.installed_power_kw))
            self._slider_sim.set(board.simultaneity_factor)
            self._var_sim.set(_fmt(board.simultaneity_factor))

            # Kabel — raščlani tip na obitelj + konfiguraciju
            self._refresh_family_list()
            family, config = self._parse_cable_type(board.cable_type)
            self._set_family_and_config(family, config)

            self._opt_section.set(str(board.cable_section_mm2))
            self._var_length.set(_fmt(board.cable_length_m))
            self._seg_count.set(str(board.cable_count))
            self._seg_method.set(board.install_method)
            self._var_safety.set(_fmt(board.cable_safety_factor))

            self._opt_prot_type.set(board.protection_type)
            self._opt_prot_rating.set(str(int(board.protection_rating_a)))
            self._var_fid.set(str(int(board.fid_sensitivity_ma)))
            self._update_fid_visibility(board.protection_type)
            self._refresh_calc_labels(board)
        finally:
            self._updating = False

        self._frame_props.grid()
        self._lbl_empty.grid_remove()
        self._lbl_board_title.configure(text=f"Ormar: {board.name}")

    def clear(self) -> None:
        self._board = None
        self._show_empty()

    def refresh_cable_types(self) -> None:
        """Osvježi listu tipova kabela (kad se baza promijeni)."""
        self._refresh_family_list()
        if self._board:
            family, config = self._parse_cable_type(self._board.cable_type)
            self._set_family_and_config(family, config)

    def set_cable_db(self, cable_db: dict) -> None:
        self._cable_db = cable_db

    # ── Interna logika kabela ─────────────────────────────────

    def _parse_cable_type(self, cable_type: str):
        """Razdvoji "FG16OR16 3G" → ("FG16OR16", "3G")."""
        try:
            from .cable_db import parse_cable_name
        except ImportError:
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from ormari.cable_db import parse_cable_name
        return parse_cable_name(cable_type)

    def _get_families(self) -> List[str]:
        try:
            from .cable_db import get_families
        except ImportError:
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from ormari.cable_db import get_families
        families = get_families(self._cable_db)
        return families if families else ["NYY-J"]

    def _get_configs(self, family: str) -> List[str]:
        try:
            from .cable_db import get_configs_for_family
        except ImportError:
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from ormari.cable_db import get_configs_for_family
        configs = get_configs_for_family(self._cable_db, family)
        return configs if configs else ["3G"]

    def _refresh_family_list(self) -> None:
        families = self._get_families()
        self._om_family.configure(values=families)

    def _set_family_and_config(self, family: str, config: str) -> None:
        families = self._get_families()
        if family not in families and families:
            family = families[0]
        self._var_family.set(family)
        configs = self._get_configs(family)
        self._om_config.configure(values=configs if configs else ["—"])
        if config not in configs and configs:
            config = configs[0]
        self._var_config.set(config)

    def _on_family_change(self) -> None:
        if self._updating:
            return
        family = self._var_family.get()
        configs = self._get_configs(family)
        self._om_config.configure(values=configs if configs else ["—"])
        if self._var_config.get() not in configs and configs:
            self._var_config.set(configs[0])
        self._apply()

    def _get_full_cable_type(self) -> str:
        family = self._var_family.get()
        config = self._var_config.get()
        if config and config != "—":
            return f"{family} {config}"
        return family

    # ── Izgradnja UI ─────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Svojstva ormara",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#E3F2FD") \
            .grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 2))

        self._lbl_board_title = ctk.CTkLabel(self, text="",
                                              font=ctk.CTkFont(size=11),
                                              text_color=SECTION_COLOR)
        self._lbl_board_title.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))

        self._lbl_empty = ctk.CTkLabel(self, text="Odaberi ormar na shemi",
                                        text_color=LABEL_COLOR, font=ctk.CTkFont(size=11))
        self._lbl_empty.grid(row=2, column=0, padx=10, pady=20)

        self._frame_props = ctk.CTkFrame(self, fg_color="transparent")
        self._frame_props.grid(row=3, column=0, sticky="ew", padx=6)
        self._frame_props.grid_columnconfigure(1, weight=1)

        r = 0

        # ── Identifikacija ────────────────────────────────────
        r = self._section(r, "IDENTIFIKACIJA")
        self._var_name = tk.StringVar()
        r = self._fe(r, "Naziv:", self._var_name, self._on_name_change)

        # ── Električno ────────────────────────────────────────
        r = self._section(r, "ELEKTRIČNO")
        self._seg_phase = ctk.StringVar(value="3F")
        r = self._fs_btn(r, "Faznost:", self._seg_phase, ["1F", "3F"], self._on_phase_change)

        self._seg_voltage = ctk.StringVar(value="400")
        r = self._fs_btn(r, "Napon (V):", self._seg_voltage, ["230", "400"], self._on_voltage_change)

        self._var_power = tk.StringVar()
        r = self._fe(r, "P direktna (kW):", self._var_power, self._apply)

        r = self._slbl(r, "Faktor istovremenosti:")
        self._slider_sim = ctk.CTkSlider(
            self._frame_props, from_=0.1, to=1.0, number_of_steps=90,
            command=self._on_slider_sim,
        )
        self._slider_sim.grid(row=r, column=0, columnspan=2, sticky="ew", padx=6, pady=2)
        r += 1
        self._var_sim = tk.StringVar()
        ent_sim = ctk.CTkEntry(self._frame_props, textvariable=self._var_sim, width=70)
        ent_sim.grid(row=r, column=1, sticky="e", padx=6, pady=2)
        ent_sim.bind("<Return>",   lambda e: self._on_sim_entry())
        ent_sim.bind("<FocusOut>", lambda e: self._on_sim_entry())
        r += 1

        # ── Kabel ────────────────────────────────────────────
        r = self._section(r, "KABEL (dolazni)")

        # Obitelj kabela
        ctk.CTkLabel(self._frame_props, text="Vrsta kabela:", text_color=LABEL_COLOR, anchor="w") \
            .grid(row=r, column=0, sticky="w", padx=6, pady=2)
        self._var_family = ctk.StringVar(value="NYY-J")
        self._om_family = ctk.CTkOptionMenu(
            self._frame_props, variable=self._var_family, values=["NYY-J"],
            command=lambda _: self._on_family_change(),
        )
        self._om_family.grid(row=r, column=1, sticky="ew", padx=6, pady=2)
        r += 1

        # Konfiguracija žila
        ctk.CTkLabel(self._frame_props, text="Žile / konfiguracija:", text_color=LABEL_COLOR, anchor="w") \
            .grid(row=r, column=0, sticky="w", padx=6, pady=2)
        self._var_config = ctk.StringVar(value="3G")
        self._om_config = ctk.CTkOptionMenu(
            self._frame_props, variable=self._var_config, values=["3G"],
            command=lambda _: self._apply(),
        )
        self._om_config.grid(row=r, column=1, sticky="ew", padx=6, pady=2)
        r += 1

        self._opt_section = ctk.StringVar(value="2.5")
        r = self._fo(r, "Presjek (mm²):", self._opt_section,
                     [str(s) for s in STANDARD_CABLE_SECTIONS], self._apply)

        self._var_length = tk.StringVar()
        r = self._fe(r, "Duljina (m):", self._var_length, self._apply)

        self._seg_count = ctk.StringVar(value="1")
        r = self._fs_btn(r, "Br. paralelnih kabela:", self._seg_count, ["1", "2"], self._apply)

        self._seg_method = ctk.StringVar(value="zrak")
        r = self._fs_btn(r, "Postavljanje:", self._seg_method, ["zrak", "zemlja"], self._apply)

        self._var_safety = tk.StringVar(value="1.25")
        r = self._fe(r, "Faktor sigurnosti (Ib/I):", self._var_safety, self._apply)

        # ── Zaštita ──────────────────────────────────────────
        r = self._section(r, "ZAŠTITA")
        self._opt_prot_type = ctk.StringVar(value="Prekidač")
        r = self._fo(r, "Tip zaštite:", self._opt_prot_type, PROTECTION_TYPES,
                     self._on_prot_type_change)

        self._opt_prot_rating = ctk.StringVar(value="16")
        r = self._fo(r, "Struja zaštite (A):", self._opt_prot_rating,
                     [str(int(v)) for v in STANDARD_FUSE_RATINGS], self._apply)

        # FID osjetljivost
        self._lbl_fid = ctk.CTkLabel(self._frame_props, text="FID osjetl. (mA):",
                                      text_color=LABEL_COLOR, anchor="w")
        self._var_fid = tk.StringVar(value="30")
        self._opt_fid = ctk.CTkOptionMenu(
            self._frame_props, variable=self._var_fid,
            values=[str(int(v)) for v in FID_SENSITIVITIES],
            command=lambda _: self._apply(),
        )
        self._lbl_fid_row = r
        r += 1

        # ── Gumbi ─────────────────────────────────────────────
        bf = ctk.CTkFrame(self._frame_props, fg_color="transparent")
        bf.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(10, 4))
        bf.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(bf, text="Primijeni", command=self._apply,
                      fg_color="#1565C0", hover_color="#1E88E5") \
            .grid(row=0, column=0, padx=(0, 3), sticky="ew")
        ctk.CTkButton(bf, text="Preporučene vrijednosti", command=self._apply_recommended,
                      fg_color="#1B5E20", hover_color="#388E3C") \
            .grid(row=0, column=1, padx=(3, 0), sticky="ew")
        r += 1

        # ── Izračunato ────────────────────────────────────────
        r = self._section(r, "IZRAČUNATO")
        self._calc_labels: dict[str, ctk.CTkLabel] = {}
        for key, lbl in [
            ("total_kw",   "P_uk ukupno (kW):"),
            ("corr_kw",    "P_v korigirano (kW):"),
            ("current_a",  "I (A):"),
            ("ampacity",   "Ib kabela (A):"),
            ("cable_st",   "Status kabela:"),
            ("breaker_st", "Status prekidača:"),
            ("rec_sec",    "Preporučeni presjek (mm²):"),
            ("rec_fuse",   "Preporučena zaštita (A):"),
        ]:
            ctk.CTkLabel(self._frame_props, text=lbl, text_color=LABEL_COLOR,
                         anchor="w", font=ctk.CTkFont(size=11)) \
                .grid(row=r, column=0, sticky="w", padx=6, pady=1)
            lv = ctk.CTkLabel(self._frame_props, text="—", text_color=CALC_COLOR,
                              anchor="e", font=ctk.CTkFont(size=11, weight="bold"))
            lv.grid(row=r, column=1, sticky="e", padx=6, pady=1)
            self._calc_labels[key] = lv
            r += 1

    # ── Widget helper ─────────────────────────────────────────

    def _section(self, r: int, text: str) -> int:
        ctk.CTkFrame(self._frame_props, height=1, fg_color="#263238") \
            .grid(row=r, column=0, columnspan=2, sticky="ew", pady=(8, 2))
        r += 1
        ctk.CTkLabel(self._frame_props, text=text, text_color=SECTION_COLOR,
                     font=ctk.CTkFont(size=10, weight="bold"), anchor="w") \
            .grid(row=r, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 4))
        return r + 1

    def _slbl(self, r: int, text: str) -> int:
        ctk.CTkLabel(self._frame_props, text=text, text_color=LABEL_COLOR, anchor="w") \
            .grid(row=r, column=0, columnspan=2, sticky="w", padx=6, pady=(4, 0))
        return r + 1

    def _fe(self, r: int, label: str, var: tk.StringVar, cmd) -> int:
        ctk.CTkLabel(self._frame_props, text=label, text_color=LABEL_COLOR, anchor="w") \
            .grid(row=r, column=0, sticky="w", padx=6, pady=2)
        ent = ctk.CTkEntry(self._frame_props, textvariable=var)
        ent.grid(row=r, column=1, sticky="ew", padx=6, pady=2)
        ent.bind("<Return>",   lambda e: cmd())
        ent.bind("<FocusOut>", lambda e: cmd())
        return r + 1

    def _fs_btn(self, r: int, label: str, var, values: list, cmd) -> int:
        ctk.CTkLabel(self._frame_props, text=label, text_color=LABEL_COLOR, anchor="w") \
            .grid(row=r, column=0, sticky="w", padx=6, pady=2)
        ctk.CTkSegmentedButton(self._frame_props, values=values, variable=var,
                               command=lambda _: cmd()) \
            .grid(row=r, column=1, sticky="ew", padx=6, pady=2)
        return r + 1

    def _fo(self, r: int, label: str, var, values: list, cmd) -> int:
        ctk.CTkLabel(self._frame_props, text=label, text_color=LABEL_COLOR, anchor="w") \
            .grid(row=r, column=0, sticky="w", padx=6, pady=2)
        ctk.CTkOptionMenu(self._frame_props, variable=var, values=values,
                          command=lambda _: cmd()) \
            .grid(row=r, column=1, sticky="ew", padx=6, pady=2)
        return r + 1

    # ── Callbackovi ──────────────────────────────────────────

    def _on_name_change(self) -> None:
        if self._board and not self._updating:
            self._board.name = self._var_name.get().strip() or "Ormar"
            self.on_change()

    def _on_phase_change(self) -> None:
        if self._updating:
            return
        self._updating = True
        self._seg_voltage.set("230" if self._seg_phase.get() == "1F" else "400")
        self._updating = False
        self._apply()

    def _on_voltage_change(self) -> None:
        if self._updating:
            return
        self._updating = True
        self._seg_phase.set("1F" if self._seg_voltage.get() == "230" else "3F")
        self._updating = False
        self._apply()

    def _on_slider_sim(self, val: float) -> None:
        if not self._updating:
            self._var_sim.set(_fmt(val))
            self._apply()

    def _on_sim_entry(self) -> None:
        try:
            val = max(0.1, min(1.0, float(self._var_sim.get())))
            self._updating = True
            self._slider_sim.set(val)
            self._var_sim.set(_fmt(val))
            self._updating = False
            self._apply()
        except ValueError:
            pass

    def _on_prot_type_change(self) -> None:
        self._update_fid_visibility(self._opt_prot_type.get())
        self._apply()

    def _update_fid_visibility(self, ptype: str) -> None:
        r = self._lbl_fid_row
        if ptype == "FID":
            self._lbl_fid.grid(row=r, column=0, sticky="w", padx=6, pady=2)
            self._opt_fid.grid(row=r, column=1, sticky="ew", padx=6, pady=2)
        else:
            self._lbl_fid.grid_remove()
            self._opt_fid.grid_remove()

    def _apply(self) -> None:
        if self._board is None or self._updating:
            return
        try:
            self._board.name               = self._var_name.get().strip() or "Ormar"
            self._board.phase              = self._seg_phase.get()
            self._board.voltage            = int(self._seg_voltage.get())
            self._board.installed_power_kw = float(self._var_power.get() or 0)
            self._board.simultaneity_factor= float(self._var_sim.get() or 0.7)
            self._board.cable_type         = self._get_full_cable_type()
            self._board.cable_section_mm2  = float(self._opt_section.get())
            self._board.cable_length_m     = float(self._var_length.get() or 0)
            self._board.cable_count        = int(self._seg_count.get())
            self._board.install_method     = self._seg_method.get()
            self._board.cable_safety_factor= float(self._var_safety.get() or 1.25)
            self._board.protection_type    = self._opt_prot_type.get()
            self._board.protection_rating_a= float(self._opt_prot_rating.get())
            self._board.fid_sensitivity_ma = float(self._var_fid.get() or 30)
        except ValueError:
            return
        self.on_change()
        self._refresh_calc_labels(self._board)
        self._lbl_board_title.configure(text=f"Ormar: {self._board.name}")

    def _apply_recommended(self) -> None:
        if not self._board:
            return
        sec = str(self._board.calc_rec_section_mm2)
        avail = [str(s) for s in STANDARD_CABLE_SECTIONS]
        if sec not in avail:
            target = self._board.calc_rec_section_mm2
            sec = min(avail, key=lambda x: (float(x) < target, abs(float(x) - target)))
        self._opt_section.set(sec)
        rec = int(self._board.calc_rec_fuse_a)
        opts = [str(int(v)) for v in STANDARD_FUSE_RATINGS]
        self._opt_prot_rating.set(min(opts, key=lambda x: abs(int(x) - rec)))
        self._apply()

    def _refresh_calc_labels(self, board: "DistributionBoard") -> None:
        self._calc_labels["total_kw"].configure(text=f"{board.calc_total_installed_kw:.2f}")
        self._calc_labels["corr_kw"].configure(text=f"{board.calc_corrected_power_kw:.2f}")
        self._calc_labels["current_a"].configure(text=f"{board.calc_current_a:.2f}")
        self._calc_labels["rec_sec"].configure(text=str(board.calc_rec_section_mm2))
        self._calc_labels["rec_fuse"].configure(text=f"{board.calc_rec_fuse_a:.0f}")

        if not self._cable_db:
            for k in ("ampacity", "cable_st", "breaker_st"):
                self._calc_labels[k].configure(text="—", text_color=CALC_COLOR)
            return

        try:
            from .cable_db import get_effective_ampacity, cable_status, breaker_check
        except ImportError:
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from ormari.cable_db import get_effective_ampacity, cable_status, breaker_check

        ib = get_effective_ampacity(
            self._cable_db, board.cable_type, board.cable_section_mm2,
            board.install_method, board.cable_count,
        )
        self._calc_labels["ampacity"].configure(
            text=f"{ib:.0f}" if ib > 0 else "?",
            text_color=CALC_COLOR,
        )

        # Status kabela
        cab_st = cable_status(
            self._cable_db, board.cable_type, board.cable_section_mm2,
            board.install_method, board.cable_count,
            board.calc_current_a, board.cable_safety_factor,
        )
        cab_txt   = {"ok": "OK", "warning": "Pažnja — ispod faktora", "overload": "PREOPTEREĆEN!"}[cab_st]
        cab_color = {"ok": CALC_COLOR, "warning": CALC_WARN, "overload": CALC_OVL}[cab_st]
        self._calc_labels["cable_st"].configure(text=cab_txt, text_color=cab_color)

        # Status prekidača (Ib ≤ In ≤ Iz)
        brk_st = breaker_check(
            board.protection_type, board.protection_rating_a,
            board.calc_current_a, ib,
        )
        brk_txt = {
            "ok":           "OK — Ib ≤ In ≤ Iz",
            "underrated":   "In < Ib — prevelika struja!",
            "overrated":    "In > Iz — kabel nije zaštićen!",
            "no_protection":"Bez zaštite",
        }.get(brk_st, "—")
        brk_color = {
            "ok": CALC_COLOR, "underrated": CALC_OVL,
            "overrated": CALC_OVL, "no_protection": CALC_WARN,
        }.get(brk_st, CALC_COLOR)
        self._calc_labels["breaker_st"].configure(text=brk_txt, text_color=brk_color)

    def _show_empty(self) -> None:
        self._lbl_board_title.configure(text="")
        self._lbl_empty.grid()
        self._frame_props.grid_remove()
