"""Usporedba opazanja — srce QC-a.

Grupira opazanja po (oznaka, atribut) i provjerava pisu li svugdje iste
vrijednosti. Statusi:

  GRESKA     — izvori se ne slazu (razlicite normalizirane vrijednosti)
  UPOZORENJE — podatak postoji samo u jednom tipu izvora, a projekt ima vise
  OK         — svi izvori se slazu
"""

from collections import defaultdict
from dataclasses import dataclass, field

GRESKA = "GRESKA"
UPOZORENJE = "UPOZORENJE"
OK = "OK"


@dataclass
class Finding:
    tag: str
    attribute: str
    status: str
    # value -> lista (source_file, source_type, raw_value, location)
    values: dict = field(default_factory=dict)

    def opis(self):
        if self.status == GRESKA:
            parts = []
            for val, sources in self.values.items():
                srcs = ", ".join(sorted({s[0] for s in sources}))
                raw = sources[0][2]
                parts.append(f"'{raw}' ({srcs})")
            return " ≠ ".join(parts)
        if self.status == UPOZORENJE:
            sources = next(iter(self.values.values()))
            src_types = sorted({s[1] for s in sources})
            return f"podatak postoji samo u izvoru: {', '.join(src_types)}"
        return "svi izvori se slažu"


def run_compare(conn, project):
    """Vrati listu Finding-a za projekt, najteze prvo."""
    cur = conn.execute(
        """SELECT tag, attribute, value, raw_value,
                  source_file, source_type, location
           FROM observations WHERE project = ?
           ORDER BY tag, attribute""",
        (project,),
    )

    groups = defaultdict(lambda: defaultdict(list))
    project_source_types = set()
    for r in cur.fetchall():
        # ime datoteke bez putanje je citljivije u izvjestaju
        fname = r["source_file"].replace("\\", "/").rsplit("/", 1)[-1]
        groups[(r["tag"], r["attribute"])][r["value"]].append(
            (fname, r["source_type"], r["raw_value"], r["location"])
        )
        project_source_types.add(r["source_type"])

    findings = []
    for (tag, attribute), values in groups.items():
        group_source_types = {
            s[1] for sources in values.values() for s in sources
        }
        if len(values) > 1:
            status = GRESKA
        elif len(group_source_types) == 1 and len(project_source_types) > 1:
            status = UPOZORENJE
        else:
            status = OK
        findings.append(
            Finding(tag=tag, attribute=attribute, status=status, values=dict(values))
        )

    order = {GRESKA: 0, UPOZORENJE: 1, OK: 2}
    findings.sort(key=lambda f: (order[f.status], f.tag, f.attribute))
    return findings


def summary(findings):
    counts = {GRESKA: 0, UPOZORENJE: 0, OK: 0}
    for f in findings:
        counts[f.status] += 1
    return counts
