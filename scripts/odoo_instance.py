#!/usr/bin/env python3
"""Accès déclaré aux bases Odoo distantes d'un projet (production, staging, test) — avec garde-fous.

Les identifiants vivent HORS des dépôts, dans `~/.odoo-agents/instances/<projet>.json`
(mode 600). Un agent ne les lit jamais autrement que par ce script, et ne les affiche jamais.

    odoo_instance.py add <projet>                 déclaration guidée (questions une à une)
    odoo_instance.py list <projet>                instances déclarées, sans secrets
    odoo_instance.py check <projet> <nom>         version + authentification (lecture seule)
    odoo_instance.py backup <projet> <nom> [--out fichier.zip]
                                                  télécharge une sauvegarde par /web/database/backup
                                                  (on-premise / Docker : demande le mot de passe maître)
    odoo_instance.py rpc <projet> <nom> <modèle> <méthode> [json-args] [--kwargs json]
                                                  appel XML-RPC ; écriture refusée en production sauf
                                                  --allow-write ET ODOO_PRODUCTION_CONFIRMED=<nom>

Règles, non négociables :
  - `kind = production` → LECTURE SEULE par défaut. Toute écriture exige que l'humain ait
    confirmé, dans la conversation, l'opération précise, puis la variable
    ODOO_PRODUCTION_CONFIRMED=<nom> sur la commande. Le script rappelle l'avertissement
    à chaque appel.
  - Pour tout ce qui dépasse la lecture (tests, reprise de données, captures), la voie
    normale est : `backup` puis `odoo-restore.sh`. On ne « teste » pas en production.
  - Une clé API (Préférences → Sécurité du compte → Nouvelle clé API) est préférée au
    mot de passe : révocable, sans 2FA, tracée.

Bibliothèque :

    from odoo_instance import Instance
    inst = Instance.load("rubixcomm", "staging")      # affiche l'avertissement si production
    inst.execute("sale.order", "search_read", [[("state", "=", "sale")]], fields=["name"], limit=5)
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import stat
import sys
import urllib.parse
import urllib.request
import xmlrpc.client
from dataclasses import dataclass, asdict
from pathlib import Path

STORE = Path(os.environ.get("ODOO_AGENTS_HOME", Path.home() / ".odoo-agents")) / "instances"
KINDS = ("production", "staging", "test", "local")
READ_METHODS = {"search", "search_read", "read", "search_count", "fields_get", "name_search",
                "read_group", "web_search_read", "web_read", "get_views", "check_access_rights",
                "default_get", "name_get", "get_metadata", "read_progress_bar", "web_read_group"}

BANNER = """
╔══════════════════════════════════════════════════════════════════════════════╗
║  ⚠️   BASE DE PRODUCTION : {name:<58} ║
║                                                                              ║
║  Tout ce que vous faites ici touche des données réelles et des utilisateurs  ║
║  en activité. Lecture seule par défaut. Aucune écriture, aucun test, aucune  ║
║  reprise de données sans confirmation explicite de l'humain pour CETTE       ║
║  opération. Pour expérimenter : sauvegarde + restauration locale.            ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""


