#!/usr/bin/env bash
# Tests d'un module Odoo sur le stack Docker local, dans la série du module.
#
#   odoo-test.sh <module> [options]
#
# Options :
#   --fresh          repart d'une base neuve — clonée depuis une base GABARIT par
#                    module (dépendances standard préinstallées, reconstruite quand la
#                    liste des dépendances change) : quelques secondes au lieu de minutes
#   --no-template    --fresh sans gabarit : installation intégrale des dépendances
#   --rebuild-template  reconstruit le gabarit avant de s'en servir
#   --quick          QA de tâche : UN seul passage (-i si la base n'existe pas, sinon -u)
#                    avec les tests ciblés — pas d'étape install/update séparée
#   --update         teste aussi la mise à jour (-u) sur la base existante
#   --uninstall      teste la désinstallation à la fin
#   --tags <spec>    passe --test-tags (défaut : /<module>)
#   --tours          n'exécute que les tours (--test-tags /<module>:HttpCase)
#   --keep           ne coupe pas PostgreSQL à la fin (il n'est de toute façon
#                    jamais coupé s'il tournait déjà avant l'appel)
#
# Base de test : $ODOO_TEST_DB si posée, sinon odoo_qa_<série>_<module>.
#
# Sortie : rapport par étape + extraction des ERROR/WARNING des logs, et une
# ligne finale `RECETTE module=… install=… update=… tests=… uninstall=… errors=…`
# lisible par odoo-recette.sh.
# Code retour : 0 seulement si installation, tests et logs sont propres.

set -uo pipefail

STACK="$(cd "$(dirname "${BASH_SOURCE[0]}")/../stack" && pwd)"
# shellcheck source=series-env.sh
. "$(dirname "${BASH_SOURCE[0]}")/series-env.sh"
CONF="/etc/odoo/odoo.conf"

MODULE="${1:-}"
if [ -z "$MODULE" ] || [[ "$MODULE" == --* ]]; then
    sed -n '2,20p' "$0" >&2
    exit 2
fi
shift

# Base de test : celle de l'utilisateur si ODOO_TEST_DB est posée, sinon une base
# par module. Deux projets de la même série (Claude sur l'un, Codex sur l'autre)
# ne doivent pas se dropper mutuellement leur base avec --fresh.
if [ -n "${ODOO_TEST_DB_EXPLICIT:-}" ]; then
    DB="$ODOO_TEST_DB"
else
    DB="odoo_qa_${ODOO_SERIES_SLUG}_$(printf '%s' "$MODULE" | tr -c 'a-z0-9_\n' '_' | cut -c1-40)"
    export ODOO_TEST_DB="$DB"
fi

FRESH=0; UPDATE=0; UNINSTALL=0; KEEP=0; QUICK=0; TEMPLATE=1; REBUILD_TPL=0
INSTALL_OK=ko; UPDATE_OK=n.a.; UNINSTALL_OK=n.a.
TAGS="/$MODULE"
while [ $# -gt 0 ]; do
    case "$1" in
        --fresh)     FRESH=1 ;;
        --update)    UPDATE=1 ;;
        --uninstall) UNINSTALL=1 ;;
        --keep)      KEEP=1 ;;
        --quick)     QUICK=1 ;;
        --no-template) TEMPLATE=0 ;;
        --rebuild-template) REBUILD_TPL=1 ;;
        --tours)     TAGS="/$MODULE:HttpCase" ;;
        --tags)      shift; TAGS="$1" ;;
        *) echo "option inconnue : $1" >&2; exit 2 ;;
    esac
    shift
done

cd "$STACK"
# Le conteneur tourne sous l'utilisateur `odoo` (uid 101) : sans droits d'écriture,
# Odoo échoue à créer /mnt/artifacts/<db>/screenshots au démarrage de Chrome.
mkdir -p artifacts && chmod 777 artifacts
LOG="artifacts/${MODULE}-$(date +%Y%m%d-%H%M%S).log"
STATUS=0

compose() { docker compose "$@"; }

