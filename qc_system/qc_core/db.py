"""SQLite baza opazanja (observations).

Svaki redak je jedno opazanje: "u izvoru X, za oznaku Y, atribut Z ima
vrijednost V". Baza ne zna koja je vrijednost tocna — samo biljezi sto
gdje pise, a usporedba (compare.py) trazi neslaganja.
"""

import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id          INTEGER PRIMARY KEY,
    project     TEXT NOT NULL,
    tag         TEXT NOT NULL,      -- normalizirana oznaka opreme/kruga
    raw_tag     TEXT NOT NULL,      -- oznaka kako doslovno pise u izvoru
    attribute   TEXT NOT NULL,      -- npr. snaga_kw, tip_kabela
    value       TEXT NOT NULL,      -- normalizirana vrijednost (za usporedbu)
    raw_value   TEXT NOT NULL,      -- vrijednost kako doslovno pise u izvoru
    source_file TEXT NOT NULL,      -- puna putanja datoteke
    source_type TEXT NOT NULL,      -- excel | word | dwg
    location    TEXT,               -- npr. "Bilanca!D7", "tablica 2, red 5"
    extracted_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_obs_lookup
    ON observations (project, tag, attribute);
CREATE INDEX IF NOT EXISTS idx_obs_source
    ON observations (project, source_file);
"""


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def replace_source(conn, project, source_file, source_type, rows):
    """Zamijeni sva opazanja iz jedne datoteke novim skenom (snapshot).

    rows: iterable dictova s kljucevima
          tag, raw_tag, attribute, value, raw_value, location
    Vraca broj upisanih opazanja.
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with conn:
        conn.execute(
            "DELETE FROM observations WHERE project = ? AND source_file = ?",
            (project, source_file),
        )
        conn.executemany(
            """INSERT INTO observations
               (project, tag, raw_tag, attribute, value, raw_value,
                source_file, source_type, location, extracted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    project,
                    r["tag"],
                    r["raw_tag"],
                    r["attribute"],
                    r["value"],
                    r["raw_value"],
                    source_file,
                    source_type,
                    r.get("location"),
                    now,
                )
                for r in rows
            ],
        )
    return len(rows)


def list_projects(conn):
    cur = conn.execute("SELECT DISTINCT project FROM observations ORDER BY project")
    return [r["project"] for r in cur.fetchall()]
