#!/usr/bin/env python3
"""Pack de configuration Odoo : exporter, appliquer, comparer des personnalisations
« Studio » (champs, modèles, automatisations, actions serveur, vues, menus, droits…)
entre une base et un fichier JSON versionnable — sans module.

Tout repose sur l'identifiant externe (`ir.model.data`, `module.name`) : un
enregistrement du pack se retrouve par son XML-ID, se crée s'il manque, se met à
jour sinon. Appliquer deux fois donne le même résultat (idempotent). Les
références (many2one, many2many) sont écrites `{"ref": "module.name"}` et
résolues à l'application : un pack ne contient jamais d'identifiant numérique.

    odoo_pack.py export --db <base> [--module studio_customization|__export__|cfg_<projet>] --out pack.json
    odoo_pack.py apply  pack.json --db <base>            # copie locale ou stack (admin/admin)
    odoo_pack.py apply  pack.json --instance <projet> <nom> [--allow-write]   # staging / production
    odoo_pack.py diff   pack.json --db <base>            # ce que l'application changerait
    odoo_pack.py xmlid  --db <base> <modèle> <id> <module.name>   # nommer un enregistrement existant

Cible locale : `--db <base>` sur `http://localhost:$ODOO_HTTP_PORT` (défaut 8079),
`admin`/`admin` — ou `--url`, `--login`, `--password`. Cible distante :
`--instance` lit `~/.odoo-agents/instances/<projet>.json` ; une production
refuse toute écriture sans `--allow-write` ET `ODOO_PRODUCTION_CONFIRMED=<nom>`
(règles d'`odoo_instance.py`).

Modèles pris en charge, dans l'ordre de dépendance (un autre modèle passe en fin) :
ir.model, ir.model.fields, res.groups, ir.model.access, ir.rule, ir.ui.view,
ir.actions.server, base.automation, ir.cron, ir.actions.act_window, ir.ui.menu,
ir.actions.report, mail.template, ir.filters, ir.default.
"""

from __future__ import annotations

import json
import os
import sys
import xmlrpc.client
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

UNRESOLVED = object()   # référence sans XML-ID dans le pack : champ ignoré à l'application
ORDER = ["ir.model", "ir.model.fields", "res.groups", "ir.model.access", "ir.rule",
         "ir.ui.view", "ir.actions.server", "base.automation", "ir.cron",
         "ir.actions.act_window", "ir.ui.menu", "ir.actions.report", "mail.template",
         "ir.filters", "ir.default"]
SKIP_FIELDS = {"id", "create_uid", "create_date", "write_uid", "write_date", "__last_update", "parent_path",
               "display_name", "xml_id", "complete_name", "message_ids", "message_follower_ids",
               "activity_ids", "website_message_ids", "rating_ids", "message_partner_ids"}
# Champs qui ne sont pas de la configuration mais de l'état de fonctionnement.
SKIP_BY_MODEL = {
    "ir.cron": {"lastcall", "nextcall", "prev_call", "failure_count", "first_failure_date"},
    "base.automation": {"last_run", "least_delay_msg"},
    "ir.model": {"field_id", "access_ids", "rule_ids", "view_ids", "count", "transient", "abstract",
                 "inherited_model_ids", "modules", "state"},
    "ir.model.fields": {"model", "state", "modules", "selection", "field_description_translated"},
    "ir.ui.view": {"arch", "arch_base", "arch_fs", "arch_prev", "arch_updated", "model_data_id",
                   "xml_id", "inherit_children_ids"},
    "ir.actions.server": {"child_ids"},
    "res.groups": {"user_ids", "users", "all_user_ids", "full_name", "model_access", "rule_groups",
                   "view_access", "menu_access"},
}


