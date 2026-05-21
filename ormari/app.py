"""
Razvodne ploče – Kalkulator i shema
Pokretanje: python ormari/app.py  ili  python -m ormari.app
"""
from __future__ import annotations
import sys, os, tkinter as tk
from tkinter import filedialog, messagebox
from typing import Optional

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import customtkinter as ctk

# Podrška za direktno pokretanje i kao modul
if __package__ is None or __package__ == "":
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(_here))
    from ormari.models       import DistributionBoard, Project
    from ormari.calculations import recalculate_all
    from ormari.canvas       import SchematicCanvas, BOX_W, BOX_H
    from ormari.persistence  import save_project, load_project
    from ormari.export       import export_image, export_pdf, export_csv
    from ormari.properties_panel import PropertiesPanel
    from ormari.cable_panel  import CablePanel
    from ormari.cable_db     import load_db, save_db, get_cable_types
else:
    from .models       import DistributionBoard, Project
    from .calculations import recalculate_all
    from .canvas       import SchematicCanvas, BOX_W, BOX_H
    from .persistence  import save_project, load_project
    from .export       import export_image, export_pdf, export_csv
    from .properties_panel import PropertiesPanel
    from .cable_panel  import CablePanel
    from .cable_db     import load_db, save_db, get_cable_types

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

C_BG     = "#0C1A28"
C_TB     = "#071420"
C_STATUS = "#050E18"


# ══════════════════════════════════════════════════════════════
#  ZoomPan
# ══════════════════════════════════════════════════════════════

class ZoomPan:
    """Kotačić=zoom | Desni klik+drag=pan | R/Home=reset."""

    def __init__(self, ax, scale: float = 1.25, on_zoom=None) -> None:
        self.ax       = ax
        self.scale    = scale
        self._on_zoom = on_zoom   # callback po zoom/reset
        self._press   = None
        self._orig    = None
        c = ax.figure.canvas
        c.mpl_connect("scroll_event",         self._scroll)
        c.mpl_connect("button_press_event",   self._press_ev)
        c.mpl_connect("button_release_event", self._release)
        c.mpl_connect("motion_notify_event",  self._motion)
        c.mpl_connect("key_press_event",      self._key)

    def save_home(self) -> None:
        self._orig = (self.ax.get_xlim(), self.ax.get_ylim())

    def _scroll(self, ev) -> None:
        if ev.inaxes != self.ax or ev.xdata is None:
            return
        f = 1 / self.scale if ev.button == "up" else self.scale
        xl, yl = self.ax.get_xlim(), self.ax.get_ylim()
        self.ax.set_xlim(ev.xdata - (ev.xdata - xl[0]) * f,
                         ev.xdata + (xl[1] - ev.xdata) * f)
        self.ax.set_ylim(ev.ydata - (ev.ydata - yl[0]) * f,
                         ev.ydata + (yl[1] - ev.ydata) * f)
        if self._on_zoom:
            self._on_zoom()
        else:
            self.ax.figure.canvas.draw_idle()

    def _press_ev(self, ev) -> None:
        if ev.inaxes == self.ax and ev.button == 3 and ev.xdata is not None:
            self._press = (ev.xdata, ev.ydata,
                           self.ax.get_xlim(), self.ax.get_ylim())

    def _release(self, ev) -> None:
        self._press = None

    def _motion(self, ev) -> None:
        if self._press is None or ev.inaxes != self.ax or ev.xdata is None:
            return
        x0, y0, xl, yl = self._press
        dx, dy = ev.xdata - x0, ev.ydata - y0
        self.ax.set_xlim(xl[0] - dx, xl[1] - dx)
        self.ax.set_ylim(yl[0] - dy, yl[1] - dy)
        self.ax.figure.canvas.draw_idle()

    def _key(self, ev) -> None:
        if ev.key in ("r", "R", "home") and self._orig:
            self.ax.set_xlim(self._orig[0])
            self.ax.set_ylim(self._orig[1])
            if self._on_zoom:
                self._on_zoom()
            else:
                self.ax.figure.canvas.draw_idle()


# ══════════════════════════════════════════════════════════════
#  Auto-raspored stabla
# ══════════════════════════════════════════════════════════════