step() { echo; echo "══ $* ═══════════════════════════════════════════════════"; }
T_STEP=0
tic() { T_STEP=$(date +%s); }
toc() { local d=$(( $(date +%s) - T_STEP )); echo "   ⏱ ${d}s"; DURATIONS="${DURATIONS:+$DURATIONS }$1=${d}s"; }
DURATIONS=""
T_ALL=$(date +%s)
psql_q() { compose exec -T db psql -U odoo -d postgres -Atc "$1"; }
db_exists() { [ "$(psql_q "SELECT 1 FROM pg_database WHERE datname='$1'")" = "1" ]; }

# Odoo tourne en one-shot (--stop-after-init) : pas besoin du service long.
run_odoo() {
    compose run --rm --no-deps -T odoo odoo "$@" 2>&1 | tee -a "$LOG"
    return "${PIPESTATUS[0]}"
}

echo "Série ${ODOO_SERIES} — image odoo-qa:${ODOO_SERIES} — base ${DB}"

step "0. Démarrage de PostgreSQL"
# Si la base tournait déjà (stack utilisé par ailleurs), on ne l'arrêtera pas à la fin.
DB_WAS_UP=0
compose ps --status running db 2>/dev/null | grep -q db && DB_WAS_UP=1
compose up -d db
compose exec -T db bash -c 'for i in $(seq 1 30); do pg_isready -U odoo -q && exit 0; sleep 1; done; exit 1' \
    || { echo "❌ PostgreSQL indisponible"; exit 1; }

# Gabarit : une base par module avec les dépendances STANDARD préinstallées.
# Les dépendances custom (présentes dans ODOO_ADDONS_DIR) n'y sont pas : leur code
# bouge avec la release, elles s'installent avec le module.
TPL="odoo_qa_${ODOO_SERIES_SLUG}_tpl_$(printf '%s' "$MODULE" | tr -c 'a-z0-9_\n' '_' | cut -c1-36)"
tpl_info() {   # → "<hash> <deps standard séparées par des virgules>"
    python3 - "$ODOO_ADDONS_DIR" "$MODULE" "$ODOO_SERIES" <<'PY'
import ast, hashlib, os, sys
addons, module, series = sys.argv[1], sys.argv[2], sys.argv[3]
path = os.path.join(addons, module, "__manifest__.py")
if not os.path.isfile(path):
    for root, dirs, files in os.walk(addons):
        if os.path.basename(root) == module and "__manifest__.py" in files:
            path = os.path.join(root, "__manifest__.py"); break
try:
    deps = ast.literal_eval(open(path).read()).get("depends", [])
except Exception:
    deps = []
def is_custom(d):
    for root, dirs, files in os.walk(addons):
        if os.path.basename(root) == d and "__manifest__.py" in files:
            return True
        dirs[:] = [x for x in dirs if not x.startswith(".") and x not in ("node_modules", "changelog")]
    return False
std = sorted(d for d in deps if d != "base" and not is_custom(d))
print(hashlib.sha1((series + ":" + ",".join(std)).encode()).hexdigest()[:12], ",".join(std))
PY
}

if [ "$FRESH" -eq 1 ]; then
    tic
    read -r TPL_HASH TPL_DEPS < <(tpl_info)
    if [ "$TEMPLATE" -eq 1 ] && [ -n "${TPL_DEPS:-}" ]; then
        CUR_HASH="$(psql_q "SELECT d.description FROM pg_shdescription d JOIN pg_database db ON db.oid=d.objoid WHERE db.datname='$TPL'")"
        if [ "$REBUILD_TPL" -eq 1 ] || [ "$CUR_HASH" != "deps=$TPL_HASH" ]; then
            step "0a. Gabarit $TPL : installation des dépendances standard ($TPL_DEPS)"
            [ -n "$CUR_HASH" ] && echo "   (gabarit périmé : dépendances modifiées)"
            compose exec -T db dropdb -U odoo --if-exists "$TPL"
            compose exec -T db createdb -U odoo "$TPL"
            if run_odoo -c "$CONF" -d "$TPL" -i "$TPL_DEPS" --stop-after-init --without-demo=all; then
                psql_q "COMMENT ON DATABASE \"$TPL\" IS 'deps=$TPL_HASH'" >/dev/null
                echo "✅ gabarit prêt"
            else
                echo "❌ gabarit en échec — repli sur une installation intégrale"
                compose exec -T db dropdb -U odoo --if-exists "$TPL"; TEMPLATE=0
            fi
        else
            echo "Gabarit $TPL à jour (deps=$TPL_HASH)"
        fi
    else
        TEMPLATE=0
    fi
    step "0b. Base neuve : $DB$([ "$TEMPLATE" -eq 1 ] && echo " (clone du gabarit)")"
    psql_q "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname IN ('$DB','$TPL') AND pid <> pg_backend_pid()" >/dev/null
    compose exec -T db dropdb -U odoo --if-exists "$DB"
    if [ "$TEMPLATE" -eq 1 ]; then
        compose exec -T db createdb -U odoo -T "$TPL" "$DB"
        compose exec -T -u root odoo sh -c "rm -rf /var/lib/odoo/filestore/$DB && cp -r /var/lib/odoo/filestore/$TPL /var/lib/odoo/filestore/$DB 2>/dev/null; chown -R odoo:odoo /var/lib/odoo/filestore/$DB 2>/dev/null" || true
    else
        compose exec -T db createdb -U odoo "$DB"
    fi
    toc base
