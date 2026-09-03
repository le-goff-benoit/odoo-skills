#!/usr/bin/env python3
"""Résolution de la série Odoo cible d'un module ou d'un projet.

Le poste héberge plusieurs séries de sources et le parc de modules custom est
mélangé (17.0, 18.0, 19.0, saas~19.x). Écrire du 19.0 dans un module 18.0 le
casse, et linter du 18.0 avec les règles 19.0 produit de fausses erreurs.
Tout l'outillage passe donc par ce module pour savoir *de quelle série on parle*.

Ordre de résolution (le premier qui répond gagne) :
  1. `--series` / `$ODOO_SERIES`
  2. `.odoo-agents/config` à la racine du projet  (ligne `series = 18.0`)
  3. le préfixe de `version` dans le `__manifest__.py` du module
  4. la série par défaut (`DEFAULT_SERIES`)

Usage :
    odoo_series.py <chemin> [--series X]     # affiche les variables shell
    from odoo_series import resolve          # côté Python
"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

SOURCES_ROOT = Path(os.environ.get("ODOO_SOURCES_DIR", Path.home() / "odoo-sources"))
DEFAULT_SERIES = "19.0"

# Capacités du framework, indexées par la série où elles deviennent la forme
# attendue. Vérifié par comptage dans les sources locales (cf. SERIES_MATRIX.md).
FEATURES = {
    "no_attrs": "17.0",          # attrs= / states= supprimés des vues
    "no_name_get": "17.0",       # name_get() -> _compute_display_name()
    "list_tag": "18.0",          # <tree> -> <list>
    "chatter_tag": "18.0",       # <div class="oe_chatter"> -> <chatter/>
    "env_translate": "18.0",     # self.env._()
    "api_readonly": "18.0",      # @api.readonly
    "models_constraint": "19.0",  # _sql_constraints -> models.Constraint
    "domain_object": "19.0",     # from odoo.fields import Domain
    "groups_privilege": "19.0",  # res.groups.privilege
    "group_ids_rename": "19.0",  # res.users.groups_id -> group_ids
    "env_cr_props": "19.0",      # self._cr/_uid/_context dépréciés
    "hr_version": "19.0",        # hr.contract -> hr.version
    "ir_access_csv": "19.4",     # ir.model.access.csv + ir.rule -> ir.access.csv
}

# Modules communautaires supprimés, par série d'introduction de la suppression.
REMOVED = {
    "19.0": {
        "account_edi_ubl_cii_tax_extension", "account_peppol_selfbilling",
        "auth_totp_mail_enforce", "hr_contract", "hr_holidays_contract",
        "hr_work_entry_contract", "hw_drivers", "hw_escpos", "hw_posbox_homepage",
        "membership", "payment_razorpay_oauth", "pos_epson_printer", "pos_paytm",
        "pos_self_order_epson_printer", "pos_six", "pos_viva_wallet",
        "product_images", "sale_async_emails", "test_hr_contract_calendar",
        "web_editor", "website_event_jitsi", "website_event_meet",
        "website_event_meet_quiz", "website_jitsi", "website_membership",
        "website_payment_authorize",
    },
}

REPLACEMENTS = {
    "hr_contract": "fusionné dans `hr` — le contrat est devenu le modèle `hr.version`",
    "hr_work_entry_contract": "fusionné dans `hr_work_entry`",
    "web_editor": "remplacé par `html_builder`",
    "membership": "supprimé",
    "product_images": "supprimé",
}


def key(series: str) -> tuple[int, int]:
    """`'19.4'` → `(19, 4)`, pour comparer deux séries."""
    match = re.match(r"(\d+)\.(\d+)", str(series))
    return (int(match[1]), int(match[2])) if match else (0, 0)


def available() -> list[str]:
    """Séries dont les sources sont présentes sur le poste, ordre croissant."""
    found = [
        p.name for p in SOURCES_ROOT.iterdir()
        if p.is_dir() and re.fullmatch(r"\d+\.\d+", p.name)
    ]
    return sorted(found, key=key)


def nearest(series: str) -> str:
    """Série de sources la plus proche disponible localement (borne basse)."""
    got = available()
    if series in got:
        return series
    lower = [s for s in got if key(s) <= key(series)]
    return lower[-1] if lower else (got[0] if got else DEFAULT_SERIES)


def ruff_config(series: str) -> Path:
    """`ruff.toml` officiel le plus proche.

    Seule la 19.0 publie un `ruff.toml` sur ce poste ; les séries antérieures
    n'en ont pas. Les familles de règles sélectionnées sont du style Python pur
    (imports, f-strings dans les logs, virgules finales) : elles s'appliquent
    telles quelles à un module 17/18. Ce qui diffère entre séries, ce sont les
    motifs Odoo — c'est `odoo_lint.py` qui les porte, pas `ruff`.
    """
    got = available()
    later = [s for s in got if key(s) >= key(series)]
    earlier = [s for s in reversed(got) if key(s) < key(series)]
    for candidate in later + earlier:
        config = SOURCES_ROOT / candidate / "ruff.toml"
        if config.is_file():
            return config
    return SOURCES_ROOT / DEFAULT_SERIES / "ruff.toml"


def has(series: str, feature: str) -> bool:
    """La série `series` attend-elle la forme `feature` ?"""
    since = FEATURES.get(feature)
    return bool(since) and key(series) >= key(since)


def removed_modules(series: str) -> set[str]:
    out: set[str] = set()
    for when, modules in REMOVED.items():
        if key(series) >= key(when):
            out |= modules
    return out


def project_root(path: Path) -> Path | None:
    """Remonte jusqu'au dossier portant `.odoo-agents/` ou `.git/`."""
    for candidate in [path, *path.parents]:
        if (candidate / ".odoo-agents").is_dir() or (candidate / ".git").exists():
            return candidate
    return None