def _auto_layout_tree(project: Project) -> None:
    LEVEL_H = 200
    H_GAP   = 50

    def subtree_width(bid: str) -> float:
        board = project.boards[bid]
        if not board.children_ids:
            return float(BOX_W)
        total = sum(subtree_width(c) for c in board.children_ids if c in project.boards)
        return max(float(BOX_W), total + H_GAP * max(0, len(board.children_ids) - 1))

    def place(bid: str, x_center: float, y: float) -> None:
        board = project.boards[bid]
        board.canvas_x = x_center - BOX_W / 2
        board.canvas_y = y
        children = [c for c in board.children_ids if c in project.boards]
        if not children:
            return
        total_w  = sum(subtree_width(c) for c in children)
        span     = total_w + H_GAP * (len(children) - 1)
        cx       = x_center - span / 2
        for cid in children:
            sw = subtree_width(cid)
            place(cid, cx + sw / 2, y - LEVEL_H)
            cx += sw + H_GAP

    if project.root_board_id and project.root_board_id in project.boards:
        place(project.root_board_id, 500, 600)

    root_ids = {project.root_board_id}
    if project.root_board_id:
        root_ids |= set(project.get_all_descendants(project.root_board_id))
    loose_x = 900
    for bid, board in project.boards.items():
        if bid not in root_ids:
            board.canvas_x, board.canvas_y = loose_x, 600
            loose_x += BOX_W + H_GAP


# ══════════════════════════════════════════════════════════════
#  Glavni prozor
# ══════════════════════════════════════════════════════════════

