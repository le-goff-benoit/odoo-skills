#!/usr/bin/env python3
"""Relève l'état d'un projet Odoo et écrit son `.odoo-agents/PROJECT.md`.

Un agent qui arrive sur un projet ne sait rien : ni la série, ni les modèles
déjà créés, ni les modules dont on dépend, ni où est la dette. Il le redécouvre
à chaque conversation, souvent de travers. Ce script produit une fois pour
toutes la fiche de faits que les trois profils lisent en premier.

Ce qui est **relevé** (mesuré dans le code) est régénéré à chaque passage, entre
les marqueurs de bloc. Ce qui est **compris** (métier, décisions, pièges) est
écrit à la main par l'agent ou par l'humain, sous les marqueurs, et n'est jamais
écrasé.

Usage : odoo_project_scan.py <chemin_du_projet> [--series X]
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import odoo_series  # noqa: E402

MARK_START = "<!-- odoo-agents:relevé début — régénéré par odoo_project_scan.py -->"
MARK_END = "<!-- odoo-agents:relevé fin -->"

SKELETON = """
## Compréhension métier

<!-- Écrit à la main, jamais écrasé par le scan. À remplir au fil des demandes. -->

*(à compléter : que fait le client, quel est son vocabulaire, quels processus
sont couverts par Odoo et lesquels restent dehors)*

## Décisions actées

| Date | Décision | Raison | Qui |
|---|---|---|---|

## Pièges connus

*(les choses qui ont déjà fait perdre du temps sur ce projet : contournements en
place, données sales, modules tiers capricieux, règles métier contre-intuitives)*
"""


def run(cmd: list[str], cwd: Path) -> str:
    try:
        out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip()


# Arbres de sources vendorisées : un projet peut contenir une copie d'Odoo
# community, enterprise ou des thèmes. Ce ne sont pas des modules custom, et les
# linter avec la série du projet fabrique de la fausse dette par centaines
# (cf. LESSONS.md L3). Ils sont écartés du relevé.
VENDOR_DIRS = frozenset({
    "enterprise", "themes", "design-themes", "odoo-sources",
    "node_modules", "venv", ".venv", "restore", "filestore",
})


def _is_vendored(module: Path, root: Path) -> bool:
    """Vrai si le module vit dans un arbre de sources vendorisées."""
    rel = module.relative_to(root).parts
    if VENDOR_DIRS & set(rel):
        return True
    # Une copie complète d'Odoo se reconnaît à son odoo/release.py.
    for i in range(len(rel)):
        if (root.joinpath(*rel[: i + 1]) / "odoo" / "release.py").exists():
            return True
    return False


def modules_of(root: Path) -> list[Path]:
    candidates = [
        p.parent for p in root.rglob("__manifest__.py")
        if "__pycache__" not in p.parts and ".git" not in p.parts
    ]
    found, skipped = [], 0
    for module in candidates:
        if _is_vendored(module, root):
            skipped += 1
        else:
            found.append(module)
    if skipped:
        print(f"  … {skipped} module(s) de sources vendorisées écartés du relevé",
              file=sys.stderr)
    return sorted(found, key=lambda p: p.name)


def read_manifest(module: Path) -> dict:
    try:
        data = ast.literal_eval((module / "__manifest__.py").read_text(encoding="utf-8"))
    except (OSError, ValueError, SyntaxError):
        return {}
    return data if isinstance(data, dict) else {}


def models_of(module: Path) -> tuple[list[str], list[str]]:
    """Modèles créés par le module, et modèles standard qu'il étend."""
    created: list[str] = []
    extended: list[str] = []
    for path in module.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not any(ast.unparse(b).startswith("models.") for b in node.bases):
                continue
            values: dict[str, object] = {}
            for stmt in node.body:
                if not isinstance(stmt, ast.Assign):
                    continue
                for target in stmt.targets:
                    if isinstance(target, ast.Name) and target.id in ("_name", "_inherit"):
                        try:
                            values[target.id] = ast.literal_eval(stmt.value)
                        except (ValueError, SyntaxError):
                            pass
            name = values.get("_name")
            inherit = values.get("_inherit")
            inherited = inherit if isinstance(inherit, list) else ([inherit] if inherit else [])
            if name and name not in inherited:
                created.append(str(name))
            else:
                extended.extend(str(i) for i in inherited)
    return sorted(set(created)), sorted(set(extended))