class Target:
    """Une base Odoo jointe par XML-RPC : locale (stack) ou instance déclarée."""

    def __init__(self, url: str, db: str, login: str, secret: str, guard=None, label: str = ""):
        self.url, self.db, self.login, self.secret = url.rstrip("/"), db, login, secret
        self.guard = guard          # Instance d'odoo_instance (règles de production) ou None
        self.label = label or f"{url} / {db}"
        self._uid = None

    @classmethod
    def local(cls, db: str, url: str | None, login: str, password: str) -> "Target":
        port = os.environ.get("ODOO_HTTP_PORT", "8079")
        return cls(url or f"http://localhost:{port}", db, login, password)

    @classmethod
    def instance(cls, project: str, name: str) -> "Target":
        import odoo_instance  # noqa: PLC0415
        inst = odoo_instance.Instance.load(project, name)
        return cls(inst.url, inst.db, inst.login, inst.secret, guard=inst, label=f"{project} / {name}")

    def uid(self) -> int:
        if self._uid is None:
            self._uid = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common", allow_none=True) \
                .authenticate(self.db, self.login, self.secret, {})
            if not self._uid:
                raise SystemExit(f"authentification refusée sur {self.label}")
        return self._uid

    def call(self, model: str, method: str, *args, allow_write: bool = False, **kwargs):
        if self.guard is not None:
            return self.guard.execute(model, method, *args, allow_write=allow_write, **kwargs)
        proxy = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object", allow_none=True)
        return proxy.execute_kw(self.db, self.uid(), self.secret, model, method, list(args), kwargs)

    # -- identifiants externes ------------------------------------------------
    def xmlid_of(self, model: str, res_id: int) -> str | None:
        rows = self.call("ir.model.data", "search_read",
                         [("model", "=", model), ("res_id", "=", res_id)],
                         fields=["module", "name"], limit=1, order="id")
        return f"{rows[0]['module']}.{rows[0]['name']}" if rows else None

    def id_of(self, xmlid: str) -> int | None:
        module, _, name = xmlid.partition(".")
        rows = self.call("ir.model.data", "search_read",
                         [("module", "=", module), ("name", "=", name)], fields=["res_id"], limit=1)
        return rows[0]["res_id"] if rows else None

    def name_record(self, model: str, res_id: int, xmlid: str, allow_write: bool) -> None:
        module, _, name = xmlid.partition(".")
        self.call("ir.model.data", "create",
                  {"module": module, "name": name, "model": model, "res_id": res_id, "noupdate": True},
                  allow_write=allow_write)


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #

def exportable_fields(target: Target, model: str) -> dict:
    meta = target.call(model, "fields_get", attributes=["type", "store", "readonly", "relation", "related",
                                                         "depends", "required", "string"])
    skip = SKIP_FIELDS | SKIP_BY_MODEL.get(model, set())
    out = {}
    for name, f in meta.items():
        if name in skip or not f.get("store") or f.get("related"):
            continue
        if f.get("type") == "one2many":
            continue
        if f.get("readonly") and not f.get("required"):
            continue
        out[name] = f
    return out


def export(target: Target, module: str, out: Path) -> int:
    entries = target.call("ir.model.data", "search_read", [("module", "=", module)],
                          fields=["model", "res_id", "name", "noupdate"], order="id")
    if not entries:
        print(f"aucun enregistrement dans le module d'identifiants « {module} » sur {target.label}")
        return 1
    by_model: dict[str, list] = {}
    for e in entries:
        by_model.setdefault(e["model"], []).append(e)
    models = [m for m in ORDER if m in by_model] + sorted(m for m in by_model if m not in ORDER)
    records, warnings = [], []
    for model in models:
        fields = exportable_fields(target, model)
        ids = [e["res_id"] for e in by_model[model]]
        rows = {r["id"]: r for r in target.call(model, "read", ids, fields=list(fields))}
        for e in by_model[model]:
            row = rows.get(e["res_id"])
            if row is None:
                warnings.append(f"{model} {module}.{e['name']} : enregistrement absent (id {e['res_id']})")
                continue
            values = {}
            for name, f in fields.items():
                val = row.get(name)
                if f["type"] == "many2one":
                    if not val:
                        values[name] = False
                        continue
                    rid = val[0] if isinstance(val, (list, tuple)) else val
                    ref = target.xmlid_of(f["relation"], rid)
                    if ref:
                        values[name] = {"ref": ref}
                    else:
                        values[name] = {"unresolved": f["relation"], "id": rid,
                                        "display": val[1] if isinstance(val, (list, tuple)) else ""}
                        warnings.append(f"{model} {module}.{e['name']}.{name} → {f['relation']}#{rid} "
                                        f"sans XML-ID (« {values[name]['display']} ») : le nommer avec "
                                        f"`odoo_pack.py xmlid` ou l'exclure")
                elif f["type"] == "many2many":
                    refs = []
                    for rid in val or []:
                        ref = target.xmlid_of(f["relation"], rid)
                        if ref:
                            refs.append({"ref": ref})
                        else:
                            refs.append({"unresolved": f["relation"], "id": rid})
                            warnings.append(f"{model} {module}.{e['name']}.{name} → {f['relation']}#{rid} sans XML-ID")
                    values[name] = refs
                else:
                    values[name] = val
            records.append({"model": model, "xml_id": f"{module}.{e['name']}",
                            "noupdate": bool(e["noupdate"]), "values": values})
    pack = {"format": "odoo-pack/1", "source": target.label, "module": module,
            "series": target.call("ir.module.module", "search_read", [("name", "=", "base")],
                                  fields=["latest_version"])[0]["latest_version"],
            "records": records}
    out.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(records)} enregistrement(s) de {len(models)} modèle(s) → {out}")
    for w in warnings:
        print("  ⚠️ " + w)
    return 0


# --------------------------------------------------------------------------- #
# Apply / diff
# --------------------------------------------------------------------------- #

