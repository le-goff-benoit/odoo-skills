#!/usr/bin/env bash
# Remonte une sauvegarde Odoo dans le stack QA, neutralisée et prête à l'emploi.
#
#   odoo-restore.sh <sauvegarde> [options]
#
# Formats acceptés :
#   .zip   dump.sql + filestore/ (+ manifest.json)   ← Odoo.sh, /web/database/manager
#   .zip   dump (format custom pg_dump), sans filestore
#   .sql   pg_dump plain
#   .dump  pg_dump custom (« dump sans filestore » d'Odoo.sh)
#
# Options :
#   --db <nom>              nom de la base locale (défaut : déduit du nom du fichier)
#   --series <série>        force la série (sinon manifest.json, puis ligne `base` du dump,
#                           puis $ODOO_SERIES, puis le module de $ODOO_ADDONS_DIR)
#   --force                 écrase une base locale du même nom
#   --no-filestore          n'importe pas le filestore (documents, images, PDF)
#   --update <modules>      met à jour ces modules après restauration (ex. « mon_module »)
#
# Ce que fait le script, dans l'ordre :
#   1. déduit la série et démarre le stack de cette série (image odoo-qa:<série>)
#   2. crée la base et importe le dump
#   3. dépose le filestore dans le volume du conteneur odoo
#   4. neutralise : `odoo neutralize` (mails, crons, paiements, webhooks + bandeau),
#      web.base.url → le stack local, bundles d'assets purgés
#   5. réactive `admin` (id 2) avec le mot de passe `admin`
#   6. liste les modules installés introuvables dans le chemin des addons
#
# La base restaurée s'utilise ensuite avec `--db <nom>` dans odoo-shot.sh,
# odoo-pdf.sh, odoo-test.sh, ou en exportant ODOO_TEST_DB=<nom>.
#
# Variables : ODOO_SERIES, ODOO_ADDONS_DIR, ODOO_HTTP_PORT (voir stack/.env.example)

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK="$(cd "$HERE/../stack" && pwd)"

usage() { sed -n '2,33p' "$0" >&2; exit 2; }

BACKUP="${1:-}"
[ -n "$BACKUP" ] && [[ "$BACKUP" != --* ]] || usage
shift
[ -f "$BACKUP" ] || { echo "Sauvegarde introuvable : $BACKUP" >&2; exit 1; }
BACKUP="$(cd "$(dirname "$BACKUP")" && pwd)/$(basename "$BACKUP")"

DB=""; SERIES="${ODOO_SERIES:-}"; FORCE=""; NO_FILESTORE=""; UPDATE=""
while [ $# -gt 0 ]; do
    case "$1" in
        --db)            shift; DB="$1" ;;
        --series)        shift; SERIES="$1" ;;
        --force)         FORCE=1 ;;
        --no-filestore)  NO_FILESTORE=1 ;;
        --update)        shift; UPDATE="$1" ;;
        -h|--help)       usage ;;
        *) echo "option inconnue : $1" >&2; usage ;;
    esac
    shift
done

# --- Format -----------------------------------------------------------------
FORMAT=""   # zip-sql | zip-custom | sql | custom
ZIP_NAMES=""
zip_has() { printf '%s\n' "$ZIP_NAMES" | grep -q "$1"; }
case "$BACKUP" in
    *.zip)
        ZIP_NAMES="$(unzip -Z1 "$BACKUP")"
        if zip_has '^dump\.sql$'; then FORMAT="zip-sql"
        elif zip_has '^dump$'; then FORMAT="zip-custom"
        else echo "Archive sans dump.sql ni dump à la racine (dossier parent non toléré)." >&2; exit 1
        fi ;;
    *.sql)  FORMAT="sql" ;;
    *.dump) FORMAT="custom" ;;
    *) echo "Extension inconnue (.zip, .sql ou .dump attendus) : $BACKUP" >&2; exit 1 ;;
