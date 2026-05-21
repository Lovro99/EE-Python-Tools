from __future__ import annotations
import json
import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Project

from .models import Project, DistributionBoard


def project_to_dict(project: Project) -> dict:
    return {
        "name": project.name,
        "author": project.author,
        "root_board_id": project.root_board_id,
        "boards": {
            bid: dataclasses.asdict(board)
            for bid, board in project.boards.items()
        },
    }


def project_from_dict(data: dict) -> Project:
    project = Project(
        name=data.get("name", "Projekt"),
        author=data.get("author", ""),
    )
    project.root_board_id = data.get("root_board_id")
    for bid, bdata in data.get("boards", {}).items():
        # Kompatibilnost — ignoriraj nepoznata polja
        known = {f.name for f in dataclasses.fields(DistributionBoard)}
        filtered = {k: v for k, v in bdata.items() if k in known}
        board = DistributionBoard(**filtered)
        project.boards[bid] = board
    return project


def save_project(project: Project, path: str | Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(project_to_dict(project), f, indent=2, ensure_ascii=False)


def load_project(path: str | Path) -> Project:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return project_from_dict(data)