@dataclass
class Instance:
    project: str
    name: str
    kind: str
    url: str
    db: str
    login: str
    secret: str = ""            # clé API ou mot de passe
    platform: str = ""          # odoo.sh | online | onpremise | docker
    notes: str = ""

    # -- stockage --------------------------------------------------------------
    @staticmethod
    def path(project: str) -> Path:
        return STORE / f"{project}.json"

    @classmethod
    def load_all(cls, project: str) -> dict[str, "Instance"]:
        p = cls.path(project)
        if not p.is_file():
            return {}
        data = json.loads(p.read_text())
        return {name: cls(project=project, name=name, **vals) for name, vals in data.items()}

    @classmethod
    def load(cls, project: str, name: str, *, quiet: bool = False) -> "Instance":
        all_ = cls.load_all(project)
        if name not in all_:
            known = ", ".join(all_) or "aucune"
            raise SystemExit(f"instance « {name} » inconnue pour {project} (déclarées : {known}). "
                             f"→ odoo_instance.py add {project}")
        inst = all_[name]
        if inst.is_production and not quiet:
            print(BANNER.format(name=f"{project} / {name} — {inst.url}"), file=sys.stderr)
        return inst

    def save(self) -> None:
        STORE.mkdir(parents=True, exist_ok=True)
        try:
            STORE.chmod(stat.S_IRWXU)
        except OSError:
            pass
        all_ = self.load_all(self.project)
        all_[self.name] = self
        data = {name: {k: v for k, v in asdict(inst).items() if k not in ("project", "name")}
                for name, inst in all_.items()}
        p = self.path(self.project)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        p.chmod(stat.S_IRUSR | stat.S_IWUSR)

    # -- accès -------------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.kind == "production"

    def _proxy(self, endpoint: str):
        return xmlrpc.client.ServerProxy(f"{self.url.rstrip('/')}/xmlrpc/2/{endpoint}", allow_none=True)

    def version(self) -> dict:
        return self._proxy("common").version()

    def uid(self) -> int:
        uid = self._proxy("common").authenticate(self.db, self.login, self.secret, {})
        if not uid:
            raise SystemExit(f"authentification refusée sur {self.url} / {self.db} ({self.login})")
        return uid

    def execute(self, model: str, method: str, *args, allow_write: bool = False, **kwargs):
        is_write = method not in READ_METHODS and not method.startswith(
            ("search", "read", "get_", "name_", "fields_", "web_read", "check_"))
        if self.is_production and is_write:
            confirmed = os.environ.get("ODOO_PRODUCTION_CONFIRMED") == self.name
            if not (allow_write and confirmed):
                raise SystemExit(
                    f"REFUSÉ : {model}.{method} est une écriture sur la PRODUCTION « {self.name} ».\n"
                    f"Il faut (1) la confirmation explicite de l'humain pour cette opération précise,\n"
                    f"(2) --allow-write / allow_write=True et (3) ODOO_PRODUCTION_CONFIRMED={self.name}.\n"
                    f"Sinon : sauvegarde + restauration locale (odoo-restore.sh)."
                )
            print(f"⚠️  ÉCRITURE EN PRODUCTION confirmée : {model}.{method}", file=sys.stderr)
        return self._proxy("object").execute_kw(self.db, self.uid(), self.secret, model, method, list(args), kwargs)

    def download_backup(self, out: Path, master_password: str, fmt: str = "zip") -> Path:
        """/web/database/backup — disponible on-premise et Docker (list_db / admin_passwd),
        pas sur Odoo.sh (utiliser l'onglet Backups) ni sur Odoo Online (Gestionnaire de bases)."""
        data = urllib.parse.urlencode({"master_pwd": master_password, "name": self.db,
                                       "backup_format": fmt}).encode()
        req = urllib.request.Request(f"{self.url.rstrip('/')}/web/database/backup", data=data)
        with urllib.request.urlopen(req, timeout=3600) as resp, open(out, "wb") as fh:
            ctype = resp.headers.get("Content-Type", "")
            if "text/html" in ctype:
                raise SystemExit("le serveur a renvoyé une page HTML : mot de passe maître refusé "
                                 "ou gestionnaire de bases désactivé (list_db = False)")
            while chunk := resp.read(1 << 20):
                fh.write(chunk)
        return out


# --- Commandes ------------------------------------------------------------------
def ask(prompt: str, default: str = "", choices: tuple[str, ...] | None = None,
        secret: bool = False, optional: bool = False) -> str:
    # getpass lit /dev/tty : on ne masque la saisie que dans un vrai terminal.
    reader = getpass.getpass if secret and sys.stdin.isatty() else input
    while True:
        suffix = f" [{default}]" if default else ""
        if choices:
            suffix = f" ({'/'.join(choices)}){suffix}"
        val = reader(f"{prompt}{suffix} : ").strip() or default
        if choices and val not in choices:
            print(f"  valeur attendue : {', '.join(choices)}")
            continue
        if val or secret or optional:
            return val


