#!/usr/bin/env python3
"""Contrôles statiques d'un module Odoo, calés sur la série cible du module.

Complète `ruff` (qui couvre le style Python) par tout ce qui est spécifique à Odoo :
manifest, cohérence des fichiers de données, sécurité, et motifs datés.

La série cible est résolue par `odoo_series.py` (--series, `.odoo-agents/config`,
puis le préfixe de `version` du manifest). Chaque motif est daté : `_sql_constraints`
est une erreur **à partir de** la 19.0, et `models.Constraint` une erreur **avant**
elle. Un module 18.0 n'est donc pas jugé avec les règles de la 19.0.

Usage : odoo_lint.py [--series X] [--only-files f1 f2 ...] <chemin_du_module> [...]
Sortie : lignes `SEVERITE fichier:ligne  message`, code retour 1 si une ERREUR existe.

`--only-files` restreint les remontées aux fichiers indiqués : les contrôles
tournent sur tout le module (il faut le voir en entier pour juger la sécurité ou
les dépendances), mais seules les anomalies portées par ces fichiers sont
affichées. C'est ce qui permet de linter un module historique sans se noyer.
"""

from __future__ import annotations

import ast
import csv
import io
import py_compile
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import odoo_series  # noqa: E402

# Portée d'un motif : None = toutes séries, ('since', f) = à partir de la série
# où `f` devient la forme attendue, ('before', f) = avant celle-ci (anachronisme).
ALWAYS = None


def since(feature: str) -> tuple[str, str]:
    return ("since", feature)


def before(feature: str) -> tuple[str, str]:
    return ("before", feature)


# (regex, sévérité, message, portée). Appliqués ligne à ligne.
PY_PATTERNS = [
    (r"_sql_constraints\s*=", "ERREUR",
     "`_sql_constraints` est obsolète : utiliser `models.Constraint(...)`",
     since("models_constraint")),
    (r"\bmodels\.(Constraint|UniqueIndex)\(", "ERREUR",
     "`models.Constraint` / `models.UniqueIndex` n'existent qu'à partir de la 19.0 : "
     "utiliser `_sql_constraints`",
     before("models_constraint")),
    (r"\bDomain\s*\(|import Domain\b", "ERREUR",
     "l'objet `Domain` n'existe qu'à partir de la 19.0 : utiliser une liste de domaine",
     before("domain_object")),
    (r"\bsuper\(\s*\w+\s*,\s*self\s*\)", "ERREUR",
     "utiliser `super()` sans argument", ALWAYS),
    (r"^\s*def\s+create\s*\(\s*self\s*,\s*vals\s*\)", "ERREUR",
     "`create` doit être `@api.model_create_multi` et prendre `vals_list`", ALWAYS),
    (r"^\s*print\s*\(", "ERREUR",
     "`print` interdit (ruff T201) : utiliser `_logger`", ALWAYS),
    (r"except\s*:", "ERREUR",
     "`except:` nu interdit (ruff BLE)", ALWAYS),
    (r"\b_\(\s*f[\"']", "ERREUR",
     "f-string dans `_()` : passer les valeurs en arguments — `_(\"x %s\", val)`", ALWAYS),
    (r"_logger\.\w+\(\s*f[\"']", "ERREUR",
     "f-string dans un log (ruff G) : `_logger.info(\"x %s\", val)`", ALWAYS),
    (r"\bself\.env\._\(", "ERREUR",
     "`self.env._()` n'existe qu'à partir de la 18.0 : utiliser `_()`",
     before("env_translate")),
    (r"@api\.readonly\b", "ERREUR",
     "`@api.readonly` n'existe qu'à partir de la 18.0", before("api_readonly")),
    (r"\bself\._(cr|uid|context)\b", "ERREUR",
     "propriété dépréciée : utiliser `self.env.cr` / `self.env.uid` / `self.env.context`",
     since("env_cr_props")),
    (r"\bself\._(cr|uid|context)\b", "AVERTISSEMENT",
     "propriété dépréciée en amont de la 19.0 : préférer `self.env.cr` / `.uid` / `.context`",
     before("env_cr_props")),
    (r"\.groups_id\b", "AVERTISSEMENT",
     "`res.users.groups_id` renommé `group_ids` en 19.0", since("group_ids_rename")),
    (r"\.group_ids\b", "AVERTISSEMENT",
     "`group_ids` est le nom 19.0 : avant, le champ s'appelle `groups_id`",
     before("group_ids_rename")),
    (r"\bhr\.contract\b", "ERREUR",
     "`hr.contract` n'existe plus en 19.0 : le modèle est `hr.version`",
     since("hr_version")),
    (r"\[\s*\(\s*0\s*,\s*0\s*,", "AVERTISSEMENT",
     "commande x2many en tuple : utiliser `Command.create({...})`", ALWAYS),
    (r"\bname_get\s*\(", "ERREUR",
     "`name_get()` supprimé : implémenter `_compute_display_name()`", since("no_name_get")),
    (r"\.sudo\(\)", "INFO",
     "`sudo()` : vérifier qu'un commentaire justifie l'élévation de droits", ALWAYS),
]