fi

ignored() { grep -q "invalid module names, ignored: .*\b$MODULE\b" "$LOG"; }

if [ "$QUICK" -eq 1 ]; then
    # Un seul chargement : installation si la base n'existe pas, mise à jour sinon,
    # tests ciblés dans le même passage.
    tic
    if db_exists "$DB"; then MODE=-u; step "1. QA de tâche : -u $MODULE + tests ($TAGS) sur $DB"
    else compose exec -T db createdb -U odoo "$DB"; MODE=-i; step "1. QA de tâche : -i $MODULE + tests ($TAGS) sur $DB (base neuve)"; fi
    if run_odoo -c "$CONF" -d "$DB" $MODE "$MODULE" --test-enable --test-tags "$TAGS" \
            --log-level=test --stop-after-init --without-demo=all --screenshots=/mnt/artifacts \
            && ! ignored; then
        echo "✅ $MODE + tests OK"; INSTALL_OK=ok; [ "$MODE" = -u ] && UPDATE_OK=ok
    elif ignored; then
        echo "❌ $MODULE est INTROUVABLE dans le chemin des addons du conteneur (ODOO_ADDONS_DIR=${ODOO_ADDONS_DIR:-?}) ou illisible par l'uid 101"
        STATUS=1
    else
        echo "❌ échec (installation, mise à jour ou tests) — voir les extraits ci-dessous"
        STATUS=1
    fi
    toc quick
else
    step "1. Installation de $MODULE sur $DB"
    tic
    # Odoo IGNORE un module absent du chemin des addons avec un simple WARNING et
    # sort en 0 : « invalid module names, ignored ». Ce faux vert est traité comme
    # un échec, sinon toute la recette valide du vide.
    if run_odoo -c "$CONF" -d "$DB" -i "$MODULE" --stop-after-init --without-demo=all && ! ignored; then
        echo "✅ installation OK"; INSTALL_OK=ok
    elif ignored; then
        echo "❌ $MODULE est INTROUVABLE dans le chemin des addons du conteneur (ODOO_ADDONS_DIR=${ODOO_ADDONS_DIR:-?})"
        echo "   ou illisible par l'utilisateur odoo (uid 101) — arrêt"
        STATUS=1
    else
        echo "❌ installation en échec — arrêt"
        STATUS=1
    fi
    toc install

    if [ "$STATUS" -eq 0 ] && [ "$UPDATE" -eq 1 ]; then
        step "2. Mise à jour (-u $MODULE)"
        tic
        if run_odoo -c "$CONF" -d "$DB" -u "$MODULE" --stop-after-init; then
            echo "✅ mise à jour OK"; UPDATE_OK=ok
        else
            echo "❌ la mise à jour casse — c'est ce qui échouera en production"
            STATUS=1
        fi
        toc update
    fi

    if [ "$STATUS" -eq 0 ]; then
        step "3. Tests (--test-tags $TAGS)"
        tic
        if run_odoo -c "$CONF" -d "$DB" -u "$MODULE" \
                --test-enable --test-tags "$TAGS" \
                --log-level=test --stop-after-init \
                --screenshots=/mnt/artifacts; then
            echo "✅ tests OK"
        else
            echo "❌ tests en échec"
            STATUS=1
        fi
        toc tests
    fi