class OrmariApp(ctk.CTk):

    def __init__(self) -> None:
        super().__init__()
        self.title("Razvodne ploče – Kalkulator i shema")
        self.geometry("1580x900")
        self.minsize(1100, 650)
        self.configure(fg_color=C_BG)

        # Baza kabela — učitaj jednom, dijeli svim komponentama
        self.cable_db: dict = load_db()

        self.project: Project = Project()
        self._current_file: Optional[str] = None
        self._dirty = False

        self._build_toolbar()
        self._build_main_area()
        self._build_statusbar()
        self._new_project_blank()

    # ── UI izgradnja ──────────────────────────────────────────

    def _build_toolbar(self) -> None:
        tb = ctk.CTkFrame(self, height=52, fg_color=C_TB, corner_radius=0)
        tb.pack(side="top", fill="x")
        tb.pack_propagate(False)

        def btn(text, cmd, color="#1E3A5F", hover="#1E88E5"):
            ctk.CTkButton(tb, text=text, command=cmd, width=0,
                          fg_color=color, hover_color=hover,
                          font=ctk.CTkFont(size=11)) \
                .pack(side="left", padx=3, pady=8)

        def sep():
            ctk.CTkLabel(tb, text="│", text_color="#263238", width=8).pack(side="left")

        btn("Novi",          self._new_project)
        btn("Otvori",        self._open_project)
        btn("Spremi",        self._save_project)
        btn("Spremi kao",    self._save_project_as)
        sep()
        btn("+ GRO",         self._add_root_board,  "#1B3A1B", "#388E3C")
        btn("+ Podormar",    self._add_child_board,  "#1B3A1B", "#388E3C")
        btn("Obriši",        self._delete_board,     "#3E1414", "#C62828")
        sep()
        btn("Export PNG",    self._export_png,       "#1A237E", "#3949AB")
        btn("Export PDF",    self._export_pdf,       "#1A237E", "#3949AB")
        btn("Export CSV",    self._export_csv,       "#1A237E", "#3949AB")
        sep()
        btn("Auto-raspored", self._auto_layout,      "#1A2A3A", "#546E7A")
        btn("Zoom reset (R)",self._reset_zoom,       "#1A2A3A", "#546E7A")

    def _build_main_area(self) -> None:
        pane = tk.PanedWindow(self, orient="horizontal",
                              bg=C_BG, sashwidth=5, sashrelief="flat")
        pane.pack(fill="both", expand=True)

        # ── Lijevo: Cable panel ───────────────────────────────
        cable_container = tk.Frame(pane, bg="#071420")
        self.cable_panel = CablePanel(
            cable_container,
            cable_db=self.cable_db,
            on_apply=self._on_cable_apply,
            on_db_changed=self._on_db_changed,
        )
        self.cable_panel.pack(fill="both", expand=True)
        pane.add(cable_container, minsize=220)

        # ── Sredina: Matplotlib canvas ────────────────────────
        canvas_frame = tk.Frame(pane, bg=C_BG)
        self.fig = Figure(figsize=(10, 7), dpi=100, facecolor=C_BG)
        self.ax  = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_facecolor(C_BG)
        self.ax.axis("off")

        self.mpl_canvas = FigureCanvasTkAgg(self.fig, master=canvas_frame)
        self.mpl_canvas.get_tk_widget().pack(fill="both", expand=True)
        pane.add(canvas_frame, minsize=650)

        self.schematic = SchematicCanvas(
            self.fig, self.ax, self.project,
            on_select=self._on_board_selected,
            cable_db=self.cable_db,
        )

        # ZoomPan — zoom poziva schematic.zoom_redraw za font scaling
        self.zoom_pan = ZoomPan(self.ax, on_zoom=self.schematic.zoom_redraw)

        # ── Desno: Properties panel ───────────────────────────
        props_container = tk.Frame(pane, bg="#0F2030")
        self.props_panel = PropertiesPanel(
            props_container,
            on_change=self._on_props_changed,
            get_cable_types=lambda: get_cable_types(self.cable_db),
        )
        self.props_panel.set_cable_db(self.cable_db)
        self.props_panel.pack(fill="both", expand=True)
        pane.add(props_container, minsize=290)

    def _build_statusbar(self) -> None:
        self._status_var = tk.StringVar(value="Spreman.")
        sb = tk.Frame(self, bg=C_STATUS, height=24)
        sb.pack(side="bottom", fill="x")
        sb.pack_propagate(False)
        tk.Label(sb, textvariable=self._status_var,
                 bg=C_STATUS, fg="#78909C",
                 font=("Segoe UI", 9), anchor="w") \
            .pack(side="left", padx=8, fill="y")

    # ── Projekt ───────────────────────────────────────────────

    def _new_project_blank(self) -> None:
        self.project = Project(name="Novi projekt")
        self.schematic.project = self.project
        self.schematic.set_selected(None)
        self.props_panel.clear()
        self._current_file = None
        self._dirty = False
        recalculate_all(self.project, self.cable_db)
        self.schematic.redraw(fit=True)
        self.zoom_pan.save_home()
        self._set_status("Novi projekt.")
        self._update_title()

    def _new_project(self) -> None:
        if self._dirty and not messagebox.askyesno(
                "Novi projekt", "Postoje nespremene promjene. Nastaviti?"):
            return
        self._new_project_blank()

    def _open_project(self) -> None:
        if self._dirty and not messagebox.askyesno(
                "Otvori", "Postoje nespremene promjene. Nastaviti?"):
            return
        path = filedialog.askopenfilename(
            title="Otvori projekt",
            filetypes=[("Projekt ormara", "*.ormar"), ("JSON", "*.json"), ("Sve", "*.*")],
        )
        if not path:
            return
        try:
            self.project = load_project(path)
            self.schematic.project = self.project
            self.schematic.set_selected(None)
            self.props_panel.clear()
            self._current_file = path
            self._dirty = False
            recalculate_all(self.project, self.cable_db)
            self.schematic.redraw(fit=True)
            self.zoom_pan.save_home()
            self._set_status(f"Ucitano: {path}")
            self._update_title()
        except Exception as e:
            messagebox.showerror("Greška", f"Nije moguće učitati:\n{e}")

    def _save_project(self) -> None:
        if self._current_file:
            self._do_save(self._current_file)
        else:
            self._save_project_as()

    def _save_project_as(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Spremi projekt",
            defaultextension=".ormar",
            filetypes=[("Projekt ormara", "*.ormar"), ("JSON", "*.json")],
        )
        if path:
            self._do_save(path)

    def _do_save(self, path: str) -> None:
        try:
            save_project(self.project, path)
            self._current_file = path
            self._dirty = False
            self._set_status(f"Spremljeno: {path}")
            self._update_title()
        except Exception as e:
            messagebox.showerror("Greška", f"Nije moguće spremiti:\n{e}")

    # ── Ormar akcije ──────────────────────────────────────────

    def _add_root_board(self) -> None:
        board = DistributionBoard(name="GRO", canvas_x=400, canvas_y=500)
        self.project.boards[board.id] = board
        if self.project.root_board_id is None:
            self.project.root_board_id = board.id
        recalculate_all(self.project, self.cable_db)
        # fit=True → postavi referentni zoom i pokaži ploču na ekranu
        self.schematic.redraw(fit=True)
        self.zoom_pan.save_home()
        self.schematic.set_selected(board.id)
        self.props_panel.load_board(board)
        self._dirty = True
        self._update_title()
        self._set_status(f"Dodan: {board.name}")

    def _add_child_board(self) -> None:
        parent_id = self.schematic.get_selected()
        if not parent_id:
            messagebox.showinfo("Nema selekcije", "Odaberi matični ormar na shemi.")
            return
        parent = self.project.boards[parent_id]
        idx    = len(parent.children_ids) + 1
        child  = DistributionBoard(
            name=f"RO-{idx}", parent_id=parent_id,
            canvas_x=parent.canvas_x + (idx - 1) * (BOX_W + 60),
            canvas_y=parent.canvas_y - 200,
        )
        self.project.boards[child.id] = child
        parent.children_ids.append(child.id)
        recalculate_all(self.project, self.cable_db)
        self.schematic.redraw(fit=False)   # zadrži zoom, ali prikaži novi ormar
        self.schematic.set_selected(child.id)
        self.props_panel.load_board(child)
        self._dirty = True
        self._update_title()
        self._set_status(f"Dodan: {child.name} pod {parent.name}")

    def _delete_board(self) -> None:
        board_id = self.schematic.get_selected()
        if not board_id:
            messagebox.showinfo("Nema selekcije", "Odaberi ormar za brisanje.")
            return
        board = self.project.boards[board_id]
        if board.children_ids:
            messagebox.showwarning("Nije moguće",
                f"Ormar '{board.name}' ima podormare. Najprije obriši podormare.")
            return
        if not messagebox.askyesno("Brisanje", f"Obrisati '{board.name}'?"):
            return
        if board.parent_id and board.parent_id in self.project.boards:
            self.project.boards[board.parent_id].children_ids = [
                c for c in self.project.boards[board.parent_id].children_ids
                if c != board_id
            ]
        if self.project.root_board_id == board_id:
            self.project.root_board_id = None
        del self.project.boards[board_id]
        self.schematic.set_selected(None)
        self.props_panel.clear()
        self._on_change()
        self._set_status(f"Obrisan: {board.name}")

    # ── Export ────────────────────────────────────────────────

    def _export_png(self) -> None:
        path = filedialog.asksaveasfilename(title="Export PNG",
            defaultextension=".png", filetypes=[("PNG slika", "*.png")])
        if path:
            try:
                export_image(self.fig, path)
                self._set_status(f"PNG: {path}")
            except Exception as e:
                messagebox.showerror("Greška", str(e))

    def _export_pdf(self) -> None:
        path = filedialog.asksaveasfilename(title="Export PDF",
            defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if path:
            try:
                export_pdf(self.fig, path)
                self._set_status(f"PDF: {path}")
            except Exception as e:
                messagebox.showerror("Greška", str(e))

    def _export_csv(self) -> None:
        path = filedialog.asksaveasfilename(title="Export CSV tablice",
            defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            try:
                export_csv(self.project, path)
                self._set_status(f"CSV: {path}")
            except Exception as e:
                messagebox.showerror("Greška", str(e))

    # ── Raspored / zoom ───────────────────────────────────────

    def _auto_layout(self) -> None:
        _auto_layout_tree(self.project)
        self.schematic.redraw(fit=True)
        self.zoom_pan.save_home()
        self._set_status("Auto-raspored primijenjen.")

    def _reset_zoom(self) -> None:
        self.zoom_pan._key(type("e", (), {"key": "r"})())

    # ── Callbackovi ──────────────────────────────────────────

    def _on_board_selected(self, board_id: Optional[str]) -> None:
        if board_id and board_id in self.project.boards:
            board = self.project.boards[board_id]
            self.props_panel.load_board(board)
            self.cable_panel.highlight_cable(board.cable_type, board.cable_section_mm2)
            self._set_status(f"Odabran: {board.name}")
        else:
            self.props_panel.clear()

    def _on_props_changed(self) -> None:
        self._on_change()
        sel = self.schematic.get_selected()
        if sel and sel in self.project.boards:
            self.props_panel._refresh_calc_labels(self.project.boards[sel])

    def _on_cable_apply(self, cable_type: str, section_mm2: float) -> None:
        """Iz cable panela — primijeni kabel na odabrani spoj."""
        sel = self.schematic.get_selected()
        if not sel or sel not in self.project.boards:
            messagebox.showinfo("Nema selekcije", "Odaberi ormar na shemi.")
            return
        board = self.project.boards[sel]
        board.cable_type        = cable_type
        board.cable_section_mm2 = section_mm2
        self._on_change()
        self.props_panel.load_board(board)
        self._set_status(f"Kabel {cable_type} {section_mm2:g}mm² primijenjen na {board.name}")

    def _on_db_changed(self) -> None:
        """Cable DB promijenjen — osvježi sve komponente."""
        self.props_panel.refresh_cable_types()
        self.schematic.cable_db = self.cable_db
        self._on_change()
        self._set_status("Baza kabela osvježena.")

    def _on_change(self) -> None:
        recalculate_all(self.project, self.cable_db)
        self.schematic.redraw(fit=False)
        self._dirty = True
        self._update_title()

    # ── Pomoć ─────────────────────────────────────────────────

    def _set_status(self, msg: str) -> None:
        self._status_var.set(msg)

    def _update_title(self) -> None:
        fname = os.path.basename(self._current_file) if self._current_file else "bez naslova"
        dirty = " •" if self._dirty else ""
        self.title(f"Razvodne ploče – {self.project.name} [{fname}]{dirty}")

    def on_close(self) -> None:
        if self._dirty and not messagebox.askyesno(
                "Izlaz", "Postoje nespremene promjene. Izaći?"):
            return
        self.destroy()


def main() -> None:
    app = OrmariApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


if __name__ == "__main__":
    main()