def cmd_add(args) -> int:
    print(f"Déclaration d'une instance Odoo pour le projet « {args.project} ».")
    print("Les identifiants sont enregistrés dans", Instance.path(args.project), "(mode 600, hors dépôt).\n")
    kind = ask("Type d'instance", "test", KINDS)
    if kind == "production":
        print(BANNER.format(name=args.project), file=sys.stderr)
        print("Préférez une clé API à un mot de passe (Préférences → Sécurité du compte → Nouvelle clé API).")
        print("Un compte en LECTURE SEULE dédié est encore mieux.")
        if ask("Confirmez-vous vouloir déclarer un accès à la PRODUCTION ? (tapez PRODUCTION)") != "PRODUCTION":
            print("Abandon.")
            return 1
    name = ask("Nom court de l'instance", kind)
    url = ask("URL (https://…)")
    db = ask("Nom de la base")
    login = ask("Identifiant (login)")
    secret = ask("Clé API ou mot de passe (saisie masquée)", secret=True)
    platform = ask("Hébergement", "odoo.sh" if url.endswith(".odoo.com") else "onpremise",
                   ("odoo.sh", "online", "onpremise", "docker"))
    notes = ask("Note (facultatif)", optional=True)
    inst = Instance(args.project, name, kind, url, db, login, secret, platform, notes)
    print("\nVérification de l'accès…")
    try:
        ver = inst.version().get("server_serie", "?")
        uid = inst.uid()
        print(f"  ✓ Odoo {ver}, uid={uid}")
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ {exc}")
        if ask("Enregistrer quand même ?", "n", ("o", "n")) == "n":
            return 1
    inst.save()
    print(f"Enregistré : {args.project} / {name} ({kind}).")
    return 0


def cmd_list(args) -> int:
    all_ = Instance.load_all(args.project)
    if not all_:
        print(f"Aucune instance déclarée pour {args.project}. → odoo_instance.py add {args.project}")
        return 1
    for inst in all_.values():
        flag = "  ⚠️ PRODUCTION — lecture seule" if inst.is_production else ""
        print(f"{inst.name:<12} {inst.kind:<10} {inst.url}  db={inst.db}  login={inst.login}  [{inst.platform}]{flag}")
        if inst.notes:
            print(f"{'':<12} {inst.notes}")
    return 0


def cmd_check(args) -> int:
    inst = Instance.load(args.project, args.name)
    ver = inst.version()
    uid = inst.uid()
    print(f"✓ {inst.url} — Odoo {ver.get('server_serie')} ({ver.get('server_version')}), base {inst.db}, uid {uid}")
    mods = inst.execute("ir.module.module", "search_read",
                        [("state", "=", "installed"), ("author", "not ilike", "Odoo")],
                        fields=["name", "installed_version"], order="name")
    if mods:
        print("Modules non Odoo installés :", ", ".join(f"{m['name']} {m['installed_version']}" for m in mods))
    return 0


def cmd_backup(args) -> int:
    inst = Instance.load(args.project, args.name)
    if inst.platform == "odoo.sh":
        raise SystemExit("Odoo.sh : télécharger la sauvegarde depuis l'onglet Backups de la branche "
                         "(format « dump + filestore »), puis odoo-restore.sh <fichier.zip>.")
    if inst.platform == "online":
        raise SystemExit("Odoo Online : Gestionnaire de bases (odoo.com/my/databases) → Télécharger, "
                         "puis odoo-restore.sh <fichier.zip>.")
    if inst.is_production and os.environ.get("ODOO_PRODUCTION_CONFIRMED") != inst.name:
        raise SystemExit("Sauvegarde d'une PRODUCTION : charge lourde sur le serveur pendant l'export.\n"
                         f"Confirmer avec l'humain, puis relancer avec ODOO_PRODUCTION_CONFIRMED={inst.name}.")
    out = Path(args.out or f"{inst.project}-{inst.name}-{inst.db}.zip")
    master = getpass.getpass("Mot de passe maître (admin_passwd) : ")
    print(f"Téléchargement vers {out}…")
    inst.download_backup(out, master)
    print(f"✓ {out} ({out.stat().st_size // (1 << 20)} Mo) → odoo-restore.sh {out}")
    return 0


def cmd_rpc(args) -> int:
    inst = Instance.load(args.project, args.name)
    rpc_args = json.loads(args.args) if args.args else []
    kwargs = json.loads(args.kwargs) if args.kwargs else {}
    result = inst.execute(args.model, args.method, *rpc_args, allow_write=args.allow_write, **kwargs)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add"); p.add_argument("project"); p.set_defaults(fn=cmd_add)
    p = sub.add_parser("list"); p.add_argument("project"); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("check"); p.add_argument("project"); p.add_argument("name"); p.set_defaults(fn=cmd_check)
    p = sub.add_parser("backup"); p.add_argument("project"); p.add_argument("name"); p.add_argument("--out")
    p.set_defaults(fn=cmd_backup)
    p = sub.add_parser("rpc"); p.add_argument("project"); p.add_argument("name")
    p.add_argument("model"); p.add_argument("method"); p.add_argument("args", nargs="?")
    p.add_argument("--kwargs"); p.add_argument("--allow-write", action="store_true"); p.set_defaults(fn=cmd_rpc)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