XML_PATTERNS = [
    (r"<tree\b|</tree>", "ERREUR",
     "`<tree>` renommé `<list>`", since("list_tag")),
    (r"\battrs\s*=", "ERREUR",
     "`attrs` supprimé : utiliser `invisible=` / `readonly=` / `required=` avec une expression",
     since("no_attrs")),
    (r"\bstates\s*=\s*[\"']", "ERREUR",
     "`states` supprimé : utiliser `invisible=\"state not in (...)\"`", since("no_attrs")),
    (r"oe_chatter", "ERREUR",
     "le chatter se déclare avec la balise `<chatter/>`", since("chatter_tag")),
    (r"<chatter\s*/?>", "ERREUR",
     "la balise `<chatter/>` n'existe qu'à partir de la 18.0 : "
     "utiliser `<div class=\"oe_chatter\">`", before("chatter_tag")),
    (r"view_mode[^>]*?>[^<]*\btree\b", "ERREUR",
     "`view_mode` doit utiliser `list` et non `tree`", since("list_tag")),
    (r"res\.groups\.privilege|privilege_id", "ERREUR",
     "`res.groups.privilege` n'existe qu'à partir de la 19.0 : utiliser `category_id`",
     before("groups_privilege")),
    (r"<xpath[^>]*expr=\"[^\"]*\[\d+\]", "AVERTISSEMENT",
     "xpath positionnel fragile : ancrer sur un `name=` ou un `id=`", ALWAYS),
]

findings: list[tuple[str, str, int, str]] = []
SERIES = odoo_series.DEFAULT_SERIES
SOURCES = odoo_series.SOURCES_ROOT / odoo_series.DEFAULT_SERIES
ENTERPRISE = odoo_series.SOURCES_ROOT / f"{odoo_series.DEFAULT_SERIES}-enterprise"


def applies(scope) -> bool:
    if scope is ALWAYS:
        return True
    kind, feature = scope
    return odoo_series.has(SERIES, feature) if kind == "since" \
        else not odoo_series.has(SERIES, feature)


def report(severity: str, path: Path | str, line: int, message: str) -> None:
    findings.append((severity, str(path), line, message))


# --------------------------------------------------------------------------- #
# Contrôles
# --------------------------------------------------------------------------- #