def lint_debt(module: Path, series: str | None) -> str:
    script = Path(__file__).resolve().parent / "odoo_lint.py"
    cmd = [sys.executable, str(script)]
    if series:
        cmd += ["--series", series]
    cmd.append(str(module))
    out = run(cmd, module)
    tail = [line for line in out.splitlines() if "erreur(s)" in line]
    return tail[-1] if tail else "non mesurée"


def git_facts(root: Path) -> list[str]:
    if not (root / ".git").exists():
        return ["dépôt git : aucun"]
    facts = []
    count = run(["git", "rev-list", "--count", "HEAD"], root)
    last = run(["git", "log", "-1", "--format=%h %ad %s", "--date=short"], root)
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root)
    facts.append(f"branche `{branch}`, {count} commits, dernier : {last}")
    hot = run(
        ["git", "log", "--since=6 months ago", "--name-only", "--pretty=format:"], root
    )
    counter = Counter(
        line for line in hot.splitlines()
        if line.strip() and line.endswith((".py", ".xml", ".js", ".csv"))
    )
    if counter:
        top = ", ".join(f"`{name}` ({n})" for name, n in counter.most_common(5))
        facts.append(f"fichiers les plus touchés sur 6 mois : {top}")
    return facts


def scan(root: Path, explicit: str | None) -> str:
    info = odoo_series.resolve(root, explicit)
    series = info["series"]
    modules = modules_of(root)

    lines = [
        MARK_START,
        f"## Relevé du {date.today().isoformat()}",
        "",
        f"- **Racine** : `{root}`",
        f"- **Série Odoo** : **{series}** (déterminée par {info['origin']})",
        f"- **Sources de référence** : `{info['sources']}` "
        f"+ `{info['enterprise'].name}`",
        f"- **Stack de QA** : image `odoo-qa:{series}`, "
        f"base `odoo_qa_{series.replace('.', '_')}`",
    ]
    for fact in git_facts(root):
        lines.append(f"- {fact}")

    lines += ["", f"## Modules custom ({len(modules)})", ""]
    for module in modules:
        manifest = read_manifest(module)
        created, extended = models_of(module)
        deps = manifest.get("depends", [])
        community = [d for d in deps if (info["sources"] / "addons" / d).is_dir()]
        enterprise = [d for d in deps if (info["enterprise"] / d).is_dir()]
        internal = [d for d in deps if any(m.name == d for m in modules)]
        unknown = [d for d in deps
                   if d not in community + enterprise + internal and d not in ("base", "web")]

        lines += [
            f"### `{module.name}`",
            "",
            f"- version `{manifest.get('version', '?')}` — "
            f"licence `{manifest.get('license', '?')}` — "
            f"auteur {manifest.get('author', '?')}",
            f"- chemin : `{module.relative_to(root)}`",
            f"- dépendances : {len(community)} community, {len(enterprise)} enterprise"
            + (f", {len(internal)} interne(s)" if internal else "")
            + (f", **{len(unknown)} introuvable(s)** : {', '.join(f'`{d}`' for d in unknown)}"
               if unknown else ""),
        ]
        if enterprise:
            lines.append(f"  - enterprise : {', '.join(f'`{d}`' for d in enterprise)}")
        if created:
            shown = ", ".join(f"`{m}`" for m in created[:12])
            more = f" (+{len(created) - 12})" if len(created) > 12 else ""
            lines.append(f"- modèles créés ({len(created)}) : {shown}{more}")
        if extended:
            shown = ", ".join(f"`{m}`" for m in extended[:12])
            more = f" (+{len(extended) - 12})" if len(extended) > 12 else ""
            lines.append(f"- modèles étendus ({len(extended)}) : {shown}{more}")

        acl = module / "security" / ("ir.access.csv"
                                     if odoo_series.has(series, "ir_access_csv")
                                     else "ir.model.access.csv")
        acl_count = len(acl.read_text(encoding="utf-8").splitlines()) - 1 if acl.is_file() else 0
        groups = len(re.findall(
            r'model="res\.groups"',
            " ".join(p.read_text(encoding="utf-8", errors="replace")
                     for p in module.rglob("*.xml")),
        ))
        tests = sorted(p.name for p in (module / "tests").glob("test_*.py")) \
            if (module / "tests").is_dir() else []
        lines += [
            f"- sécurité : {acl_count} ligne(s) d'accès, {groups} groupe(s) déclaré(s)",
            f"- tests : {len(tests)} fichier(s)"
            + (f" — {', '.join(f'`{t}`' for t in tests)}" if tests else " — **aucun**"),
            f"- dette lint (série {series}) : {lint_debt(module, explicit)}",
            "",
        ]

    lines += [
        "## Commandes utiles sur ce projet",
        "",
        "```bash",
        f"export ODOO_ADDONS_DIR={root}",
        f"export ODOO_SERIES={series}",
        f"{Path(__file__).resolve().parent}/odoo-lint.sh --changed <module>",
        f"{Path(__file__).resolve().parent}/odoo-stack.sh up",
        f"{Path(__file__).resolve().parent}/odoo-test.sh <module> --fresh --update",
        "```",
        "",
        MARK_END,
    ]
    return "\n".join(lines)


