#!/usr/bin/env python3
"""Environnements Odoo d'un projet (production, staging, test, local) — déclarés une fois,
lus par les agents sans jamais voir un secret.

Deux niveaux de stockage, par conception :

  - `<projet>/.odoo-agents/instances.json` — ce qui se partage et se commite : nom,
    type, URL, base, hébergement, note. AUCUN secret, AUCUN identifiant personnel.
    Un collègue qui clone le projet voit les environnements ; il n'a plus qu'à
    ajouter *sa* clé dans *son* trousseau.
  - le TROUSSEAU du bureau (GNOME Keyring / libsecret) — l'identifiant et la clé API
    (ou le mot de passe) de la personne, chiffrés au repos, déverrouillés avec la
    session ; jamais sur le disque en clair, jamais dans la conversation. Repli
    sans trousseau (session SSH sans D-Bus) : `~/.odoo-agents/instances/<projet>.json`
    en mode 600, ou `ODOO_INSTANCE_LOGIN` / `ODOO_INSTANCE_SECRET` dans l'environnement.

Déclarer un environnement se fait dans une BOÎTE DE DIALOGUE du bureau (zenity) :
le secret va du clavier au trousseau sans passer par le terminal ni par l'agent.

    odoo_instance.py add     <projet>              déclarer un environnement (dialogue)
    odoo_instance.py secret  <projet> <nom>        (re)saisir identifiant + clé, ou le mot de passe maître
    odoo_instance.py list    <projet>              environnements déclarés, sans secret
    odoo_instance.py check   <projet> <nom>        joignable ? version ? série cohérente avec le projet ?
    odoo_instance.py backup  <projet> <nom> [--out fichier.zip]     (on-premise / Docker)
    odoo_instance.py rpc     <projet> <nom> <modèle> <méthode> [json-args] [--kwargs json]
    odoo_instance.py migrate <projet>              ancien fichier ~/.odoo-agents → projet + trousseau
    odoo_instance.py remove  <projet> <nom>

`<projet>` est un nom (`~/<projet>`) ou un chemin ; sans lui, le projet courant.

Règles, non négociables :
  - `kind = production` → LECTURE SEULE par défaut. Toute écriture exige la confirmation
    de l'humain, dans la conversation, pour l'opération précise, puis
    ODOO_PRODUCTION_CONFIRMED=<nom> sur la commande. Le script rappelle l'avertissement.
  - Tests, captures, reprises de données : sur une copie locale (`backup` + `odoo-restore.sh`).
  - Clé API (Préférences → Sécurité du compte → Nouvelle clé API) plutôt que mot de passe :
    révocable, tracée, hors 2FA. Compte en lecture seule pour la production.

Bibliothèque :

    from odoo_instance import Instance
    inst = Instance.load("rubixcomm", "staging")
    inst.execute("sale.order", "search_read", [[("state", "=", "sale")]], fields=["name"], limit=5)
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import stat
import subprocess
import sys
import urllib.parse
import urllib.request
import xmlrpc.client
from dataclasses import dataclass, asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

LEGACY_STORE = Path(os.environ.get("ODOO_AGENTS_HOME", Path.home() / ".odoo-agents")) / "instances"
KINDS = ("production", "staging", "test", "local")
PLATFORMS = ("odoo.sh", "online", "onpremise", "docker")
META_FIELDS = ("kind", "url", "db", "platform", "notes")
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


# --------------------------------------------------------------------------- #
# Projet
# --------------------------------------------------------------------------- #

def project_root(project: str | None) -> Path | None:
    """`<projet>` = chemin, ou nom sous $HOME, ou rien (projet courant)."""
    candidates = []
    if project:
        candidates += [Path(project), Path.home() / project]
    candidates.append(Path.cwd())
    for c in candidates:
        c = c.expanduser().resolve()
        for probe in [c, *c.parents]:
            if (probe / ".odoo-agents").is_dir():
                return probe
    return None


def project_name(project: str | None) -> str:
    root = project_root(project)
    return root.name if root else (Path(project).name if project else Path.cwd().name)


def project_file(project: str | None) -> Path | None:
    root = project_root(project)
    return root / ".odoo-agents" / "instances.json" if root else None


# --------------------------------------------------------------------------- #
# Trousseau (libsecret / GNOME Keyring)
# --------------------------------------------------------------------------- #

def _keyring_attrs(project: str, name: str) -> dict[str, str]:
    return {"application": "odoo-agents", "project": project, "instance": name}


def _keyring_collection():
    """Collection par défaut du trousseau, déverrouillée ; None si indisponible."""
    try:
        import secretstorage  # noqa: PLC0415
        bus = secretstorage.dbus_init()
        coll = secretstorage.get_default_collection(bus)
        if coll.is_locked():
            coll.unlock()
        return None if coll.is_locked() else coll
    except Exception:  # noqa: BLE001 — pas de D-Bus, pas de trousseau, module absent
        return None


def keyring_available() -> bool:
    return _keyring_collection() is not None


def keyring_get(project: str, name: str) -> dict | None:
    """{"login", "secret", "master"?} ou None. Tolère l'ancien format (secret nu)."""
    coll = _keyring_collection()
    if coll is None:
        return None
    for item in coll.search_items(_keyring_attrs(project, name)):
        raw = item.get_secret().decode("utf-8")
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {"secret": raw}
        except ValueError:
            return {"secret": raw}
    return None