def _from_config(path: Path) -> str | None:
    root = project_root(path)
    if not root:
        return None
    config = root / ".odoo-agents" / "config"
    if not config.is_file():
        return None
    for line in config.read_text(encoding="utf-8", errors="replace").splitlines():
        found = re.match(r"\s*series\s*[=:]\s*([\d.]+)", line)
        if found:
            return found[1]
    return None


def _from_manifest(path: Path) -> str | None:
    module = path if (path / "__manifest__.py").exists() else None
    if module is None:
        for candidate in sorted(path.glob("*/__manifest__.py")):
            module = candidate.parent
            break
    if module is None:
        return None
    try:
        manifest = ast.literal_eval((module / "__manifest__.py").read_text(encoding="utf-8"))
    except (OSError, ValueError, SyntaxError):
        return None
    found = re.match(r"(\d+\.\d+)\.", str(manifest.get("version", "")))
    return found[1] if found else None


def resolve(path: str | Path, explicit: str | None = None) -> dict:
    """Renvoie la série cible et les chemins de sources associés."""
    path = Path(path).resolve()
    series = (
        explicit
        or os.environ.get("ODOO_SERIES")
        or _from_config(path)
        or _from_manifest(path)
        or DEFAULT_SERIES
    )
    origin = (
        "explicite" if explicit else
        "$ODOO_SERIES" if os.environ.get("ODOO_SERIES") else
        ".odoo-agents/config" if _from_config(path) else
        "__manifest__.py" if _from_manifest(path) else
        "défaut"
    )
    sources = SOURCES_ROOT / nearest(series)
    return {
        "series": series,
        "origin": origin,
        "sources": sources,
        "enterprise": SOURCES_ROOT / f"{nearest(series)}-enterprise",
        "ruff_config": ruff_config(series),
        "docker_image": f"odoo:{series}",
        "exact_sources": (SOURCES_ROOT / series).is_dir(),
    }


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if a != "--series"]
    explicit = None
    if "--series" in argv:
        index = argv.index("--series")
        explicit = argv[index + 1] if len(argv) > index + 1 else None
        args = [a for a in args if a != explicit]
    if not args:
        print(__doc__)
        return 2

    info = resolve(args[0], explicit)
    for name, value in info.items():
        print(f"ODOO_{name.upper()}={value}")
    if not info["exact_sources"]:
        print(f"# sources {info['series']} absentes : repli sur {info['sources'].name}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
