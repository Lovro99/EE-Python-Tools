from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Project, DistributionBoard

# Identično formulama iz sumPowerV2.lsp
CURR_FACTOR_3F = 658.18   # ≈ √3 × 400 × 0.95
CURR_FACTOR_1F = 218.5    # ≈ 230 × 0.95

# IEC 60364-5-52, metoda B2 (kabel u cijevi u zidu), Cu vodič, PVC izolacija, 30°C
AMPACITY_B2: dict[float, float] = {
    1.5:   15.0,
    2.5:   21.0,
    4.0:   28.0,
    6.0:   36.0,
    10.0:  50.0,
    16.0:  68.0,
    25.0:  89.0,
    35.0:  110.0,
    50.0:  134.0,
    70.0:  171.0,
    95.0:  207.0,
    120.0: 239.0,
}

STANDARD_FUSE_RATINGS = [
    6, 10, 13, 16, 20, 25, 32, 35, 40, 50,
    63, 80, 100, 125, 160, 200, 224, 250,
    300, 315, 355, 400, 425, 450, 500, 630,
]


def calc_current(corrected_power_kw: float, phase: str) -> float:
    if corrected_power_kw <= 0:
        return 0.0
    factor = CURR_FACTOR_3F if phase == "3F" else CURR_FACTOR_1F
    return (corrected_power_kw * 1000.0) / factor


def recommended_cable_section(current_a: float) -> float:
    for section, ampacity in sorted(AMPACITY_B2.items()):
        if ampacity >= current_a:
            return section
    return 120.0


def recommended_fuse_rating(current_a: float) -> float:
    """Sljedeća standardna veličina iznad I × 1.25 (IEC 60364-4-43)."""
    target = current_a * 1.25
    for rating in STANDARD_FUSE_RATINGS:
        if rating >= target:
            return float(rating)
    return float(STANDARD_FUSE_RATINGS[-1])


def recalculate_all(project: "Project", cable_db: dict = None) -> None:
    """
    Bottom-up izračun svih ormara (post-order DFS).

    Svaki ormar: ukupna snaga = vlastita instalirana + zbroj djece ukupnih snaga.
    Faktor istovremenosti primjenjuje se na UKUPNU instaliranu snagu ormara.
    Ako je cable_db prisutan, koristi bazu za preporučeni presjek kabela.
    """
    for board_id in project.get_ordered_leaves_first():
        board = project.boards[board_id]
        children = project.get_children(board_id)

        children_total = sum(c.calc_total_installed_kw for c in children)
        board.calc_total_installed_kw = board.installed_power_kw + children_total

        board.calc_corrected_power_kw = (
            board.calc_total_installed_kw * board.simultaneity_factor
        )

        board.calc_current_a = calc_current(board.calc_corrected_power_kw, board.phase)

        # Preporučeni presjek: iz baze (ako dostupno) ili tablica B2
        rec_sec = None
        if cable_db:
            try:
                from .cable_db import recommended_section_from_db
            except ImportError:
                import sys, os
                sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                from ormari.cable_db import recommended_section_from_db
            rec_sec = recommended_section_from_db(
                cable_db, board.cable_type, board.calc_current_a,
                board.install_method, board.cable_safety_factor,
            )
        if rec_sec is None:
            rec_sec = recommended_cable_section(board.calc_current_a)
        board.calc_rec_section_mm2 = rec_sec
        board.calc_rec_fuse_a = recommended_fuse_rating(board.calc_current_a)
