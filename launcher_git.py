"""
Git i verzije za EE Alati launcher
==================================
Sve sto launcher radi s gitom, bez ikakvog GUI-ja (da se moze koristiti i iz
deploy.ps1 / komandne linije):

  - info o trenutnom commitu (grana, hash, datum, poruka)
  - fetch + provjera ima li novih commita na udaljenom repou
  - fast-forward azuriranje (nikad ne brise lokalne promjene)
  - popis udaljenih grana i testne kopije grana (git worktree u .grane/)
  - datum zadnje promjene po alatu (jedan `git log` za sve alate)
  - VERSION.json za stabilnu (deployanu) verziju na shareu

CLI (koristi ga deploy.ps1):
  python launcher_git.py verzija-json --repo . --rev origin/master --izlaz VERSION.json
"""

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime

GRANE_DIR = ".grane"                 # testne kopije grana (u .gitignore)
GRANE_MAPA = "grane.json"            # mapa-u-.grane -> ime grane
VERSION_JSON = "VERSION.json"        # info o stabilnoj verziji (pise deploy)
REQ_HASH_FILE = "ee_requirements.sha256"  # u venvu: hash zadnje instaliranih paketa


class GitGreska(Exception):
    pass


# -- osnovno -----------------------------------------------------------------
def _bez_prozora():
    """Na Windowsima pythonw + subprocess inace blicne konzolni prozor."""
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def git(args, cwd, timeout=60, provjeri=True):
    """Pokrene git naredbu; vrati stdout (bez zavrsnih razmaka). Na gresku GitGreska."""
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"   # nikad ne cekaj lozinku u nevidljivoj konzoli
    try:
        r = subprocess.run(
            ["git", "-c", "core.quotepath=off", *args], cwd=cwd,
            capture_output=True, timeout=timeout, encoding="utf-8", errors="replace", env=env,
            creationflags=_bez_prozora(),
        )
    except FileNotFoundError:
        raise GitGreska("Git nije instaliran (ili nije na PATH-u).")
    except subprocess.TimeoutExpired:
        raise GitGreska(f"git {args[0]}: isteklo vrijeme ({timeout} s) — provjeri mrežu.")
    if provjeri and r.returncode != 0:
        raise GitGreska((r.stderr or r.stdout).strip() or f"git {args[0]} nije uspio")
    return r.stdout.rstrip()  # samo desno: `status --porcelain` pocinje razmakom


def je_git_repo(putanja):
    """True ako je `putanja` korijen git repoa (ne neka podmapa / share kopija)."""
    try:
        vrh = git(["rev-parse", "--show-toplevel"], putanja, timeout=10)
    except GitGreska:
        return False
    return os.path.normcase(os.path.abspath(vrh)) == os.path.normcase(os.path.abspath(putanja))


def _datum(iso):
    """'2026-10-14T12:30:00+02:00' -> '14.10.2026.'"""
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m.%Y.")
    except (ValueError, TypeError):
        return iso or ""


def info_commita(cwd, rev="HEAD"):
    out = git(["log", "-1", "--format=%h%x00%H%x00%cI%x00%s", rev], cwd)
    kratki, puni, iso, poruka = out.split("\x00", 3)
    return {"hash": kratki, "puni_hash": puni, "iso": iso,
            "datum": _datum(iso), "poruka": poruka}


def trenutna_grana(cwd):
    """Ime grane, ili None ako je detached HEAD."""
    ime = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    return None if ime == "HEAD" else ime


def fetch(cwd):
    git(["fetch", "--prune", "--quiet", "origin"], cwd, timeout=90)


def upstream(cwd):
    """'origin/master' za trenutnu granu, ili None ako nema upstreama."""
    try:
        return git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd)
    except GitGreska:
        return None


def broj_commita_iza(cwd, prema):
    """Koliko commita `prema` ima, a HEAD nema (0 = azurno)."""
    return int(git(["rev-list", "--count", f"HEAD..{prema}"], cwd) or 0)


