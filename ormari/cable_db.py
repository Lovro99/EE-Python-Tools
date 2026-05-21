"""Upravljanje bazom podataka kabela (cable_db.json)."""
from __future__ import annotations
import json
from pathlib import Path
from typing import List, Optional, Tuple

DB_PATH = Path(__file__).parent / "cable_db.json"


# ── Load / Save ───────────────────────────────────────────────

def load_db() -> dict:
    if DB_PATH.exists():
        try:
            with open(DB_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_db(db: dict) -> None:
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


# ── Parsiranje naziva kabela ──────────────────────────────────

def parse_cable_name(full_name: str) -> Tuple[str, str]:
    """
    "FG16OR16 3G" → ("FG16OR16", "3G")
    "NYY-J 2G"   → ("NYY-J", "2G")
    "SomeCable"  → ("SomeCable", "")
    """
    parts = full_name.rsplit(" ", 1)
    if len(parts) == 2 and parts[1]:
        return parts[0], parts[1]
    return full_name, ""


def get_families(db: dict) -> List[str]:
    """Jedinstvene obitelji kabela (bez konfiguracije žila)."""
    seen: set = set()
    result: List[str] = []
    for key in db:
        family, _ = parse_cable_name(key)
        if family not in seen:
            seen.add(family)
            result.append(family)
    return result


def get_configs_for_family(db: dict, family: str) -> List[str]:
    """Dostupne konfiguracije (žile) za zadanu obitelj kabela."""
    configs: List[str] = []
    for key in db:
        f, c = parse_cable_name(key)
        if f == family and c:
            configs.append(c)
    return configs


def get_full_key(family: str, config: str) -> str:
    """Spoji obitelj i konfiguraciju u puni ključ."""
    if config:
        return f"{family} {config}"
    return family


# ── Upiti u bazu ──────────────────────────────────────────────

def get_cable_types(db: dict) -> List[str]:
    return list(db.keys())


def get_sections(db: dict, cable_type: str) -> List[dict]:
    """Lista rječnika: {mm2, zrak, zemlja}."""
    return db.get(cable_type, {}).get("presjeci", [])


def get_ampacity(db: dict, cable_type: str, section_mm2: float,
                 method: str = "zrak") -> float:
    """Strujno opterećenje za zadani kabel, presjek i metodu."""
    for p in get_sections(db, cable_type):
        if abs(p["mm2"] - section_mm2) < 0.01:
            val = p.get(method, 0)
            return float(val) if val else 0.0
    return 0.0


def get_effective_ampacity(
    db: dict, cable_type: str, section_mm2: float,
    method: str = "zrak", cable_count: int = 1,
) -> float:
    """Efektivna struja kabela — množi s brojem paralelnih kabela."""
    return get_ampacity(db, cable_type, section_mm2, method) * max(1, cable_count)


def recommended_section_from_db(
    db: dict, cable_type: str, current_a: float,
    method: str = "zrak", safety_factor: float = 1.25,
) -> Optional[float]:
    """Najmanji presjek čiji ampacity >= current_a * safety_factor."""
    sections = get_sections(db, cable_type)
    if not sections:
        return None
    target = current_a * safety_factor
    for p in sorted(sections, key=lambda x: x["mm2"]):
        val = p.get(method, 0) or 0
        if val >= target:
            return float(p["mm2"])
    valid = [p for p in sections if (p.get(method) or 0) > 0]
    if valid:
        return float(max(valid, key=lambda x: x["mm2"])["mm2"])
    return None


# ── Status provjere ───────────────────────────────────────────

def cable_status(
    db: dict, cable_type: str, section_mm2: float,
    method: str, cable_count: int, current_a: float, safety_factor: float,
) -> str:
    """
    'ok'       — Ib(kabel) >= I * faktor_sigurnosti
    'warning'  — Ib(kabel) >= I, ali < I * faktor_sigurnosti
    'overload' — I > Ib(kabel)
    """
    ib = get_effective_ampacity(db, cable_type, section_mm2, method, cable_count)
    if ib <= 0:
        return "ok"
    if current_a > ib:
        return "overload"
    if current_a * safety_factor > ib:
        return "warning"
    return "ok"


def breaker_check(
    protection_type: str,
    rating_a: float,
    current_a: float,
    cable_ampacity: float,
) -> str:
    """
    Provjera IEC 60364-4-43: Ib ≤ In ≤ Iz

    Ib  = struja ormara (current_a)
    In  = nazivna struja zaštite (rating_a)
    Iz  = struja kabela (cable_ampacity)

    Vraća:
      'ok'           — Ib ≤ In ≤ Iz  (ispravno)
      'underrated'   — In < Ib        (prekidač premali, struja ormara ga palí)
      'overrated'    — In > Iz        (kabel nije zaštićen od prekostruje)
      'no_protection'— nema zaštite (Direktno)
    """
    if protection_type == "Direktno":
        return "no_protection"

    # Rastavljač ne štiti od prekostruje — preskočimo Ib≤In provjeru
    # ali Iz provjera ostaje (rastavljač ne smije biti veći od kabela)
    if protection_type != "Rastavljač":
        if rating_a < current_a:
            return "underrated"

    if cable_ampacity > 0 and rating_a > cable_ampacity:
        return "overrated"

    return "ok"
