from __future__ import annotations
import csv
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from matplotlib.figure import Figure
    from .models import Project


def export_image(fig: "Figure", path: str | Path, dpi: int = 200) -> None:
    fig.savefig(str(path), dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor())


def export_pdf(fig: "Figure", path: str | Path) -> None:
    fig.savefig(str(path), format="pdf", bbox_inches="tight", facecolor=fig.get_facecolor())


def export_csv(project: "Project", path: str | Path) -> None:
    """Tablarni izvoz proračuna za sve ormare."""
    rows = []
    for board in project.boards.values():
        parent = project.boards.get(board.parent_id)
        rows.append({
            "Naziv": board.name,
            "Nadređeni ormar": parent.name if parent else "—",
            "Faza": board.phase,
            "Napon_V": board.voltage,
            "P_instal_kW": f"{board.installed_power_kw:.2f}",
            "Faktor_i": f"{board.simultaneity_factor:.2f}",
            "P_uk_total_kW": f"{board.calc_total_installed_kw:.2f}",
            "P_v_kW": f"{board.calc_corrected_power_kw:.2f}",
            "I_A": f"{board.calc_current_a:.2f}",
            "Tip_kabela": board.cable_type,
            "Presjek_mm2": board.cable_section_mm2,
            "Duljina_m": board.cable_length_m,
            "Tip_zastite": board.protection_type,
            "Zastita_A": board.protection_rating_a,
            "Prp_presjek_mm2": board.calc_rec_section_mm2,
            "Prp_zastita_A": board.calc_rec_fuse_a,
        })

    if not rows:
        return

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