def keyring_set(project: str, name: str, data: dict) -> bool:
    coll = _keyring_collection()
    if coll is None:
        return False
    current = keyring_get(project, name) or {}
    current.update({k: v for k, v in data.items() if v is not None})
    coll.create_item(f"Odoo {project} / {name} (odoo-agents)", _keyring_attrs(project, name),
                     json.dumps(current).encode("utf-8"), replace=True)
    return True


def keyring_delete(project: str, name: str) -> None:
    coll = _keyring_collection()
    if coll is None:
        return
    for item in coll.search_items(_keyring_attrs(project, name)):
        item.delete()


# --------------------------------------------------------------------------- #
# Instance
# --------------------------------------------------------------------------- #

@dataclass
class Instance:
    project: str
    name: str
    kind: str
    url: str
    db: str
    login: str = ""
    secret: str = ""            # clé API ou mot de passe — jamais écrit dans le projet
    platform: str = ""          # odoo.sh | online | onpremise | docker
    notes: str = ""
    master: str = ""            # mot de passe maître (backup), trousseau seulement

    # -- lecture ---------------------------------------------------------------
    @classmethod
    def load_all(cls, project: str | None) -> dict[str, "Instance"]:
        pname = project_name(project)
        out: dict[str, Instance] = {}
        pfile = project_file(project)
        if pfile and pfile.is_file():
            for name, meta in json.loads(pfile.read_text(encoding="utf-8")).items():
                out[name] = cls(project=pname, name=name, **{k: meta.get(k, "") for k in META_FIELDS})
        legacy = LEGACY_STORE / f"{pname}.json"
        if legacy.is_file():
            for name, vals in json.loads(legacy.read_text()).items():
                if name in out:
                    continue
                inst = cls(project=pname, name=name,
                           **{k: v for k, v in vals.items() if k in META_FIELDS or k in ("login", "secret")})
                if inst.secret == "@keyring":
                    inst.secret = ""
                out[name] = inst
        for inst in out.values():
            creds = keyring_get(pname, inst.name) or {}
            inst.login = os.environ.get("ODOO_INSTANCE_LOGIN") or creds.get("login") or inst.login
            inst.secret = os.environ.get("ODOO_INSTANCE_SECRET") or creds.get("secret") or inst.secret
            inst.master = creds.get("master", "")
        return out

    @classmethod
    def load(cls, project: str | None, name: str, *, quiet: bool = False) -> "Instance":
        all_ = cls.load_all(project)
        if name not in all_:
            known = ", ".join(all_) or "aucune"
            raise SystemExit(f"environnement « {name} » inconnu pour {project_name(project)} "
                             f"(déclarés : {known}). → odoo_instance.py add {project or '.'}")
        inst = all_[name]
        if inst.is_production and not quiet:
            print(BANNER.format(name=f"{inst.project} / {name} — {inst.url}"), file=sys.stderr)
        return inst

    @property
    def has_credentials(self) -> bool:
        return bool(self.login and self.secret)

    # -- écriture --------------------------------------------------------------
    def save(self, project: str | None = None) -> str:
        """Métadonnées dans le projet, identifiants dans le trousseau (ou repli 600)."""
        pfile = project_file(project or self.project)
        if pfile is None:
            raise SystemExit("aucun projet trouvé (dossier .odoo-agents/) : lancer odoo_project_scan.py "
                             "sur la racine du projet, ou passer son chemin")
        data = json.loads(pfile.read_text(encoding="utf-8")) if pfile.is_file() else {}
        data[self.name] = {k: getattr(self, k) for k in META_FIELDS}
        pfile.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        creds = {"login": self.login, "secret": self.secret}
        if self.master:
            creds["master"] = self.master
        if keyring_set(self.project, self.name, creds):
            return "trousseau"
        LEGACY_STORE.mkdir(parents=True, exist_ok=True)
        try:
            LEGACY_STORE.chmod(stat.S_IRWXU)
        except OSError:
            pass
        legacy = LEGACY_STORE / f"{self.project}.json"
        raw = json.loads(legacy.read_text()) if legacy.is_file() else {}
        raw[self.name] = {**{k: getattr(self, k) for k in META_FIELDS}, "login": self.login,
                          "secret": self.secret}
        legacy.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n")
        legacy.chmod(stat.S_IRUSR | stat.S_IWUSR)
        return "fichier (trousseau indisponible)"

    # -- accès -------------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.kind == "production"

    def _proxy(self, endpoint: str):
        return xmlrpc.client.ServerProxy(f"{self.url.rstrip('/')}/xmlrpc/2/{endpoint}", allow_none=True)

    def version(self) -> dict:
        return self._proxy("common").version()

    def uid(self) -> int:
        if not self.has_credentials:
            raise SystemExit(
                f"aucun identifiant pour {self.project} / {self.name} dans votre trousseau : "
                f"`odoo_instance.py secret {self.project} {self.name}` (ou session verrouillée / SSH "
                "sans D-Bus : déverrouiller, ou ODOO_INSTANCE_LOGIN + ODOO_INSTANCE_SECRET).")
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
        """/web/database/backup — on-premise et Docker (list_db / admin_passwd) ;
        pas sur Odoo.sh (onglet Backups) ni Odoo Online (Gestionnaire de bases)."""
        data = urllib.parse.urlencode({"master_pwd": master_password, "name": self.db,
                                       "backup_format": fmt}).encode()
        req = urllib.request.Request(f"{self.url.rstrip('/')}/web/database/backup", data=data)
        with urllib.request.urlopen(req, timeout=3600) as resp, open(out, "wb") as fh:
            if "text/html" in resp.headers.get("Content-Type", ""):
                raise SystemExit("le serveur a renvoyé une page HTML : mot de passe maître refusé "
                                 "ou gestionnaire de bases désactivé (list_db = False)")
            while chunk := resp.read(1 << 20):
                fh.write(chunk)
        return out


