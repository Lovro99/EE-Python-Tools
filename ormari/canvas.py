from __future__ import annotations
from typing import Callable, Optional, TYPE_CHECKING
import math, sys, os

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch, Rectangle, Circle
from matplotlib.lines import Line2D

if TYPE_CHECKING:
    from .models import Project, DistributionBoard

try:
    from .cable_db import get_effective_ampacity, cable_status, breaker_check
except ImportError:
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(_here))
    from ormari.cable_db import get_effective_ampacity, cable_status, breaker_check

# ── Dimenzije ─────────────────────────────────────────────────
BOX_W = 210
BOX_H = 90
SYM_H = 50     # prostora za simbol zaštite iznad kutije

# ── Boje ──────────────────────────────────────────────────────
C_BG         = "#0C1A28"
C_BOX_FILL   = "#0F2030"
C_ROOT_EDGE  = "#1E88E5"
C_CHILD_EDGE = "#546E7A"
C_SEL_EDGE   = "#FFD600"
C_LINE_OK    = "#455A64"
C_LINE_WARN  = "#FF8C00"
C_LINE_OVL   = "#F44336"
C_TXT_NAME   = "#E3F2FD"
C_TXT_INFO   = "#90A4AE"
C_TXT_DATA   = "#B0BEC5"
C_TXT_CABLE  = "#80DEEA"
C_PROT_OK    = "#80CBC4"
C_PROT_UNDER = "#FF8C00"   # prekidač premali (In < Ib)
C_PROT_OVER  = "#F44336"   # kabel nije zaštićen (In > Iz)
C_OK         = "#4CAF50"
C_WARN       = "#FF8C00"
C_OVL        = "#F44336"

# Baze fontova (pt) — skaliraju s _fs
_F_NAME  = 10.0
_F_INFO  = 8.0
_F_DATA  = 8.0
_F_SMALL = 7.5
_F_TINY  = 7.0
_F_CONN  = 10.0   # font na vodu (kabel tip/struja)
_F_PROT  = 10.0   # font na simbolu zaštite


def _fs_font(base: float, fs: float) -> float:
    """Skalira font; bazna veličina pri fs=1; ne ide ispod 5pt."""
    return max(5.0, base * fs)


def draw_protection_symbol(
    ax, cx: float, cy: float,
    prot_type: str, rating_a: float,
    fs: float = 1.0, breaker_st: str = "ok"
) -> None:
    """IEC simbol zaštite. Rating DESNO. Boja ovisi o statusu prekidača."""
    w = 20 * fs
    h = 32 * fs

    # Boja simbola
    if breaker_st == "underrated":
        sym_color = C_PROT_UNDER
    elif breaker_st == "overrated":
        sym_color = C_PROT_OVER
    else:
        sym_color = C_PROT_OK

    if prot_type == "Direktno":
        ax.add_line(Line2D([cx, cx], [cy - h / 2, cy + h / 2],
                           color=C_LINE_OK, lw=1.5, zorder=2))
        return

    if prot_type == "Prekidač":
        ax.add_patch(Rectangle(
            (cx - w / 2, cy - h / 2), w, h,
            linewidth=max(1, 1.8 * fs),
            edgecolor=sym_color, facecolor=C_BOX_FILL, zorder=3))
        ax.add_line(Line2D(
            [cx - w / 2 + 2 * fs, cx + w / 2 - 2 * fs],
            [cy - h / 2 + 2 * fs, cy + h / 2 - 2 * fs],
            color=sym_color, lw=max(1, 1.8 * fs), zorder=4))

    elif prot_type == "NH_osigurač":
        ax.add_patch(FancyBboxPatch(
            (cx - w / 2, cy - h / 2), w, h,
            boxstyle=f"round,pad={max(1, 3 * fs)}",
            linewidth=max(1, 1.8 * fs),
            edgecolor=sym_color, facecolor=C_BOX_FILL, zorder=3))
        ax.add_line(Line2D(
            [cx, cx], [cy - h / 2 - 3 * fs, cy + h / 2 + 3 * fs],
            color=sym_color, lw=max(1, 1.8 * fs), zorder=4))

    elif prot_type == "Rastavljač":
        ax.add_line(Line2D([cx, cx], [cy - h / 2, cy - 6 * fs],
                           color=sym_color, lw=max(1, 2.2 * fs), zorder=3))
        ax.add_line(Line2D([cx, cx], [cy + 6 * fs, cy + h / 2],
                           color=sym_color, lw=max(1, 2.2 * fs), zorder=3))
        ax.add_line(Line2D(
            [cx - 10 * fs, cx + 10 * fs],
            [cy - 8 * fs, cy + 8 * fs],
            color=sym_color, lw=max(1, 2.2 * fs), zorder=3))

    elif prot_type == "FID":
        ax.add_patch(Rectangle(
            (cx - w / 2, cy - h / 2 + 4 * fs), w, h - 8 * fs,
            linewidth=max(1, 1.8 * fs),
            edgecolor=sym_color, facecolor=C_BOX_FILL, zorder=3))
        ax.text(cx, cy + 2 * fs, "FI",
                fontsize=_fs_font(7.5, fs), color=sym_color,
                ha="center", va="center", zorder=4, fontweight="bold")
        ax.add_patch(Circle((cx, cy - h / 2 + 2 * fs), radius=4 * fs,
                            facecolor=sym_color, edgecolor="none", zorder=4))

    # Rating DESNO od simbola
    ax.text(cx + w / 2 + 5 * fs, cy,
            f"{rating_a:.0f} A",
            fontsize=_fs_font(_F_PROT, fs), color=sym_color,
            ha="left", va="center", zorder=4, fontweight="bold")