esac

# --- Nom de base par défaut : <nom-du-fichier> assaini ----------------------
if [ -z "$DB" ]; then
    DB="$(basename "$BACKUP")"; DB="${DB%.*}"
    DB="$(echo "$DB" | tr 'A-Z' 'a-z' | sed 's/[^a-z0-9_]/_/g; s/__*/_/g; s/^_//; s/_$//')"
fi

# --- Série ------------------------------------------------------------------
series_from_version() {   # "saas~19.4.1.2.0" → "19.4" ; "18.0.1.0.0" → "18.0"
    sed -E 's/^saas~//; s/^([0-9]+\.[0-9]+).*/\1/'
}
if [ -z "$SERIES" ]; then
    case "$FORMAT" in
        zip-sql|zip-custom)
            if zip_has '^manifest\.json$'; then
                SERIES="$(unzip -p "$BACKUP" manifest.json \
                    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("version",""))' \
                    | series_from_version)"
            fi ;;
    esac
fi
if [ -z "$SERIES" ] && { [ "$FORMAT" = "zip-sql" ] || [ "$FORMAT" = "sql" ]; }; then
    # Ligne du module `base` dans la COPY de ir_module_module : la 1re version
    # à 5 composantes est la sienne.
    if [ "$FORMAT" = "zip-sql" ]; then reader=(unzip -p "$BACKUP" dump.sql); else reader=(cat "$BACKUP"); fi
    SERIES="$("${reader[@]}" | grep -m1 -P '^\d+\tbase\t' \
        | grep -oP '(saas~)?\d+\.\d+\.\d+\.\d+\.\d+' | head -1 | series_from_version || true)"
fi
if [ -z "$SERIES" ] && [ -n "${ODOO_ADDONS_DIR:-}" ] && [ -d "$ODOO_ADDONS_DIR" ]; then
    SERIES="$(python3 "$HERE/odoo_series.py" "$ODOO_ADDONS_DIR" 2>/dev/null | sed -n 's/^ODOO_SERIES=//p')"
fi
[ -n "$SERIES" ] || { echo "Série indéterminable : passer --series <série>." >&2; exit 1; }

export ODOO_SERIES="$SERIES"
# shellcheck source=series-env.sh
. "$HERE/series-env.sh"
HTTP_PORT="${ODOO_HTTP_PORT:-8079}"
CONF="/etc/odoo/odoo.conf"

echo "ODOO_SERIES=$SERIES"
echo "Sauvegarde : $BACKUP ($FORMAT)"
echo "Base cible : $DB  →  http://localhost:$HTTP_PORT  (admin/admin)"

cd "$STACK"
compose() { docker compose "$@"; }
psql_db()  { compose exec -T db psql -U odoo -v ON_ERROR_STOP=1 -q "$@"; }

if ! docker image inspect "odoo-qa:$SERIES" >/dev/null 2>&1; then
    echo "Image odoo-qa:$SERIES absente — construction (une fois par série)…"
    compose build odoo
fi
compose up -d
for _ in $(seq 1 60); do
    compose exec -T db pg_isready -U odoo >/dev/null 2>&1 && break
    sleep 1
done

# --- Base -------------------------------------------------------------------
if psql_db -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname='$DB'" | grep -qx 1; then
    if [ -n "$FORCE" ]; then
        echo "Base $DB existante — suppression (--force)."
        psql_db -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$DB' AND pid <> pg_backend_pid()" >/dev/null
        psql_db -d postgres -c "DROP DATABASE \"$DB\""
        compose exec -T -u root odoo rm -rf "/var/lib/odoo/filestore/$DB"
    else
        echo "La base $DB existe déjà. Relancer avec --force pour l'écraser, ou --db <autre_nom>." >&2
        exit 1
    fi
fi
psql_db -d postgres -c "CREATE DATABASE \"$DB\" ENCODING 'UTF8' TEMPLATE template0"

