#!/usr/bin/env python3
"""Briefing compact d'un projet Odoo, à lire en premier par chaque agent.

Remplace quatre lectures de fichiers (PROJECT.md, JOURNAL.md, LESSONS.md,
SERIES_MATRIX.md — 60 Ko et plus sur un projet vivant) par un seul relevé de
quelques Ko qui contient tout ce qu'un agent doit savoir avant d'agir :

  - la série cible et son origine, les sources de référence ;
  - la release de changelog ouverte (s'il y en a un) et ses points ;
  - les sections écrites à la main de PROJECT.md (métier, décisions, pièges) ;
  - le relevé (une ligne par module) ;
  - les N dernières entrées du journal (défaut 3) et toutes les lignes « Appris » ;
  - les leçons de LESSONS.md qui s'appliquent à la série (Portée + Règle) ;
  - les formes attendues dans cette série (ce qui diffère du guide 19.0).

Usage : odoo_briefing.py <chemin_du_projet_ou_du_module> [--series X] [--journal N]
                          [--full-journal]
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import odoo_series  # noqa: E402

HOME = Path(__file__).resolve().parent.parent
FEATURE_LABELS = {
    "no_attrs": "`invisible=\"expr\"` (plus d'`attrs`/`states`)",
    "no_name_get": "`_compute_display_name` (plus de `name_get`)",
    "list_tag": "`<list>` (plus de `<tree>`)",
    "chatter_tag": "`<chatter/>`",
    "env_translate": "`self.env._()` disponible",
    "api_readonly": "`@api.readonly` disponible",
    "models_constraint": "`models.Constraint` (plus de `_sql_constraints`)",
    "domain_object": "objet `Domain`",
    "groups_privilege": "`res.groups.privilege` (plus de `category_id`)",
    "group_ids_rename": "`res.users.group_ids` (et non `groups_id`)",
    "env_cr_props": "`self.env.cr` obligatoire (plus de `self._cr`)",
    "hr_version": "`hr.version` (plus de `hr.contract`)",
    "ir_access_csv": "`security/ir.access.csv` (plus d'`ir.model.access.csv` ni d'`ir.rule`)",
}
INVERSE = {
    "list_tag": "`<tree>` (et non `<list>`)",
    "chatter_tag": "`<div class=\"oe_chatter\">` (et non `<chatter/>`)",
    "models_constraint": "`_sql_constraints` (et non `models.Constraint`)",
    "domain_object": "listes de domaine (pas d'objet `Domain`)",
    "groups_privilege": "`category_id` sur les groupes (pas de `privilege`)",
    "group_ids_rename": "`res.users.groups_id` (et non `group_ids`)",
    "hr_version": "`hr.contract` existe encore",
    "ir_access_csv": "`ir.model.access.csv` + `ir.rule`",
}


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 10) -> str:
    try:
        out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip()


def section(title: str) -> str:
    return f"\n## {title}\n"


def hand_written(project_md: Path) -> str:
    """Tout ce qui suit le bloc relevé : compréhension, décisions, pièges."""
    text = project_md.read_text(encoding="utf-8", errors="replace")
    _, _, tail = text.partition("<!-- odoo-agents:relevé fin -->")
    tail = re.sub(r"<!--.*?-->", "", tail, flags=re.S)
    # Les paragraphes-gabarits « (à compléter : …) » ne portent aucune information.
    tail = re.sub(r"\*\(à compléter[^)]*\)\*", "", tail)
    tail = re.sub(r"\*\(les choses qui ont déjà fait perdre[^)]*\)\*", "", tail)
    # Une section sans contenu est dite vide, en un mot.
    chunks = re.split(r"(?m)^(## .+)$", tail)
    out = [chunks[0].strip()]
    for heading, body in zip(chunks[1::2], chunks[2::2]):
        body = body.strip()
        empty = not body or re.fullmatch(r"\|[^\n]*\|\n\|[-| ]*\|", body)
        out.append(f"{heading}\n{'*(vide)*' if empty else body}")
    return re.sub(r"\n{3,}", "\n\n", "\n\n".join(o for o in out if o)).strip()


def survey_lines(project_md: Path) -> list[str]:
    """Une ligne par module, à partir du relevé."""
    text = project_md.read_text(encoding="utf-8", errors="replace")
    head, _, _ = text.partition("<!-- odoo-agents:relevé fin -->")
    out, current = [], None
    for line in head.splitlines():
        found = re.match(r"### `([^`]+)`", line)
        if found:
            current = found[1]
            out.append(f"- `{current}`")
            continue
        if current and re.match(r"- (version|dépendances|modèles créés|tests|dette lint)", line):
            out[-1] += " · " + line[2:].split(" — ")[0].strip()
    return out


def journal_entries(journal: Path) -> list[str]:
    text = journal.read_text(encoding="utf-8", errors="replace")
    # Retire le gabarit d'entrée présent dans l'en-tête.
    text = re.sub(r"```markdown.*?```", "", text, flags=re.S)
    parts = re.split(r"(?m)^## (?=\d{4}-\d{2}-\d{2})", text)
    return ["## " + p.strip() for p in parts[1:] if p.strip()]


def learned_lines(entries: list[str]) -> list[str]:
    """Les lignes « Appris » de toutes les entrées, une puce par leçon."""
    out = []
    for entry in entries:
        title = entry.splitlines()[0][3:]
        found = re.search(r"\*\*Appris\*\*\s*:?(.*?)(?=\n\*\*[A-ZÀ-Ü][^*]*\*\*|\Z)", entry, re.S)
        if not found:
            continue
        body = found[1].strip()
        bullets = [b.strip() for b in re.split(r"\n\s*-\s+", "\n" + body) if b.strip()]
        for bullet in bullets:
            bullet = re.sub(r"\s+", " ", bullet)
            out.append(f"- ({title[:10]}) {bullet[:220]}{'…' if len(bullet) > 220 else ''}")
    return out


def lessons(series: str) -> list[str]:
    path = HOME / "LESSONS.md"
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    out = []
    for block in re.split(r"(?m)^### ", text)[1:]:
        title = block.splitlines()[0].strip()
        if title.startswith("L<n>"):
            continue  # le gabarit de leçon
        scope = re.search(r"\*\*Portée\*\*\s*:\s*(.+)", block)
        rule = re.search(r"\*\*Règle\*\*\s*:\s*(.+?)(?=\n\*\*|\Z)", block, re.S)
        scope_text = scope[1].strip() if scope else "universelle"
        found = re.search(r"série\s*[≥>=]+\s*([\d.]+)", scope_text)
        if found and odoo_series.key(series) < odoo_series.key(found[1]):
            continue
        rule_text = re.sub(r"\s+", " ", rule[1].strip()) if rule else ""
        out.append(f"- **{title}** [{scope_text}] — {rule_text}")
    return out


def lot_label(root: Path) -> str:
    """Le mot du projet pour une release de changelog (« release » chez NECA), « release » par défaut."""
    config = root / ".odoo-agents" / "config"
    if config.is_file():
        for line in config.read_text(encoding="utf-8", errors="replace").splitlines():
            found = re.match(r"\s*lot_label\s*[=:]\s*(\S+)", line)
            if found:
                return found[1]
    return "release"


def lot_status(root: Path) -> str:
    lot_script = HOME / "scripts" / "odoo-release.sh"
    if not lot_script.is_file():
        return ""
    current = run([str(lot_script), "current", str(root)])
    if not current:
        return (f"aucune {lot_label(root)} ouverte — s'ouvre après le verdict de l'analyste ou du support "
                "(`odoo-release.sh open <projet> \"<titre>\"`)")
    release = Path(current)
    points = run([str(lot_script), "points", str(release)])
    base = (release / ".base").read_text().strip() if (release / ".base").is_file() else "?"
    lines = [f"`{release.relative_to(root)}` (base git `{base[:10]}`)"]
    if points:
        lines += ["  " + p for p in points.splitlines()]
    return "\n".join(lines)


def deployed_versions(root: Path, modules: list[str]) -> list[str]:
    """Version des modules du projet sur chaque instance déclarée (lecture seule, 6 s max)."""
    if not modules:
        return []
    try:
        import odoo_instance  # noqa: PLC0415
    except ImportError:
        return []
    out = []
    import socket
    old = socket.getdefaulttimeout()
    socket.setdefaulttimeout(6)
    try:
        for inst in odoo_instance.Instance.load_all(root.name).values():
            if inst.kind not in ("production", "staging") or not inst.secret:
                continue
            try:
                rows = inst.execute("ir.module.module", "search_read",
                                    [("name", "in", modules)],
                                    fields=["name", "installed_version", "state"])
            except Exception as exc:  # noqa: BLE001 — hors ligne, refus, timeout
                out.append(f"{inst.name} : injoignable ({type(exc).__name__})")
                continue
            parts = [f"`{r['name']}` {r['installed_version'] or r['state']}" for r in rows]
            out.append(f"{inst.name} ({inst.kind}) : " + (", ".join(parts) or "aucun module du projet"))
    finally:
        socket.setdefaulttimeout(old)
    return out


def inbox_status(root: Path) -> str:
    """Ce que l'humain a déposé dans <projet>/inbox/ : sauvegardes et mails, du plus récent au plus ancien."""
    inbox = root / "inbox"
    if not inbox.is_dir():
        return ""
    files = sorted((p for p in inbox.iterdir() if p.is_file() and not p.name.startswith(".")),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return "vide"
    import datetime
    out = []
    for p in files[:8]:
        when = datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime("%d.%m %H:%M")
        size = p.stat().st_size
        kind = ("sauvegarde → `odoo-restore.sh inbox/%s --db <client>_test --force`" % p.name
                if p.suffix.lower() in (".zip", ".dump", ".sql") else
                "mail → `odoo_mail.py inbox/%s --release <release>`" % p.name
                if p.suffix.lower() == ".eml" else "fichier")
        out.append(f"`{p.name}` ({size // (1 << 20)} Mo, déposé le {when}) — {kind}")
    if len(files) > 8:
        out.append(f"… +{len(files) - 8}")
    return "\n  - " + "\n  - ".join(out)


def restored_dbs(series: str) -> str:
    """Bases présentes sur le stack de la série (sans démarrer quoi que ce soit)."""
    names = run(["docker", "ps", "--format", "{{.Names}}"], timeout=5).splitlines()
    dbs = []
    for name in names:
        if name == f"odoo-qa-{series.replace('.', '_')}-db-1":
            out = run(["docker", "exec", name, "psql", "-U", "odoo", "-d", "postgres", "-Atc",
                       "SELECT datname FROM pg_database WHERE datistemplate=false "
                       "AND datname NOT IN ('postgres')"], timeout=8)
            dbs += [d for d in out.splitlines() if d]
    return ", ".join(dbs)


def main(argv: list[str]) -> int:
    args = argv[1:]
    explicit = None
    n_journal = 3
    full_journal = False
    if "--series" in args:
        i = args.index("--series"); explicit = args[i + 1]; del args[i:i + 2]
    if "--journal" in args:
        i = args.index("--journal"); n_journal = int(args[i + 1]); del args[i:i + 2]
    if "--full-journal" in args:
        full_journal = True; args.remove("--full-journal")
    if not args:
        print(__doc__)
        return 2

    path = Path(args[0]).resolve()
    info = odoo_series.resolve(path, explicit)
    series = info["series"]
    root = odoo_series.project_root(path) or path
    agents = root / ".odoo-agents"

    out = [f"# Briefing — {root.name}", ""]
    out.append(f"- **Série** : **{series}** (origine : {info['origin']}) · sources "
               f"`{info['sources']}` + `{info['enterprise'].name}`"
               + ("" if info["exact_sources"] else " · ⚠️ sources exactes absentes, repli"))
    out.append(f"- **Racine** : `{root}`")
    common = run(["git", "rev-parse", "--git-common-dir"], cwd=root)
    if common and common not in (".git", str(root / ".git")):
        out.append(f"- ⚠️ **worktree git** : dépôt principal `{Path(common).parent}`")
    if not agents.is_dir():
        out.append(f"- ⚠️ pas de `.odoo-agents/` : lancer `odoo_project_scan.py {root}`")
        print("\n".join(out))
        return 0

    out.append(f"- **{lot_label(root).capitalize()}** : {lot_status(root)}")
    inst = HOME / "scripts" / "odoo_instance.py"
    declared = run([sys.executable, str(inst), "list", root.name]) if inst.is_file() else ""
    if declared and "aucune" not in declared.lower():
        out.append("- **Instances déclarées** : " + "; ".join(
            l.strip() for l in declared.splitlines() if l.strip())[:300])
    dbs = restored_dbs(series)
    if dbs:
        out.append(f"- **Bases sur le stack {series}** : {dbs}")
    inbox = inbox_status(root)
    if inbox:
        out.append(f"- **Inbox** (`inbox/`, déposé par l'humain) : {inbox}")
    project_md = agents / "PROJECT.md"
    modules = re.findall(r"^### `([^`]+)`", project_md.read_text(encoding="utf-8", errors="replace"), re.M) \
        if project_md.is_file() else []
    for line in deployed_versions(root, modules):
        out.append(f"- **Déployé** — {line}")
    repo_versions = re.findall(r"^### `([^`]+)`\n\n- version `([^`]+)`",
                               project_md.read_text(encoding="utf-8", errors="replace"), re.M) \
        if project_md.is_file() else []
    if repo_versions and any(l.startswith("- **Déployé**") for l in out):
        out.append("- **Dépôt** : " + ", ".join(f"`{m}` {v}" for m, v in repo_versions))

    forms = [FEATURE_LABELS[f] for f in odoo_series.FEATURES if odoo_series.has(series, f)]
    against = [INVERSE[f] for f in INVERSE if not odoo_series.has(series, f)]
    out.append(section(f"Formes attendues en {series}"))
    if against:
        out.append("**Différences avec le guide 19.0** : " + " · ".join(against))
    out.append("Formes en vigueur : " + " · ".join(forms))

    project_md = agents / "PROJECT.md"
    if project_md.is_file():
        out.append(section("Modules (relevé)"))
        out += survey_lines(project_md) or ["*(relevé vide — relancer le scan)*"]
        out.append(section("Ce que le projet sait déjà (PROJECT.md, écrit à la main)"))
        out.append(hand_written(project_md) or "*(rien encore)*")

    journal = agents / "JOURNAL.md"
    if journal.is_file():
        entries = journal_entries(journal)
        shown = entries if full_journal else entries[-n_journal:]
        out.append(section(f"Journal — {len(entries)} entrée(s), "
                           f"{'toutes' if full_journal else f'les {len(shown)} dernières'}"))
        for entry in shown:
            body = entry.strip()
            if not full_journal and len(body) > 1800:
                body = body[:1800] + "\n…(entrée tronquée, lire JOURNAL.md pour le détail)"
            out.append(body + "\n")
        learned = learned_lines(entries[:-len(shown)] if shown else entries)
        if learned:
            out.append(section("Appris sur ce projet (entrées plus anciennes)"))
            out += learned

    out.append(section(f"Leçons du dispositif applicables en {series} (LESSONS.md)"))
    out += lessons(series) or ["*(aucune)*"]

    text = "\n".join(out)
    print(text)
    print(f"\n— briefing : {len(text.encode('utf-8')) // 1024} Ko. Détail : "
          f"`{agents}/`, `{HOME}/LESSONS.md`, `{HOME}/SERIES_MATRIX.md`.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