def lokalne_promjene(cwd):
    """Popis izmijenjenih praćenih datoteka (neprateni se ignoriraju)."""
    out = git(["status", "--porcelain", "--untracked-files=no"], cwd)
    return [l[3:] for l in out.splitlines() if l.strip()]


def promijenjene_datoteke(cwd, od, do):
    if od == do:
        return []
    out = git(["diff", "--name-only", od, do], cwd)
    return [l for l in out.splitlines() if l]


def azuriraj_ff(cwd, prema):
    """Fast-forward HEAD na `prema`. Lokalne promjene se nikad ne brisu:
    ako bi ih azuriranje pregazilo, git odbije i dobije se GitGreska."""
    git(["merge", "--ff-only", "--quiet", prema], cwd)


# -- grane i testne kopije (worktree) ------------------------------------------
def udaljene_grane(cwd):
    """Lista udaljenih grana, najnovija prva: dict(ime, datum, hash, poruka)."""
    out = git([
        "for-each-ref", "--sort=-committerdate", "refs/remotes/origin",
        "--format=%(refname:lstrip=3)%00%(committerdate:iso-strict)"
        "%00%(objectname:short)%00%(subject)",
    ], cwd)
    grane = []
    for l in out.splitlines():
        ime, iso, h, poruka = l.split("\x00", 3)
        if ime == "HEAD":
            continue
        grane.append({"ime": ime, "iso": iso, "datum": _datum(iso),
                      "hash": h, "poruka": poruka})
    return grane


def _sigurno_ime(grana):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", grana)[:60]


def _ucitaj_mapu(repo):
    p = os.path.join(repo, GRANE_DIR, GRANE_MAPA)
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _spremi_mapu(repo, mapa):
    d = os.path.join(repo, GRANE_DIR)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, GRANE_MAPA), "w", encoding="utf-8") as f:
        json.dump(mapa, f, indent=2, ensure_ascii=False)


def putanja_kopije(repo, grana):
    return os.path.join(repo, GRANE_DIR, _sigurno_ime(grana))


def osiguraj_kopiju(repo, grana):
    """Testna kopija grane u .grane/<ime>, postavljena na origin/<grana>.
    Vrati (putanja, stari_hash ili None ako je kopija nova)."""
    put = putanja_kopije(repo, grana)
    cilj = f"origin/{grana}"
    stari = None
    if os.path.isdir(put) and os.path.exists(os.path.join(put, ".git")):
        stari = git(["rev-parse", "HEAD"], put)
        # checkout odbije ako bi pregazio lokalne izmjene u kopiji
        git(["checkout", "--quiet", "--detach", cilj], put)
    else:
        git(["worktree", "prune"], repo)
        git(["worktree", "add", "--quiet", "--detach", put, cilj], repo, timeout=120)
    mapa = _ucitaj_mapu(repo)
    mapa[_sigurno_ime(grana)] = grana
    _spremi_mapu(repo, mapa)
    return put, stari


def ocisti_kopije(repo, postojece_grane):
    """Obrise testne kopije grana kojih vise nema na GitHubu (npr. nakon
    merge-a). Kopije s lokalnim izmjenama ostavlja. Vrati popis obrisanih."""
    mapa = _ucitaj_mapu(repo)
    obrisane = []
    for kljuc, grana in list(mapa.items()):
        if grana in postojece_grane:
            continue
        put = os.path.join(repo, GRANE_DIR, kljuc)
        try:
            if os.path.isdir(put) and lokalne_promjene(put):
                continue
            if os.path.isdir(put):
                git(["worktree", "remove", "--force", put], repo)
        except GitGreska:
            continue
        del mapa[kljuc]
        obrisane.append(grana)
    if obrisane:
        _spremi_mapu(repo, mapa)
        try:
            git(["worktree", "prune"], repo)
        except GitGreska:
            pass
    return obrisane


