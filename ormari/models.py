from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List
import uuid


STANDARD_FUSE_RATINGS: List[float] = [
    6, 10, 13, 16, 20, 25, 32, 35, 40, 50,
    63, 80, 100, 125, 160, 200, 224, 250,
    300, 315, 355, 400, 425, 450, 500, 630,
]

STANDARD_CABLE_SECTIONS: List[float] = [
    1.5, 2.5, 4.0, 6.0, 10.0, 16.0, 25.0,
    35.0, 50.0, 70.0, 95.0, 120.0,
]

CABLE_TYPES: List[str] = ["NYY", "PP41", "FG7", "NHXMH", "N2XH", "NYM"]

PROTECTION_TYPES: List[str] = [
    "Prekidač", "Rastavljač", "NH_osigurač", "FID", "Direktno"
]

FID_SENSITIVITIES: List[float] = [6, 10, 30, 100, 300, 500]


@dataclass
class DistributionBoard:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Novi ormar"

    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)

    phase: str = "3F"          # "1F" ili "3F"
    voltage: int = 400          # 230 ili 400
    installed_power_kw: float = 0.0
    simultaneity_factor: float = 0.7

    cable_type: str = "NYY"
    cable_section_mm2: float = 2.5
    cable_length_m: float = 0.0
    protection_type: str = "Prekidač"
    protection_rating_a: float = 16.0
    fid_sensitivity_ma: float = 30.0
    cable_count: int = 1           # 1 ili 2 paralelna kabela
    install_method: str = "zrak"   # "zrak" ili "zemlja"
    cable_safety_factor: float = 1.25  # kabel mora imati Ib >= I * faktor

    canvas_x: float = 100.0
    canvas_y: float = 100.0

    # Izračunate vrijednosti (postavljaju se u calculations.recalculate_all)
    calc_total_installed_kw: float = 0.0
    calc_corrected_power_kw: float = 0.0
    calc_current_a: float = 0.0
    calc_rec_section_mm2: float = 2.5
    calc_rec_fuse_a: float = 16.0


@dataclass
class Project:
    name: str = "Novi projekt"
    author: str = ""
    boards: dict = field(default_factory=dict)  # id -> DistributionBoard
    root_board_id: Optional[str] = None

    def get_board(self, board_id: str) -> Optional[DistributionBoard]:
        return self.boards.get(board_id)

    def get_children(self, board_id: str) -> List[DistributionBoard]:
        board = self.boards.get(board_id)
        if not board:
            return []
        return [self.boards[cid] for cid in board.children_ids if cid in self.boards]

    def get_ordered_leaves_first(self) -> List[str]:
        """Post-order DFS — listovi se računaju prije roditelja."""
        order: List[str] = []
        visited: set = set()

        def dfs(bid: str) -> None:
            if bid in visited:
                return
            visited.add(bid)
            for cid in self.boards[bid].children_ids:
                if cid in self.boards:
                    dfs(cid)
            order.append(bid)

        if self.root_board_id and self.root_board_id in self.boards:
            dfs(self.root_board_id)
        # Ormari koji nisu u stablu (no parent, not root) — dodaj ih na kraj
        for bid in self.boards:
            if bid not in visited:
                order.append(bid)
        return order

    def get_all_descendants(self, board_id: str) -> List[str]:
        """Svi potomci zadanog ormara (BFS)."""
        result: List[str] = []
        queue = list(self.boards[board_id].children_ids)
        while queue:
            cid = queue.pop(0)
            if cid in self.boards:
                result.append(cid)
                queue.extend(self.boards[cid].children_ids)
        return result