fi

if [ "$STATUS" -eq 0 ] && [ "$UNINSTALL" -eq 1 ]; then
    step "4. Désinstallation"
    tic
    if compose run --rm --no-deps -T -e MOD="$MODULE" odoo \
            odoo shell -c "$CONF" -d "$DB" --no-http <<'PY' 2>&1 | tee -a "$LOG"
import os
module = env['ir.module.module'].search([('name', '=', os.environ['MOD'])])
module.button_immediate_uninstall()
env.cr.commit()
print('ETAT_APRES_DESINSTALLATION:', module.state)
PY
    then
        grep -q "ETAT_APRES_DESINSTALLATION: uninstalled" "$LOG" \
            && { echo "✅ désinstallation OK"; UNINSTALL_OK=ok; } \
            || { echo "❌ le module n'est pas passé à l'état 'uninstalled'"; STATUS=1; }
    else
        echo "❌ désinstallation en échec"
        STATUS=1
    fi
    toc uninstall
fi

step "5. Analyse des logs"
ERRORS=$(grep -cE "^[0-9-]+ [0-9:,]+ [0-9]+ (ERROR|CRITICAL)" "$LOG" || true)
FAILED=$(grep -cE "FAIL:|ERROR:.*test" "$LOG" || true)
WARNS=$(grep -E "^[0-9-]+ [0-9:,]+ [0-9]+ WARNING" "$LOG" | grep -c "$MODULE" || true)
SKIPPED=$(grep -c "skipped Test" "$LOG" || true)

echo "ERROR/CRITICAL : $ERRORS"
echo "tests échoués  : $FAILED"
echo "tests ignorés  : $SKIPPED"
echo "WARNING liés à $MODULE : $WARNS"

# Un test ignoré faute de dépendance (websocket-client, chromium) est un faux vert :
# on le traite comme un échec, sinon les tours passent inaperçus.
if [ "$SKIPPED" -gt 0 ]; then
    echo
    echo "── tests ignorés ──"
    grep "skipped Test" "$LOG" | sed 's/^.*skipped /  /' | head -20
    if grep -qE "skipped Test.*(not installed|not found|Chrome)" "$LOG"; then
        echo "  ⚠️  ignorés faute de dépendance dans l'image : reconstruire avec"
        echo "     odoo-stack.sh build"
        STATUS=1
    fi
fi

if [ "$ERRORS" -gt 0 ] || [ "$FAILED" -gt 0 ]; then
    echo
    echo "── extraits ──"
    grep -nE "^[0-9-]+ [0-9:,]+ [0-9]+ (ERROR|CRITICAL)|FAIL:" "$LOG" | head -40
    STATUS=1
fi
if [ "$WARNS" -gt 0 ]; then
    echo
    echo "── avertissements liés au module (à traiter) ──"
    grep -E "^[0-9-]+ [0-9:,]+ [0-9]+ WARNING" "$LOG" | grep "$MODULE" | head -20
fi

if [ "$KEEP" -eq 0 ] && [ "$DB_WAS_UP" -eq 0 ]; then compose stop db >/dev/null 2>&1; fi

RESULT_LINE="$(grep -h "odoo.tests.result:" "$LOG" 2>/dev/null | tail -1 | sed 's/.*odoo.tests.result: //; s/ when loading.*//')"
echo "RECETTE module=$MODULE db=$DB install=$INSTALL_OK update=$UPDATE_OK uninstall=$UNINSTALL_OK tests=\"${RESULT_LINE:-non exécutés}\" errors=$ERRORS failed=$FAILED skipped=$SKIPPED warnings=$WARNS total=$(( $(date +%s) - T_ALL ))s ${DURATIONS}"

echo
echo "Log complet   : $STACK/$LOG"
echo "Captures      : $STACK/artifacts/"
if [ "$STATUS" -eq 0 ]; then
    echo "✅ $MODULE : installation, tests et logs propres"
else
    echo "❌ $MODULE : voir ci-dessus"
fi
exit "$STATUS"