def resolve(target: Target, value, cache: dict):
    if isinstance(value, dict):
        if "ref" in value:
            ref = value["ref"]
            if ref not in cache:
                rid = target.id_of(ref)
                if rid is None:
                    raise SystemExit(f"référence introuvable sur la cible : {ref}")
                cache[ref] = rid
            return cache[ref]
        if "unresolved" in value:
            return UNRESOLVED
    return value


def normalize(current, field_type: str):
    """Valeur lue sur la cible, mise sous la forme comparable au pack (après résolution)."""
    if field_type == "many2one":
        return current[0] if isinstance(current, (list, tuple)) else (current or False)
    if field_type == "many2many":
        return sorted(current or [])
    return current


def apply(target: Target, pack: dict, dry_run: bool, allow_write: bool) -> int:
    cache: dict = {}
    created = updated = unchanged = 0
    for rec in pack["records"]:
        model, xmlid = rec["model"], rec["xml_id"]
        cache.setdefault(xmlid, target.id_of(xmlid))
        rid = cache[xmlid]
        meta = target.call(model, "fields_get", attributes=["type"])
        vals, m2m = {}, {}
        for name, value in rec["values"].items():
            if name not in meta:
                print(f"  ⚠️ {xmlid}.{name} inconnu sur la cible (série différente ?) — ignoré")
                continue
            if meta[name]["type"] == "many2many":
                ids = [resolve(target, v, cache) for v in (value or [])]
                if UNRESOLVED in ids:
                    print(f"  ⚠️ {xmlid}.{name} : référence sans XML-ID dans le pack — champ ignoré")
                    continue
                m2m[name] = sorted(ids)
                vals[name] = [(6, 0, ids)]
                continue
            resolved = resolve(target, value, cache)
            if resolved is UNRESOLVED:
                print(f"  ⚠️ {xmlid}.{name} : référence sans XML-ID dans le pack — champ ignoré")
                continue
            vals[name] = resolved
        if rid is None:
            print(f"  + {model} {xmlid}")
            if not dry_run:
                rid = target.call(model, "create", vals, allow_write=allow_write)
                if isinstance(rid, list):   # create([vals]) renvoie une liste selon la série
                    rid = rid[0]
                target.name_record(model, rid, xmlid, allow_write)
                cache[xmlid] = rid
            created += 1
            continue
        current = target.call(model, "read", [rid], fields=list(vals))[0]
        changes = {}
        for name, value in vals.items():
            cur = normalize(current.get(name), meta[name]["type"])
            new = m2m[name] if name in m2m else value
            if cur != new and not (cur in (False, "", None) and new in (False, "", None)):
                changes[name] = (cur, new)
        if not changes:
            unchanged += 1
            continue
        print(f"  ~ {model} {xmlid} : " + ", ".join(
            f"{k} ({str(a)[:40]!r} → {str(b)[:40]!r})" for k, (a, b) in changes.items()))
        if not dry_run:
            target.call(model, "write", [rid], {k: vals[k] for k in changes}, allow_write=allow_write)
        updated += 1
    verb = "à créer / à modifier / inchangés" if dry_run else "créés / modifiés / inchangés"
    print(f"{created} / {updated} / {unchanged} {verb} sur {target.label}")
    return 0


# --------------------------------------------------------------------------- #

def main(argv: list[str]) -> int:
    args = argv[1:]
    if not args or args[0] not in ("export", "apply", "diff", "xmlid"):
        print(__doc__)
        return 2
    cmd = args.pop(0)

    def take(flag, n=1):
        if flag in args:
            i = args.index(flag); vals = args[i + 1:i + 1 + n]; del args[i:i + 1 + n]
            return vals if n > 1 else vals[0]
        return None

    db = take("--db"); url = take("--url"); login = take("--login") or "admin"
    password = take("--password") or "admin"; instance = take("--instance", 2)
    module = take("--module") or "studio_customization"; out = take("--out")
    allow_write = "--allow-write" in args
    if allow_write:
        args.remove("--allow-write")

    if instance:
        target = Target.instance(*instance)
    elif db:
        target = Target.local(db, url, login, password)
    else:
        print("cible manquante : --db <base> ou --instance <projet> <nom>", file=sys.stderr)
        return 2

    if cmd == "export":
        return export(target, module, Path(out or f"pack_{module}.json"))
    if cmd == "xmlid":
        model, res_id, xmlid = args[0], int(args[1]), args[2]
        target.name_record(model, res_id, xmlid, allow_write)
        print(f"{model}#{res_id} nommé {xmlid} sur {target.label}")
        return 0
    pack = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    if pack.get("format") != "odoo-pack/1":
        raise SystemExit("format de pack inconnu")
    if cmd == "diff":
        print(f"Comparaison de {args[0]} avec {target.label} (aucune écriture) :")
        return apply(target, pack, dry_run=True, allow_write=False)
    print(f"Application de {args[0]} sur {target.label} :")
    return apply(target, pack, dry_run=False, allow_write=allow_write)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