# -- verzije alata --------------------------------------------------------------
def putanja_alata_u_repou(alat):
    """Putanja (relativna, s '/') koju git prati za alat, ili None (vanjski alat)."""
    if "modul" in alat:
        return alat["modul"].split(".")[0]
    s = alat.get("skripta", "")
    if not s or os.path.isabs(s) or re.match(r"^[A-Za-z]:", s):
        return None
    return s.replace("\\", "/")


def zadnje_promjene(cwd, putanje, rev="HEAD"):
    """{putanja: dict(datum, iso, hash, poruka)} — zadnji commit koji je
    dirao svaku putanju. Jedan `git log` za sve, ne po jedan po alatu."""
    putanje = [p for p in dict.fromkeys(putanje) if p]
    if not putanje:
        return {}
    out = git(["log", "--format=%x01%h%x00%cI%x00%s", "--name-only", rev,
               "--", *putanje], cwd, timeout=60)
    rezultat, trenutni = {}, None
    for l in out.splitlines():
        if l.startswith("\x01"):
            h, iso, poruka = l[1:].split("\x00", 2)
            trenutni = {"hash": h, "iso": iso, "datum": _datum(iso), "poruka": poruka}
            continue
        if not l or trenutni is None:
            continue
        for p in putanje:
            if p not in rezultat and (l == p or l.startswith(p + "/")):
                rezultat[p] = trenutni
        if len(rezultat) == len(putanje):
            break
    return rezultat


def napravi_verziju_json(repo, rev, izlaz):
    """VERSION.json za stabilnu verziju (deploy na share): commit + zadnja
    promjena i verzija svakog alata, sve na reviziji `rev`."""
    alati = json.loads(git(["show", f"{rev}:tools.json"], repo))["alati"]
    putanje = {putanja_alata_u_repou(a) for a in alati} - {None}
    promjene = zadnje_promjene(repo, sorted(putanje), rev)
    podaci = {
        "commit": info_commita(repo, rev),
        "grana": rev.split("/", 1)[-1],
        "objavljeno": datetime.now().isoformat(timespec="seconds"),
        "alati": promjene,
    }
    with open(izlaz, "w", encoding="utf-8") as f:
        json.dump(podaci, f, indent=2, ensure_ascii=False)
    return podaci


def ucitaj_verziju_json(mapa):
    try:
        with open(os.path.join(mapa, VERSION_JSON), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# -- ovisnosti (pip) ---------------------------------------------------------------
def u_venvu():
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def _hash_datoteke(putanja):
    with open(putanja, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def treba_instalirati(req_putanja):
    """True ako se requirements.txt promijenio od zadnje instalacije u ovaj venv."""
    if not os.path.isfile(req_putanja):
        return False
    try:
        with open(os.path.join(sys.prefix, REQ_HASH_FILE), encoding="utf-8") as f:
            return f.read().strip() != _hash_datoteke(req_putanja)
    except OSError:
        return True


def instaliraj_pakete(python_exe, req_putanja):
    """pip install -r requirements.txt; na uspjeh zapamti hash. Vrati (ok, poruka)."""
    r = subprocess.run(
        [python_exe, "-m", "pip", "install", "--disable-pip-version-check",
         "-q", "-r", req_putanja],
        capture_output=True, encoding="utf-8", errors="replace",
        creationflags=_bez_prozora(),
    )
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip()[-1500:]
    with open(os.path.join(sys.prefix, REQ_HASH_FILE), "w", encoding="utf-8") as f:
        f.write(_hash_datoteke(req_putanja))
    return True, ""


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="naredba", required=True)
    vj = sub.add_parser("verzija-json", help="napravi VERSION.json za deploy")
    vj.add_argument("--repo", default=os.path.dirname(os.path.abspath(__file__)))
    vj.add_argument("--rev", default="origin/master")
    vj.add_argument("--izlaz", required=True)
    args = ap.parse_args(argv)
    if args.naredba == "verzija-json":
        p = napravi_verziju_json(args.repo, args.rev, args.izlaz)
        c = p["commit"]
        print(f"VERSION.json: {p['grana']} @ {c['hash']} ({c['datum']}) — {c['poruka']}")


if __name__ == "__main__":
    main()