class SchematicCanvas:
    """
    Matplotlib canvas za shemu razvodnih ormara.
    Lijevi klik = selekcija | Drag = premještanje | Desni drag = pan | Kotačić = zoom
    """

    def __init__(
        self,
        fig: Figure, ax,
        project: "Project",
        on_select: Callable[[Optional[str]], None],
        cable_db: dict = None,
    ) -> None:
        self.fig       = fig
        self.ax        = ax
        self.project   = project
        self.on_select = on_select
        self.cable_db  = cable_db or {}

        self._selected_id: Optional[str] = None
        self._drag_data:   Optional[tuple] = None
        self._drag_started = False
        self._box_map: dict = {}

        self._ref_xlim_width: Optional[float] = None
        self._is_redrawing = False

        canvas = fig.canvas
        canvas.mpl_connect("pick_event",          self._on_pick)
        canvas.mpl_connect("button_press_event",  self._on_press)
        canvas.mpl_connect("button_release_event",self._on_release)
        canvas.mpl_connect("motion_notify_event", self._on_motion)

    # ── Font scale ────────────────────────────────────────────

    @property
    def _fs(self) -> float:
        """Vraća _current_fs koji je izračunat PRIJE ax.cla() u redraw()."""
        return getattr(self, "_current_fs", 1.0)

    def _compute_fs(self, xlim=None) -> float:
        """Izračun faktora skaliranja iz trenutnih (ili zadanih) xlim granica."""
        if not self._ref_xlim_width:
            return 1.0
        try:
            if xlim is None:
                xlim = self.ax.get_xlim()
            cur_w = abs(xlim[1] - xlim[0])
            if cur_w < 1:
                return 2.5
            return max(0.4, min(3.0, self._ref_xlim_width / cur_w))
        except Exception:
            return 1.0

    # ── Javno sučelje ─────────────────────────────────────────

    def set_selected(self, bid: Optional[str]) -> None:
        self._selected_id = bid

    def get_selected(self) -> Optional[str]:
        return self._selected_id

    def zoom_redraw(self) -> None:
        """Poziva ZoomPan na scroll/reset — redraw s novim font scaleom."""
        self.redraw(fit=False)

    def redraw(self, fit: bool = False) -> None:
        if self._is_redrawing:
            return
        self._is_redrawing = True

        # ── 1. Spremi VIEW i izračunaj _fs PRIJE cla() ───────
        #    ax.cla() resetira limate na (0,1) pa bi _fs bio kriv
        saved = None
        if not fit:
            saved = (self.ax.get_xlim(), self.ax.get_ylim())
            # Font scale iz TRENUTNOG (zoom) xlim — PRIJE brisanja
            self._current_fs = self._compute_fs(saved[0])
        else:
            # Za fit, koristimo 1.0 dok ne postavimo novi ref
            self._current_fs = 1.0

        # ── 2. Resetiraj os ───────────────────────────────────
        self.ax.cla()
        self.ax.set_autoscale_on(False)   # onemogući auto-rescale
        self._box_map.clear()
        self.ax.set_facecolor(C_BG)
        self.ax.axis("off")

        # ── 3. Postavi limate PRIJE crtanja ───────────────────
        #    Nužno jer cla() vraća na default (0,1)
        if not fit and saved is not None and self._ref_xlim_width is not None:
            self.ax.set_xlim(saved[0])
            self.ax.set_ylim(saved[1])

        # ── 4. Crtanje ────────────────────────────────────────
        if not self.project.boards:
            self.ax.text(0.5, 0.5, "Klikni '+ GRO' za početak",
                         transform=self.ax.transAxes,
                         color=C_TXT_INFO, fontsize=13,
                         ha="center", va="center")
            self.ax.set_xlim(0, 1000)
            self.ax.set_ylim(0, 800)
        else:
            self._draw_connections()
            self._draw_boards()

            if fit or saved is None or self._ref_xlim_width is None:
                # Fit: postavi pravi view i spremi referencu
                self._fit_view()
                self._ref_xlim_width = abs(self.ax.get_xlim()[1] - self.ax.get_xlim()[0])
                # Ažuriraj _current_fs na 1.0 (= referentni zoom)
                self._current_fs = 1.0
            # else: limate su već postavljeni u koraku 3

        self._is_redrawing = False
        self.fig.canvas.draw_idle()

    # ── Crtanje ───────────────────────────────────────────────

    def _draw_boards(self) -> None:
        for board in self.project.boards.values():
            self._draw_board_box(board)

    def _draw_board_box(self, board: "DistributionBoard") -> None:
        x, y   = board.canvas_x, board.canvas_y
        fs     = self._fs
        is_sel = board.id == self._selected_id
        is_root= board.parent_id is None

        edge_color = (C_SEL_EDGE if is_sel else
                      C_ROOT_EDGE if is_root else C_CHILD_EDGE)

        patch = FancyBboxPatch(
            (x, y), BOX_W, BOX_H,
            boxstyle="round,pad=4",
            facecolor=C_BOX_FILL, edgecolor=edge_color,
            linewidth=2.5 if is_sel else 1.8,
            picker=True, zorder=3,
        )
        patch._board_id = board.id
        self.ax.add_patch(patch)
        self._box_map[patch] = board.id

        pad = 8

        # Naziv + faznost/napon/i
        self.ax.text(x + pad, y + BOX_H - 14,
                     board.name,
                     fontsize=_fs_font(_F_NAME, fs), fontweight="bold",
                     color=C_TXT_NAME, zorder=4, clip_on=True)
        self.ax.text(x + BOX_W - pad, y + BOX_H - 14,
                     f"{board.phase}  {board.voltage}V  i={board.simultaneity_factor:.2f}",
                     fontsize=_fs_font(_F_INFO, fs), color=C_TXT_INFO,
                     ha="right", zorder=4, clip_on=True)

        # Snage
        self.ax.text(x + pad, y + BOX_H - 30,
                     f"P_uk={board.calc_total_installed_kw:.2f}kW   "
                     f"P_v={board.calc_corrected_power_kw:.2f}kW",
                     fontsize=_fs_font(_F_DATA, fs), color=C_TXT_DATA,
                     zorder=4, clip_on=True)

        # Struja + presjek
        self.ax.text(x + pad, y + BOX_H - 46,
                     f"I = {board.calc_current_a:.2f} A     "
                     f"Presjek = {board.cable_section_mm2:g} mm²",
                     fontsize=_fs_font(_F_DATA, fs), color=C_TXT_DATA,
                     zorder=4, clip_on=True)

        # Kabel + zaštita
        prot_str = board.protection_type
        if board.protection_type == "FID":
            prot_str += f" {board.fid_sensitivity_ma:.0f}mA"
        n_txt = "2×" if board.cable_count == 2 else ""
        self.ax.text(x + pad, y + BOX_H - 62,
                     f"{n_txt}{board.cable_type}  "
                     f"{board.protection_rating_a:.0f}A  {prot_str}",
                     fontsize=_fs_font(_F_SMALL, fs), color="#78909C",
                     zorder=4, clip_on=True)

        # Preporučeno + status kabela u donjem lijevom uglu
        if board.parent_id is not None:
            cab_st = cable_status(
                self.cable_db, board.cable_type, board.cable_section_mm2,
                board.install_method, board.cable_count,
                board.calc_current_a, board.cable_safety_factor,
            )
            rec_color = C_OK if cab_st == "ok" else (C_WARN if cab_st == "warning" else C_OVL)
        else:
            rec_color = C_OK
        self.ax.text(x + pad, y + 6,
                     f"Preporučeno: {board.calc_rec_section_mm2:g}mm²  "
                     f"{board.calc_rec_fuse_a:.0f}A",
                     fontsize=_fs_font(_F_TINY, fs), color=rec_color,
                     zorder=4, clip_on=True)

    def _draw_connections(self) -> None:
        for board in self.project.boards.values():
            if board.parent_id and board.parent_id in self.project.boards:
                self._draw_connection(self.project.boards[board.parent_id], board)

    def _draw_connection(self, parent: "DistributionBoard", child: "DistributionBoard") -> None:
        fs = self._fs

        px = parent.canvas_x + BOX_W / 2
        py = parent.canvas_y
        cx = child.canvas_x + BOX_W / 2
        cy = child.canvas_y + BOX_H
        mid_y = (py + cy) / 2

        # ── Status kabela ──────────────────────────────────────
        cab_st = cable_status(
            self.cable_db, child.cable_type, child.cable_section_mm2,
            child.install_method, child.cable_count,
            child.calc_current_a, child.cable_safety_factor,
        )

        # ── Status prekidača ───────────────────────────────────
        ib_kabel = get_effective_ampacity(
            self.cable_db, child.cable_type, child.cable_section_mm2,
            child.install_method, child.cable_count,
        )
        brk_st = breaker_check(
            child.protection_type,
            child.protection_rating_a,
            child.calc_current_a,
            ib_kabel,
        )

        # Boja linije: najgori od cable_status i breaker_status
        def _worst(a: str, b: str) -> str:
            order = {"ok": 0, "warning": 1, "underrated": 1,
                     "no_protection": 0, "overrated": 2, "overload": 2}
            if order.get(b, 0) > order.get(a, 0):
                return b
            return a

        worst = _worst(cab_st, brk_st)
        line_color = {
            "ok": C_LINE_OK, "warning": C_LINE_WARN,
            "underrated": C_LINE_WARN, "no_protection": C_LINE_OK,
            "overrated": C_LINE_OVL, "overload": C_LINE_OVL,
        }.get(worst, C_LINE_OK)
        lw = max(1, 1.8 if worst == "ok" else 2.5)

        # Polylinja
        self.ax.plot([px, px, cx, cx], [py, mid_y, mid_y, cy],
                     color=line_color, lw=lw, zorder=1)

        # ── Label kabela (horizontalni segment) ────────────────
        lx = (px + cx) / 2
        ly = mid_y

        ib_txt = f"{ib_kabel:.0f}" if ib_kabel > 0 else "?"
        i_txt  = f"{child.calc_current_a:.1f}"
        n_txt  = "2×" if child.cable_count == 2 else ""
        meth   = "Z" if child.install_method == "zemlja" else "A"   # Zrak/Amo
        line1  = f"{n_txt}{child.cable_type}  {child.cable_section_mm2:g}mm²  [{meth}]"
        if child.cable_length_m > 0:
            line1 += f"  L={child.cable_length_m:.0f}m"
        line2  = f"I = {i_txt} A    Ib = {ib_txt} A"

        # Boja I/Ib linije
        i_color = C_OK if cab_st == "ok" else (C_WARN if cab_st == "warning" else C_OVL)

        gap = 6 * fs
        self.ax.text(lx, ly + gap, line1,
                     fontsize=_fs_font(_F_CONN, fs), color=C_TXT_CABLE,
                     ha="center", va="bottom", zorder=2, fontweight="bold",
                     bbox=dict(facecolor=C_BG, edgecolor="none", pad=1.5))
        self.ax.text(lx, ly - gap * 0.4, line2,
                     fontsize=_fs_font(_F_CONN - 0.5, fs), color=i_color,
                     ha="center", va="top", zorder=2,
                     bbox=dict(facecolor=C_BG, edgecolor="none", pad=1.5))

        # ── Simbol zaštite ────────────────────────────────────
        sym_cy = cy + SYM_H / 2 + 4
        draw_protection_symbol(
            self.ax, cx, sym_cy,
            child.protection_type, child.protection_rating_a,
            fs=fs, breaker_st=brk_st,
        )

    def _fit_view(self) -> None:
        if not self.project.boards:
            return
        xs = [b.canvas_x for b in self.project.boards.values()]
        ys = [b.canvas_y for b in self.project.boards.values()]
        pad_x, pad_y = 100, 100
        self.ax.set_xlim(min(xs) - pad_x, max(xs) + BOX_W + pad_x)
        self.ax.set_ylim(min(ys) - SYM_H - pad_y, max(ys) + BOX_H + pad_y)

    # ── Event handleri ────────────────────────────────────────

    def _on_pick(self, event) -> None:
        bid = getattr(event.artist, "_board_id", None)
        if bid:
            self._selected_id = bid
            self.on_select(bid)
            self.redraw(fit=False)

    def _on_press(self, event) -> None:
        if event.button != 1 or event.xdata is None or not self._selected_id:
            return
        board = self.project.boards.get(self._selected_id)
        if board and (board.canvas_x <= event.xdata <= board.canvas_x + BOX_W and
                      board.canvas_y <= event.ydata <= board.canvas_y + BOX_H):
            self._drag_data = (
                self._selected_id,
                event.xdata, event.ydata,
                board.canvas_x, board.canvas_y,
            )
            self._drag_started = False

    def _on_motion(self, event) -> None:
        if not self._drag_data or event.xdata is None or event.ydata is None:
            return
        bid, mx0, my0, bx0, by0 = self._drag_data
        dx, dy = event.xdata - mx0, event.ydata - my0
        if not self._drag_started and math.hypot(dx, dy) < 5:
            return
        self._drag_started = True
        board = self.project.boards.get(bid)
        if board:
            board.canvas_x = bx0 + dx
            board.canvas_y = by0 + dy
            self.redraw(fit=False)

    def _on_release(self, event) -> None:
        self._drag_data    = None
        self._drag_started = False
