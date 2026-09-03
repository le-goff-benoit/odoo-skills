#!/usr/bin/env bash
# Tests d'un module Odoo sur le stack Docker local, dans la série du module.
#
#   odoo-test.sh <module> [options]
#
# Options :
#   --fresh          repart d'une base neuve (drop + create) — recommandé
#   --update         teste aussi la mise à jour (-u) sur la base existante
#   --uninstall      teste la désinstallation à la fin
#   --tags <spec>    passe --test-tags (défaut : /<module>)
#   --tours          n'exécute que les tours (--test-tags /<module>:HttpCase)
#   --keep           ne coupe pas le stack à la fin
#
# Sortie : rapport par étape + extraction des ERROR/WARNING des logs.
# Code retour : 0 seulement si installation, tests et logs sont propres.

set -uo pipefail

STACK="$(cd "$(dirname "${BASH_SOURCE[0]}")/../stack" && pwd)"
# shellcheck source=series-env.sh
. "$(dirname "${BASH_SOURCE[0]}")/series-env.sh"
DB="$ODOO_TEST_DB"
CONF="/etc/odoo/odoo.conf"

MODULE="${1:-}"
if [ -z "$MODULE" ] || [[ "$MODULE" == --* ]]; then
    sed -n '2,18p' "$0" >&2
    exit 2
fi
shift

FRESH=0; UPDATE=0; UNINSTALL=0; KEEP=0
TAGS="/$MODULE"
while [ $# -gt 0 ]; do
    case "$1" in
        --fresh)     FRESH=1 ;;
        --update)    UPDATE=1 ;;
        --uninstall) UNINSTALL=1 ;;
        --keep)      KEEP=1 ;;
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

# Odoo tourne en one-shot (--stop-after-init) : pas besoin du service long.
run_odoo() {
    compose run --rm --no-deps -T odoo odoo "$@" 2>&1 | tee -a "$LOG"
    return "${PIPESTATUS[0]}"
}

echo "Série ${ODOO_SERIES} — image odoo-qa:${ODOO_SERIES} — base ${DB}"

step "0. Démarrage de PostgreSQL"
compose up -d db
compose exec -T db bash -c 'for i in $(seq 1 30); do pg_isready -U odoo -q && exit 0; sleep 1; done; exit 1' \
    || { echo "❌ PostgreSQL indisponible"; exit 1; }

if [ "$FRESH" -eq 1 ]; then
    step "0b. Base neuve : drop + create $DB"
    compose exec -T db dropdb -U odoo --if-exists "$DB"
    compose exec -T db createdb -U odoo "$DB"
fi

step "1. Installation de $MODULE sur $DB"
if run_odoo -c "$CONF" -d "$DB" -i "$MODULE" --stop-after-init --without-demo=all; then
    echo "✅ installation OK"
else
    echo "❌ installation en échec — arrêt"
    STATUS=1
fi

if [ "$STATUS" -eq 0 ] && [ "$UPDATE" -eq 1 ]; then
    step "2. Mise à jour (-u $MODULE)"
    if run_odoo -c "$CONF" -d "$DB" -u "$MODULE" --stop-after-init; then
        echo "✅ mise à jour OK"
    else
        echo "❌ la mise à jour casse — c'est ce qui échouera en production"
        STATUS=1
    fi
fi

if [ "$STATUS" -eq 0 ]; then
    step "3. Tests (--test-tags $TAGS)"
    if run_odoo -c "$CONF" -d "$DB" -u "$MODULE" \
            --test-enable --test-tags "$TAGS" \
            --log-level=test --stop-after-init \
            --screenshots=/mnt/artifacts; then
        echo "✅ tests OK"
    else
        echo "❌ tests en échec"
        STATUS=1
    fi
fi

if [ "$STATUS" -eq 0 ] && [ "$UNINSTALL" -eq 1 ]; then
    step "4. Désinstallation"
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
            && echo "✅ désinstallation OK" \
            || { echo "❌ le module n'est pas passé à l'état 'uninstalled'"; STATUS=1; }
    else
        echo "❌ désinstallation en échec"
        STATUS=1
    fi
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

[ "$KEEP" -eq 1 ] || compose stop db >/dev/null 2>&1

echo
echo "Log complet   : $STACK/$LOG"
echo "Captures      : $STACK/artifacts/"
if [ "$STATUS" -eq 0 ]; then
    echo "✅ $MODULE : installation, tests et logs propres"
else
    echo "❌ $MODULE : voir ci-dessus"
fi
exit "$STATUS"