def merge(target: Path, block: str) -> None:
    header = f"# Projet {target.parent.parent.name} — fiche de contexte\n\n" \
             "> Lue en premier par les agents Odoo. Le bloc « relevé » est " \
             "régénéré par `odoo_project_scan.py` ; tout ce qui est en dessous " \
             "est écrit à la main et conservé.\n\n"
    if target.exists():
        old = target.read_text(encoding="utf-8")
        if MARK_START in old and MARK_END in old:
            head, _, rest = old.partition(MARK_START)
            _, _, tail = rest.partition(MARK_END)
            target.write_text(head + block + tail, encoding="utf-8")
            return
        target.write_text(header + block + "\n" + old, encoding="utf-8")
        return
    target.write_text(header + block + "\n" + SKELETON, encoding="utf-8")


def main(argv: list[str]) -> int:
    args = argv[1:]
    explicit = None
    if "--series" in args:
        index = args.index("--series")
        explicit = args[index + 1] if len(args) > index + 1 else None
        args = args[:index] + args[index + 2:]
    if not args:
        print(__doc__)
        return 2

    root = Path(args[0]).resolve()
    if not root.is_dir():
        print(f"ERREUR : {root} n'est pas un répertoire")
        return 2

    home = root / ".odoo-agents"
    home.mkdir(exist_ok=True)

    config = home / "config"
    if not config.exists():
        detected = odoo_series.resolve(root, explicit)["series"]
        config.write_text(
            "# Configuration des agents Odoo pour ce projet.\n"
            "# La série fait autorité sur la détection automatique.\n"
            f"series = {detected}\n",
            encoding="utf-8",
        )
        print(f"  ✓ {config}  (series = {detected})")

    journal = home / "JOURNAL.md"
    if not journal.exists():
        journal.write_text(
            f"# Journal des interventions — {root.name}\n\n"
            "> Une entrée par intervention des agents. Écrite par le profil QA à "
            "la fin de la chaîne, relue par le développeur au début de la "
            "suivante. C'est la mémoire courte du projet.\n\n"
            "Format d'une entrée :\n\n"
            "```markdown\n"
            "## AAAA-MM-JJ — <titre de la demande>\n"
            "**Demandé** : …\n"
            "**Fait** : … (fichiers, modèles, champs)\n"
            "**Verdict QA** : VALIDÉ / SOUS RÉSERVE / REFUSÉ — …\n"
            "**Appris** : ce que la prochaine intervention doit savoir "
            "(piège, contrainte métier, dépendance cachée)\n"
            "**Reste ouvert** : …\n"
            "```\n",
            encoding="utf-8",
        )
        print(f"  ✓ {journal}")

    project = home / "PROJECT.md"
    merge(project, scan(root, explicit))
    print(f"  ✓ {project}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