# --------------------------------------------------------------------------- #
# Saisie : dialogue du bureau, sinon terminal
# --------------------------------------------------------------------------- #

def gui_available() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")) \
        and shutil.which("zenity") is not None


def zenity(*args: str) -> str | None:
    """Lance zenity ; None si annulé."""
    try:
        out = subprocess.run(["zenity", *args], capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.rstrip("\n") if out.returncode == 0 else None


def ask(prompt: str, default: str = "", choices: tuple[str, ...] | None = None,
        secret: bool = False, optional: bool = False) -> str:
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


def guess_platform(url: str) -> str:
    host = urllib.parse.urlparse(url).hostname or ""
    if host.endswith(".odoo.com"):
        return "online" if host.count(".") == 2 and not host.endswith(".dev.odoo.com") else "odoo.sh"
    return "onpremise"


def guess_kind(url: str, name: str) -> str:
    host = urllib.parse.urlparse(url).hostname or ""
    low = (name + host).lower()
    if "prod" in low:
        return "production"
    if "staging" in low or "preprod" in low:
        return "staging"
    if "localhost" in host or host.startswith("127."):
        return "local"
    return "test"


def dialog_declare(pname: str, use_gui: bool) -> dict | None:
    """Renvoie {name, kind, url, db, platform, notes, login, secret} ou None (annulé)."""
    if use_gui:
        out = zenity("--forms", f"--title=Environnement Odoo — {pname}",
                     "--text=Déclarer un environnement. La clé va directement dans votre trousseau.\n"
                     "Préférez une clé API (Préférences → Sécurité du compte) à un mot de passe.",
                     "--add-entry=Nom court (production, staging, test…)",
                     "--add-combo=Type", f"--combo-values={'|'.join(KINDS)}",
                     "--add-entry=URL (https://…)",
                     "--add-entry=Nom de la base",
                     "--add-combo=Hébergement", f"--combo-values={'|'.join(PLATFORMS)}",
                     "--add-entry=Identifiant (login)",
                     "--add-password=Clé API ou mot de passe",
                     "--add-entry=Note (facultatif)",
                     "--separator=\x1f", "--width=520")
        if out is None:
            return None
        name, kind, url, db, platform, login, secret, notes = (out.split("\x1f") + [""] * 8)[:8]
        name = name.strip() or kind or guess_kind(url, "")
        kind = kind or guess_kind(url, name)
        platform = platform or guess_platform(url)
        if kind == "production":
            ok = zenity("--question", "--title=PRODUCTION", "--width=480",
                        f"--text=Vous déclarez un accès à la PRODUCTION de {pname}.\n\n"
                        "Les agents n'y feront que de la lecture ; toute écriture vous sera demandée "
                        "explicitement, opération par opération.\n\nConfirmer ?")
            if ok is None:
                return None
        return dict(name=name, kind=kind, url=url.strip(), db=db.strip(), platform=platform,
                    notes=notes.strip(), login=login.strip(), secret=secret)

    print(f"Déclaration d'un environnement Odoo pour « {pname} ».")
    kind = ask("Type", "test", KINDS)
    if kind == "production":
        print(BANNER.format(name=pname), file=sys.stderr)
        if ask("Confirmez-vous vouloir déclarer un accès à la PRODUCTION ? (tapez PRODUCTION)") != "PRODUCTION":
            return None
    name = ask("Nom court", kind)
    url = ask("URL (https://…)")
    db = ask("Nom de la base")
    platform = ask("Hébergement", guess_platform(url), PLATFORMS)
    login = ask("Identifiant (login)")
    secret = ask("Clé API ou mot de passe (saisie masquée)", secret=True)
    notes = ask("Note (facultatif)", optional=True)
    return dict(name=name, kind=kind, url=url, db=db, platform=platform, notes=notes,
                login=login, secret=secret)


def dialog_credentials(pname: str, name: str, use_gui: bool, current_login: str = "",
                       master: bool = False) -> tuple[str, str] | None:
    if master:
        if use_gui:
            val = zenity("--password", f"--title=Mot de passe maître — {pname} / {name}")
            return ("", val) if val is not None else None
        return ("", getpass.getpass("Mot de passe maître (admin_passwd) : "))
    if use_gui:
        out = zenity("--forms", f"--title=Identifiants — {pname} / {name}",
                     "--text=Vos identifiants pour cet environnement (trousseau personnel).",
                     "--add-entry=Identifiant (login)", "--add-password=Clé API ou mot de passe",
                     "--separator=\x1f")
        if out is None:
            return None
        login, secret = (out.split("\x1f") + [""])[:2]
        return (login.strip() or current_login, secret)
    login = ask("Identifiant (login)", current_login)
    secret = ask("Clé API ou mot de passe (saisie masquée)", secret=True)
    return (login, secret)


# --------------------------------------------------------------------------- #
# Commandes
# --------------------------------------------------------------------------- #

def cmd_add(args) -> int:
    pname = project_name(args.project)
    if project_file(args.project) is None:
        raise SystemExit(f"projet introuvable : {args.project or os.getcwd()} (pas de .odoo-agents/) — "
                         "odoo_project_scan.py <racine> d'abord")
    use_gui = gui_available() and not args.no_gui
    where_secret = "le trousseau du bureau" if keyring_available() else \
        f"{LEGACY_STORE} (mode 600 — trousseau indisponible)"
    print(f"Métadonnées → {project_file(args.project)} (à commiter, sans secret) ; "
          f"identifiants → {where_secret}.")
    vals = dialog_declare(pname, use_gui)
    if vals is None:
        print("Abandon.")
        return 1
    inst = Instance(project=pname, **vals)
    print("Vérification de l'accès…")
    try:
        ver = inst.version().get("server_serie", "?")
        uid = inst.uid()
        print(f"  ✓ Odoo {ver}, uid={uid}")
        warn_series(args.project, ver)
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ {exc}")
        keep = zenity("--question", "--text=La vérification a échoué. Enregistrer quand même ?") is not None \
            if use_gui else ask("Enregistrer quand même ?", "n", ("o", "n")) == "o"
        if not keep:
            return 1
    where = inst.save(args.project)
    print(f"Enregistré : {pname} / {inst.name} ({inst.kind}, {inst.platform}) — identifiants dans {where}.")
    return 0


def warn_series(project: str | None, server_serie: str) -> None:
    try:
        import odoo_series  # noqa: PLC0415
        root = project_root(project)
        if root:
            local = odoo_series.resolve(root)["series"]
            remote = server_serie.replace("saas~", "")
            if remote and local and remote != local:
                print(f"  ⚠️ série du projet {local}, série de l'instance {server_serie} : "
                      "vérifier .odoo-agents/config")
    except Exception:  # noqa: BLE001
        pass


def cmd_secret(args) -> int:
    inst = Instance.load(args.project, args.name, quiet=True)
    use_gui = gui_available() and not args.no_gui
    res = dialog_credentials(inst.project, inst.name, use_gui, inst.login, master=args.master)
    if res is None:
        print("Abandon.")
        return 1
    login, secret = res
    if args.master:
        ok = keyring_set(inst.project, inst.name, {"master": secret})
        print("Mot de passe maître enregistré dans le trousseau." if ok else "Trousseau indisponible.")
        return 0 if ok else 1
    inst.login, inst.secret = login, secret
    try:
        print(f"  ✓ uid={inst.uid()} sur {inst.url}")
    except SystemExit as exc:
        print(f"  ✗ {exc}")
        if not (ask("Enregistrer quand même ?", "n", ("o", "n")) == "o" if not use_gui else
                zenity("--question", "--text=Authentification refusée. Enregistrer quand même ?") is not None):
            return 1
    ok = keyring_set(inst.project, inst.name, {"login": login, "secret": secret})
    print("Identifiants enregistrés dans le trousseau." if ok else
          "Trousseau indisponible : relancer dans une session de bureau, ou ODOO_INSTANCE_LOGIN/SECRET.")
    return 0 if ok else 1


def cmd_list(args) -> int:
    all_ = Instance.load_all(args.project)
    pname = project_name(args.project)
    if not all_:
        print(f"Aucun environnement déclaré pour {pname}. → odoo_instance.py add {args.project or '.'}")
        return 1
    for inst in all_.values():
        flag = "  ⚠️ PRODUCTION — lecture seule" if inst.is_production else ""
        creds = "identifiants: ✓ trousseau" if inst.has_credentials else "identifiants: ✗ manquants (odoo_instance.py secret)"
        print(f"{inst.name:<12} {inst.kind:<10} {inst.url}  db={inst.db}  [{inst.platform}]  {creds}{flag}")
        if inst.notes:
            print(f"{'':<12} {inst.notes}")
    return 0


def cmd_check(args) -> int:
    inst = Instance.load(args.project, args.name)
    ver = inst.version()
    uid = inst.uid()
    print(f"✓ {inst.url} — Odoo {ver.get('server_serie')} ({ver.get('server_version')}), base {inst.db}, uid {uid}")
    warn_series(args.project, str(ver.get("server_serie", "")))
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
    master = inst.master
    if not master:
        res = dialog_credentials(inst.project, inst.name, gui_available() and not args.no_gui, master=True)
        if res is None:
            return 1
        master = res[1]
        keyring_set(inst.project, inst.name, {"master": master})
    print(f"Téléchargement vers {out}…")
    inst.download_backup(out, master)
    print(f"✓ {out} ({out.stat().st_size // (1 << 20)} Mo) → odoo-restore.sh {out}")
    return 0


def cmd_migrate(args) -> int:
    """Ancien fichier ~/.odoo-agents/instances/<projet>.json → projet + trousseau."""
    pname = project_name(args.project)
    legacy = LEGACY_STORE / f"{pname}.json"
    if not legacy.is_file():
        print(f"rien à migrer ({legacy} absent)")
        return 0
    if project_file(args.project) is None:
        raise SystemExit("projet introuvable : passer son chemin")
    moved = 0
    for name, vals in json.loads(legacy.read_text()).items():
        creds = keyring_get(pname, name) or {}
        secret = creds.get("secret") or (vals.get("secret") if vals.get("secret") != "@keyring" else "")
        inst = Instance(project=pname, name=name, login=creds.get("login") or vals.get("login", ""),
                        secret=secret or "", **{k: vals.get(k, "") for k in META_FIELDS})
        where = inst.save(args.project)
        moved += 1
        print(f"  ✓ {pname} / {name} → {project_file(args.project)} + {where}")
    if keyring_available():
        legacy.unlink()
        print(f"{moved} environnement(s) migré(s) ; {legacy} supprimé (plus aucun secret sur le disque).")
    else:
        print(f"{moved} environnement(s) migré(s) ; {legacy} conservé (trousseau indisponible).")
    return 0


def cmd_remove(args) -> int:
    pname = project_name(args.project)
    pfile = project_file(args.project)
    removed = False
    if pfile and pfile.is_file():
        data = json.loads(pfile.read_text(encoding="utf-8"))
        if args.name in data:
            del data[args.name]
            pfile.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            removed = True
    legacy = LEGACY_STORE / f"{pname}.json"
    if legacy.is_file():
        raw = json.loads(legacy.read_text())
        if args.name in raw:
            del raw[args.name]
            legacy.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n")
            removed = True
    keyring_delete(pname, args.name)
    print(f"Supprimé : {pname} / {args.name} (projet, fichier et trousseau)." if removed
          else f"{args.name} : inconnu dans le projet ; trousseau nettoyé.")
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

    def proj(p):
        p.add_argument("project", nargs="?", default=None, help="nom (~/<projet>) ou chemin ; défaut : projet courant")
        p.add_argument("--no-gui", action="store_true", help="saisie au terminal plutôt que dans une boîte de dialogue")

    p = sub.add_parser("add"); proj(p); p.set_defaults(fn=cmd_add)
    p = sub.add_parser("secret"); proj(p); p.add_argument("name"); p.add_argument("--master", action="store_true")
    p.set_defaults(fn=cmd_secret)
    p = sub.add_parser("list"); proj(p); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("check"); proj(p); p.add_argument("name"); p.set_defaults(fn=cmd_check)
    p = sub.add_parser("backup"); proj(p); p.add_argument("name"); p.add_argument("--out"); p.set_defaults(fn=cmd_backup)
    p = sub.add_parser("migrate"); proj(p); p.set_defaults(fn=cmd_migrate)
    p = sub.add_parser("remove"); proj(p); p.add_argument("name"); p.set_defaults(fn=cmd_remove)
    p = sub.add_parser("rpc"); proj(p); p.add_argument("name")
    p.add_argument("model"); p.add_argument("method"); p.add_argument("args", nargs="?")
    p.add_argument("--kwargs"); p.add_argument("--allow-write", action="store_true"); p.set_defaults(fn=cmd_rpc)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