def check_python(module: Path) -> None:
    patterns = [p for p in PY_PATTERNS if applies(p[3])]
    for path in sorted(module.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            with tempfile.NamedTemporaryFile(suffix=".pyc", delete=True) as tmp:
                py_compile.compile(str(path), cfile=tmp.name, doraise=True)
        except py_compile.PyCompileError as exc:
            report("ERREUR", path, getattr(exc.exc_value, "lineno", 0) or 0,
                   f"erreur de syntaxe : {exc.exc_value}")
            continue

        text = path.read_text(encoding="utf-8", errors="replace")
        for num, line in enumerate(text.splitlines(), start=1):
            stripped = line.split("#", 1)[0]
            for pattern, severity, message, _scope in patterns:
                if re.search(pattern, stripped):
                    report(severity, path, num, message)

        check_models(path, text)


def check_models(path: Path, text: str) -> None:
    """Contrôles AST : _description, computes incomplets."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {ast.unparse(b) for b in node.bases}
        if not any(b.startswith("models.") for b in bases):
            continue

        assigns = {
            t.id: stmt.value
            for stmt in node.body
            if isinstance(stmt, ast.Assign)
            for t in stmt.targets
            if isinstance(t, ast.Name)
        }
        is_new_model = "_name" in assigns and "_inherit" not in assigns
        if "_inherit" in assigns and "_name" in assigns:
            try:
                inherit = ast.literal_eval(assigns["_inherit"])
                name = ast.literal_eval(assigns["_name"])
                is_new_model = name not in (inherit if isinstance(inherit, list) else [inherit])
            except (ValueError, SyntaxError):
                is_new_model = False
        if is_new_model and "_description" not in assigns:
            report("ERREUR", path, node.lineno,
                   f"modèle `{node.name}` sans `_description`")

        for stmt in node.body:
            if isinstance(stmt, ast.FunctionDef) and stmt.name.startswith("_compute_"):
                has_depends = any(
                    "api.depends" in ast.unparse(d) for d in stmt.decorator_list
                )
                if not has_depends:
                    report("AVERTISSEMENT", path, stmt.lineno,
                           f"`{stmt.name}` sans `@api.depends` : "
                           "intentionnel uniquement si le champ n'est pas stocké")
                body = ast.unparse(stmt)
                if "for " not in body and "self." in body:
                    report("AVERTISSEMENT", path, stmt.lineno,
                           f"`{stmt.name}` n'itère pas sur `self`")


def check_xml(module: Path) -> None:
    patterns = [p for p in XML_PATTERNS if applies(p[3])]
    for path in sorted(module.rglob("*.xml")):
        raw = path.read_bytes()
        try:
            ET.fromstring(raw)
        except ET.ParseError as exc:
            line = exc.position[0] if exc.position else 0
            report("ERREUR", path, line, f"XML invalide : {exc}")
            continue

        text = raw.decode("utf-8", errors="replace")
        for num, line in enumerate(text.splitlines(), start=1):
            for pattern, severity, message, _scope in patterns:
                if re.search(pattern, line):
                    report(severity, path, num, message)


def check_manifest(module: Path) -> dict:
    manifest_path = module / "__manifest__.py"
    if not manifest_path.exists():
        report("ERREUR", module, 0, "`__manifest__.py` absent")
        return {}

    try:
        manifest = ast.literal_eval(manifest_path.read_text(encoding="utf-8"))
    except (ValueError, SyntaxError) as exc:
        report("ERREUR", manifest_path, 0, f"manifest illisible : {exc}")
        return {}
    if not isinstance(manifest, dict):
        report("ERREUR", manifest_path, 0, "le manifest doit être un dictionnaire")
        return {}

    for key in ("name", "author", "license"):
        if not manifest.get(key):
            report("ERREUR", manifest_path, 0, f"clé obligatoire manquante : `{key}`")

    version = str(manifest.get("version", ""))
    if version and not version.startswith(f"{SERIES}."):
        report("AVERTISSEMENT", manifest_path, 0,
               f"version `{version}` : préfixer par la série cible (`{SERIES}.x.y.z`)")

    removed = odoo_series.removed_modules(SERIES)
    for dep in manifest.get("depends", []):
        if dep in removed:
            hint = odoo_series.REPLACEMENTS.get(dep, f"supprimé en {SERIES}")
            report("ERREUR", manifest_path, 0, f"dépendance `{dep}` : {hint}")
        elif not (SOURCES / "addons" / dep).exists() \
                and not (ENTERPRISE / dep).exists() \
                and not (module.parent / dep).exists() \
                and dep not in {"base", "web"}:
            report("AVERTISSEMENT", manifest_path, 0,
                   f"dépendance `{dep}` introuvable dans les sources {SERIES} "
                   "ni à côté du module")

    seen_menu = False
    for rel in manifest.get("data", []) + manifest.get("demo", []):
        if not (module / rel).exists():
            report("ERREUR", manifest_path, 0, f"fichier de données absent : `{rel}`")
        if "menu" in Path(rel).name:
            seen_menu = True
        elif seen_menu and rel.startswith("views/"):
            report("AVERTISSEMENT", manifest_path, 0,
                   f"`{rel}` chargé après les menus : les menus doivent être en dernier")

    for bundle, assets in (manifest.get("assets") or {}).items():
        for asset in assets:
            spec = asset if isinstance(asset, str) else asset[-1]
            if any(c in spec for c in "*?[") or spec.startswith(("/", "http")):
                continue
            head, _, tail = spec.partition("/")
            if head == module.name and not (module / tail).exists():
                report("ERREUR", manifest_path, 0,
                       f"asset introuvable dans `{bundle}` : `{spec}`")

    return manifest


def declared_models(module: Path) -> tuple[dict[str, Path], set[str]]:
    """Modèles créés par le module (hors extensions), et ceux qui sont transients."""
    declared: dict[str, Path] = {}
    transient: set[str] = set()

    for path in module.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = {ast.unparse(b) for b in node.bases}
            if not any(b.startswith("models.") for b in bases):
                continue
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "_name" for t in stmt.targets
                ):
                    try:
                        name = ast.literal_eval(stmt.value)
                    except (ValueError, SyntaxError):
                        continue
                    inherits = [
                        s for s in node.body
                        if isinstance(s, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == "_inherit" for t in s.targets)
                    ]
                    inherited: list[str] = []
                    for s in inherits:
                        try:
                            val = ast.literal_eval(s.value)
                        except (ValueError, SyntaxError):
                            continue
                        inherited += val if isinstance(val, list) else [val]
                    if name in inherited:
                        continue  # extension d'un modèle existant
                    declared[name] = path
                    if "models.TransientModel" in bases or "models.AbstractModel" in bases:
                        transient.add(name)

    return declared, transient


def check_security(module: Path) -> None:
    declared, transient = declared_models(module)
    persistent = declared.keys() - transient

    # 19.4 fusionne droits d'accès et règles d'enregistrement dans `ir.access`.
    unified = odoo_series.has(SERIES, "ir_access_csv")
    csv_name = "ir.access.csv" if unified else "ir.model.access.csv"
    csv_path = module / "security" / csv_name
    legacy_path = module / "security" / "ir.model.access.csv"

    if unified and legacy_path.exists():
        report("ERREUR", legacy_path, 0,
               "`ir.model.access.csv` est remplacé par `security/ir.access.csv` "
               "(modèle `ir.access`, colonnes `model_id,group_id/id,operation,domain`)")

    covered: set[str] = set()
    if csv_path.exists():
        reader = csv.DictReader(io.StringIO(csv_path.read_text(encoding="utf-8")))
        expected = (
            ["id", "name", "model_id", "group_id/id", "operation", "domain"] if unified
            else ["id", "name", "model_id:id", "group_id:id",
                  "perm_read", "perm_write", "perm_create", "perm_unlink"]
        )
        if reader.fieldnames != expected:
            report("AVERTISSEMENT", csv_path, 1,
                   f"en-tête inattendu, attendu : {','.join(expected)}")
        group_column = "group_id/id" if unified else "group_id:id"
        for num, row in enumerate(reader, start=2):
            if unified:
                covered.add((row.get("model_id") or "").strip())
            else:
                ref = (row.get("model_id:id") or "").strip().split(".")[-1]
                covered.add(ref)
            if not (row.get(group_column) or "").strip():
                report("AVERTISSEMENT", csv_path, num,
                       f"`{row.get('id')}` sans groupe : droit accordé à tout le monde")
    elif persistent:
        report("ERREUR", module, 0,
               f"`security/{csv_name}` absent alors que le module déclare des modèles")

    for name in sorted(persistent):
        # L'XML ID d'un modèle est `model_` + son nom, points remplacés par `_`.
        expected_ref = name if unified else f"model_{name.replace('.', '_')}"
        if expected_ref not in covered:
            report("ERREUR", declared[name], 0,
                   f"modèle `{name}` sans ligne dans `security/{csv_name}`")

    # Multi-société : un company_id sans règle d'enregistrement est un classique.
    rules = " ".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in module.rglob("*.xml")
    )
    if unified:
        rules += " ".join(
            p.read_text(encoding="utf-8", errors="replace")
            for p in module.glob("security/ir.access.csv")
        )
    marker = "company_id" if unified else "ir.rule"
    for name, path in declared.items():
        if name in transient:
            continue
        src = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"company_id\s*=\s*fields\.Many2one", src) and marker not in rules:
            report("AVERTISSEMENT", path, 0,
                   f"`{name}` porte un `company_id` mais le module ne déclare aucune "
                   "règle multi-société")


def check_tests(module: Path) -> None:
    tests = module / "tests"
    if not tests.is_dir():
        report("AVERTISSEMENT", module, 0, "aucun répertoire `tests/`")
        return
    if not (tests / "__init__.py").exists():
        report("ERREUR", tests, 0, "`tests/__init__.py` absent : les tests ne seront pas chargés")
    files = list(tests.rglob("test_*.py"))
    if not files:
        report("AVERTISSEMENT", tests, 0, "aucun fichier `test_*.py`")
        return
    init = (tests / "__init__.py").read_text(encoding="utf-8", errors="replace") \
        if (tests / "__init__.py").exists() else ""
    for path in files:
        if path.parent == tests and path.stem not in init:
            report("ERREUR", path, 0,
                   f"`{path.stem}` non importé dans `tests/__init__.py`")


# --------------------------------------------------------------------------- #

def main(argv: list[str]) -> int:
    global SERIES, SOURCES, ENTERPRISE

    args = argv[1:]
    explicit_series = None
    if "--series" in args:
        index = args.index("--series")
        explicit_series = args[index + 1] if len(args) > index + 1 else None
        args = args[:index] + args[index + 2:]

    only: set[str] | None = None
    if "--only-files" in args:
        index = args.index("--only-files")
        rest = args[index + 1:]
        targets = [a for a in rest if Path(a).is_dir()]
        only = {str(Path(f).resolve()) for f in rest if f not in targets}
        args = args[:index] + targets

    if not args:
        print(__doc__)
        return 2

    for arg in args:
        module = Path(arg).resolve()
        if not (module / "__manifest__.py").exists():
            sub = [p.parent for p in module.glob("*/__manifest__.py")]
            if not sub:
                print(f"ERREUR  {module}  n'est pas un module Odoo (pas de __manifest__.py)")
                return 2
            modules = sub
        else:
            modules = [module]

        for mod in modules:
            info = odoo_series.resolve(mod, explicit_series)
            SERIES = info["series"]
            SOURCES = info["sources"]
            ENTERPRISE = info["enterprise"]
            print(f"── {mod.name}  ({mod})")
            print(f"   série cible : {SERIES}  (source : {info['origin']})")
            if not info["exact_sources"]:
                print(f"   ⚠️  sources {SERIES} absentes du poste, "
                      f"repli sur {SOURCES.name} pour la résolution des dépendances")
            check_manifest(mod)
            check_python(mod)
            check_xml(mod)
            check_security(mod)
            check_tests(mod)

    shown = findings
    if only is not None:
        hidden = len(findings)
        shown = [f for f in findings if str(Path(f[1]).resolve()) in only]
        hidden -= len(shown)
        if hidden:
            print(f"\n({hidden} anomalie(s) sur des fichiers non modifiés, masquées)")

    errors = warnings = infos = 0
    for severity, path, line, message in sorted(shown, key=lambda f: (f[1], f[2])):
        where = f"{path}:{line}" if line else str(path)
        print(f"{severity:14} {where}\n{'':14} {message}")
        errors += severity == "ERREUR"
        warnings += severity == "AVERTISSEMENT"
        infos += severity == "INFO"

    print(f"\n{errors} erreur(s), {warnings} avertissement(s), {infos} info(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