echo "Import du dump…"
case "$FORMAT" in
    zip-sql)    unzip -p "$BACKUP" dump.sql | psql_db -d "$DB" -o /dev/null ;;
    sql)        psql_db -d "$DB" -o /dev/null < "$BACKUP" ;;
    zip-custom) unzip -p "$BACKUP" dump | compose exec -T db pg_restore -U odoo -d "$DB" --no-owner --no-privileges ;;
    custom)     compose exec -T db pg_restore -U odoo -d "$DB" --no-owner --no-privileges < "$BACKUP" ;;
esac

# --- Filestore --------------------------------------------------------------
if [ -z "$NO_FILESTORE" ] && [ "$FORMAT" = "zip-sql" ] \
        && zip_has '^filestore/'; then
    echo "Dépôt du filestore…"
    TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
    unzip -q "$BACKUP" 'filestore/*' -d "$TMP"
    tar -C "$TMP/filestore" -cf - . | compose exec -T -u root odoo sh -c \
        "mkdir -p /var/lib/odoo/filestore/$DB && tar -xf - -C /var/lib/odoo/filestore/$DB \
         && chown -R odoo:odoo /var/lib/odoo/filestore/$DB && chmod -R u+rwX /var/lib/odoo/filestore/$DB"
else
    compose exec -T -u root odoo sh -c "mkdir -p /var/lib/odoo/filestore/$DB && chown odoo:odoo /var/lib/odoo/filestore/$DB"
    [ -n "$NO_FILESTORE" ] || echo "Pas de filestore dans la sauvegarde : les pièces jointes seront absentes."
fi

# --- Neutralisation ---------------------------------------------------------
echo "Neutralisation (odoo neutralize)…"
compose exec -T odoo odoo neutralize -c "$CONF" -d "$DB" >/dev/null

echo "Réglages locaux (admin/admin, web.base.url, assets)…"
compose exec -T -e RESTORE_PORT="$HTTP_PORT" odoo odoo shell -c "$CONF" -d "$DB" --no-http <<'PY' 2>&1 \
    | grep -vE '^\s*$|^[0-9]{4}-[0-9]{2}-[0-9]{2} ' | sed 's/^/  /' || true
import os
import odoo
admin = env['res.users'].browse(2).with_context(active_test=False)
admin.write({'active': True, 'password': 'admin'})
icp = env['ir.config_parameter'].sudo()
icp.set_param('web.base.url', 'http://localhost:%s' % os.environ['RESTORE_PORT'])
icp.set_param('web.base.url.freeze', 'True')
env['ir.attachment'].sudo().search([('url', '=like', '/web/assets/%')]).unlink()
paths = list(odoo.addons.__path__)
PSEUDO = {'studio_customization'}   # module virtuel de Studio, jamais sur disque
installed = env['ir.module.module'].search([('state', 'in', ('installed', 'to upgrade', 'to install'))])
missing = sorted(m.name for m in installed if m.name not in PSEUDO
                 and not any(os.path.isdir(os.path.join(p, m.name)) for p in paths))
env.cr.commit()
print('Modules installés : %d' % len(installed))
if missing:
    print('ABSENTS du chemin des addons (%d) : %s' % (len(missing), ', '.join(missing)))
    print("→ régler ODOO_ADDONS_DIR sur le dossier qui contient les modules custom de ce client.")
PY

if [ -n "$UPDATE" ]; then
    echo "Mise à jour de : $UPDATE…"
    compose exec -T odoo odoo -c "$CONF" -d "$DB" -u "$UPDATE" --stop-after-init --no-http 2>&1 \
        | grep -E "ERROR|CRITICAL|Modules loaded" | sed 's/^/  /' || true
fi

echo
echo "Base $DB prête : http://localhost:$HTTP_PORT/web?db=$DB  (admin / admin)"
echo "Pour la viser par défaut : export ODOO_TEST_DB=$DB"
