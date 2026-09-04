#!/usr/bin/env bash
# Recette complète d'un module à la clôture d'une release : tout ce qui doit être
# vert avant de livrer, enchaîné en une commande, résumé en un tableau.
#
#   odoo-recette.sh <module> [options]
#
# Options :
#   --release <dossier>       dossier de la release : la référence git vient de son `.base`,
#                         le résumé est écrit dans <release>/recette.md
#   --base <ref-git>      référence pour le lint --changed (défaut : .base de la release, sinon HEAD)
#   --db <copie_client>   base restaurée du client : mise à niveau -u dessus, logs contrôlés
#   --no-uninstall        ne teste pas la désinstallation
#   --no-fresh            garde la base de test existante (plus rapide, moins probant)
#   --full-lint           linte tout le module, pas seulement les fichiers modifiés
#
# Protocole, dans l'ordre :
#   1. lint (ruff config Odoo + contrôles Odoo), restreint aux fichiers de la release
#   2. base neuve : installation, mise à jour -u, suite de tests complète du
#      module (tours inclus), désinstallation — via odoo-test.sh
#   3. mise à niveau sur la copie du client si --db : c'est le contrôle qui voit
#      les vues Studio cassées, les données noupdate et les contraintes violées
#   4. résumé : tableau Contrôle / Résultat / Détail, ligne de résultat Odoo
#      (« N failed, N error(s) of N tests »), chemins des logs
#
# Code retour 0 seulement si tout est vert. Le résumé dit ce qui n'a pas été
# exécuté : rien n'est passé sous silence.
#
# Variables : ODOO_SERIES, ODOO_ADDONS_DIR (obligatoire : dossier CONTENANT le module)

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK="$(cd "$HERE/../stack" && pwd)"

MODULE="${1:-}"
if [ -z "$MODULE" ] || [[ "$MODULE" == --* ]]; then sed -n '2,28p' "$0" >&2; exit 2; fi
shift

RELEASE=""; BASE=""; CLIENT_DB=""; UNINSTALL=1; FRESH=1; FULL_LINT=0
while [ $# -gt 0 ]; do
    case "$1" in
        --release)          shift; RELEASE="$(cd "$1" && pwd)" ;;
        --base)         shift; BASE="$1" ;;
        --db)           shift; CLIENT_DB="$1" ;;
        --no-uninstall) UNINSTALL=0 ;;
        --no-fresh)     FRESH=0 ;;
        --full-lint)    FULL_LINT=1 ;;
        *) echo "option inconnue : $1" >&2; exit 2 ;;
    esac
    shift
done

# --- Où est le module ? ------------------------------------------------------
ADDONS="${ODOO_ADDONS_DIR:-}"
if [ -z "$ADDONS" ] && [ -n "$RELEASE" ]; then ADDONS="$(cd "$RELEASE/../.." && pwd)"; fi
if [ -z "$ADDONS" ] || [ ! -f "$ADDONS/$MODULE/__manifest__.py" ]; then
    found="$(find "${ADDONS:-.}" -maxdepth 3 -path "*/$MODULE/__manifest__.py" 2>/dev/null | head -1)"
    [ -n "$found" ] || { echo "module $MODULE introuvable sous ${ADDONS:-.} : régler ODOO_ADDONS_DIR" >&2; exit 2; }
    ADDONS="$(cd "$(dirname "$found")/.." && pwd)"
fi
export ODOO_ADDONS_DIR="$ADDONS"
MODULE_DIR="$ADDONS/$MODULE"

# shellcheck source=series-env.sh
. "$HERE/series-env.sh"
[ -n "$BASE" ] || { [ -n "$RELEASE" ] && [ -f "$RELEASE/.base" ] && BASE="$(cat "$RELEASE/.base")"; }
[ "$BASE" = "sans-git" ] && BASE=""

STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$STACK/artifacts"
SUMMARY="${RELEASE:-$STACK/artifacts}/recette.md"
[ -n "$RELEASE" ] || SUMMARY="$STACK/artifacts/recette-$MODULE-$STAMP.md"

declare -a ROWS=()
row() { ROWS+=("| $1 | $2 | $3 |"); }
STATUS=0
step() { echo; echo "══ $* ═══════════════════════════════════════════════════"; }

VERSION="$(python3 -c "import ast,sys; print(ast.literal_eval(open(sys.argv[1]).read()).get('version','?'))" "$MODULE_DIR/__manifest__.py" 2>/dev/null || echo "?")"
BASE_VERSION="?"
if [ -n "$BASE" ]; then
    rel="$(realpath --relative-to="$(git -C "$ADDONS" rev-parse --show-toplevel)" "$MODULE_DIR/__manifest__.py")"
    BASE_VERSION="$(git -C "$ADDONS" show "$BASE:$rel" 2>/dev/null \
        | python3 -c "import ast,sys; print(ast.literal_eval(sys.stdin.read()).get('version','?'))" 2>/dev/null || echo "?")"
fi

echo "Recette de $MODULE — série $ODOO_SERIES — version $BASE_VERSION → $VERSION"
[ -n "$BASE" ] && echo "Référence git : $BASE"
[ -n "$RELEASE" ] && echo "Release : $RELEASE"

# --- 1. Lint -----------------------------------------------------------------
step "1. Lint"
LINT_LOG="$STACK/artifacts/recette-$MODULE-$STAMP-lint.log"
if [ "$FULL_LINT" -eq 1 ] || [ -z "$BASE" ]; then
    "$HERE/odoo-lint.sh" "$MODULE_DIR" 2>&1 | tee "$LINT_LOG"; rc=${PIPESTATUS[0]}
    scope="module entier"
else
    "$HERE/odoo-lint.sh" --changed "$BASE" "$MODULE_DIR" 2>&1 | tee "$LINT_LOG"; rc=${PIPESTATUS[0]}
    scope="fichiers de la release (--changed ${BASE:0:10})"
fi
LINT_LINE="$(grep -E "^[0-9]+ erreur" "$LINT_LOG" | tail -1)"
case "$rc" in
    0) row "Lint ($scope)" "✅" "${LINT_LINE:-0 erreur}" ;;
    2) row "Lint ($scope)" "⚠️ partiel" "ruff non exécuté — ${LINT_LINE:-}" ; STATUS=1 ;;
    *) row "Lint ($scope)" "❌" "${LINT_LINE:-voir $LINT_LOG}" ; STATUS=1 ;;
esac

# --- 2. Base neuve : install / update / tests / uninstall ---------------------
step "2. Base neuve : installation, mise à jour, tests, désinstallation"
TEST_ARGS=(--update --keep)
[ "$FRESH" -eq 1 ] && TEST_ARGS+=(--fresh)
[ "$UNINSTALL" -eq 1 ] && TEST_ARGS+=(--uninstall)
TEST_OUT="$STACK/artifacts/recette-$MODULE-$STAMP-test.out"
"$HERE/odoo-test.sh" "$MODULE" "${TEST_ARGS[@]}" 2>&1 | tee "$TEST_OUT"
TEST_RC=${PIPESTATUS[0]}
TEST_LOG="$(sed -n 's/^Log complet *: *//p' "$TEST_OUT" | tail -1)"
TEST_DB="$(sed -n 's/^RECETTE .*db=\([^ ]*\).*/\1/p' "$TEST_OUT" | tail -1)"

mark() { grep -q "$1" "$TEST_OUT" && echo "✅" || echo "❌"; }
if grep -q "✅ installation OK" "$TEST_OUT"; then row "Installation base neuve" "✅" "";
else row "Installation base neuve" "❌" "voir $TEST_LOG"; STATUS=1; fi
if grep -q "✅ mise à jour OK" "$TEST_OUT"; then row "Mise à jour (-u)" "✅" "";
elif grep -q "mise à jour" "$TEST_OUT"; then row "Mise à jour (-u)" "❌" "voir $TEST_LOG"; STATUS=1;
else row "Mise à jour (-u)" "— non exécutée" ""; fi
RESULT_LINE="$(grep -h "odoo.tests.result:" "$TEST_LOG" 2>/dev/null | tail -1 | sed 's/.*odoo.tests.result: //; s/ when loading.*//')"
STATS_LINE="$(grep -h "odoo.tests.stats: $MODULE:" "$TEST_LOG" 2>/dev/null | tail -1 | sed "s/.*odoo.tests.stats: $MODULE: //; s/ queries.*/ queries/")"
TOURS="$(grep -c "tour succeeded\|Tour .* succeeded" "$TEST_LOG" 2>/dev/null || true)"
if grep -q "✅ tests OK" "$TEST_OUT"; then
    if echo "$RESULT_LINE" | grep -qE "of 0 tests"; then
        row "Tests Python" "⚠️ aucun test" "le module ne déclare aucun test : à écrire"; STATUS=1
    else
        row "Tests Python (suite complète)" "✅" "${RESULT_LINE:-?}${STATS_LINE:+ — $STATS_LINE}"
    fi
elif grep -q "Tests (" "$TEST_OUT"; then
    row "Tests Python (suite complète)" "❌" "${RESULT_LINE:-voir $TEST_LOG}"; STATUS=1
else
    row "Tests Python" "— non exécutés" "installation en échec"; STATUS=1
fi
if [ "${TOURS:-0}" -gt 0 ]; then row "Tours navigateur (Chrome headless)" "✅" "$TOURS tour(s) succeeded";
elif grep -rqs "start_tour" "$MODULE_DIR/tests" 2>/dev/null; then row "Tours navigateur" "❌" "start_tour présent, aucun « tour succeeded » dans le log"; STATUS=1;
else row "Tours navigateur" "n.a." "aucun tour dans le module"; fi
if [ "$UNINSTALL" -eq 1 ]; then
    if grep -q "✅ désinstallation OK" "$TEST_OUT"; then row "Désinstallation" "✅" "";
    else row "Désinstallation" "❌" "voir $TEST_LOG"; STATUS=1; fi
fi
ERR="$(sed -n 's/^ERROR\/CRITICAL *: *//p' "$TEST_OUT" | tail -1)"
WARN="$(sed -n "s/^WARNING liés à $MODULE *: *//p" "$TEST_OUT" | tail -1)"
if [ "${ERR:-0}" = "0" ]; then row "Logs (ERROR/CRITICAL)" "✅" "0 erreur, ${WARN:-?} warning(s) liés au module";
else row "Logs (ERROR/CRITICAL)" "❌" "${ERR:-?} erreur(s) — voir $TEST_LOG"; STATUS=1; fi
[ "$TEST_RC" -eq 0 ] || STATUS=1

# --- 3. Mise à niveau sur la copie du client ---------------------------------
if [ -n "$CLIENT_DB" ]; then
    step "3. Mise à niveau de $MODULE sur la copie client $CLIENT_DB"
    CLIENT_LOG="$STACK/artifacts/recette-$MODULE-$STAMP-client.log"
    ( cd "$STACK" && docker compose run --rm --no-deps -T odoo \
        odoo -c /etc/odoo/odoo.conf -d "$CLIENT_DB" -u "$MODULE" --stop-after-init --no-http ) \
        > "$CLIENT_LOG" 2>&1
    CRC=$?
    CERR=$(grep -cE "^[0-9-]+ [0-9:,]+ [0-9]+ (ERROR|CRITICAL)" "$CLIENT_LOG" || true)
    CWARN=$(grep -E "^[0-9-]+ [0-9:,]+ [0-9]+ WARNING" "$CLIENT_LOG" | grep -c "$MODULE\|ir.ui.view\|ir_ui_view" || true)
    if [ "$CRC" -eq 0 ] && [ "$CERR" -eq 0 ]; then
        row "Mise à niveau sur copie client \`$CLIENT_DB\`" "✅" "0 ERROR, $CWARN warning(s) vue/module"
    else
        row "Mise à niveau sur copie client \`$CLIENT_DB\`" "❌" "rc=$CRC, $CERR ERROR — voir $CLIENT_LOG"; STATUS=1
    fi
    [ "$CWARN" -gt 0 ] && grep -E "WARNING" "$CLIENT_LOG" | grep "$MODULE\|ir.ui.view\|ir_ui_view" | head -10
else
    row "Mise à niveau sur copie client" "— non exécutée" "aucune copie fournie (--db) : réserve à écrire"
fi

# --- 4. Résumé ----------------------------------------------------------------
step "4. Résumé"
VERSION_NOTE=""
if [ "$BASE_VERSION" != "?" ] && [ "$BASE_VERSION" = "$VERSION" ] && [ -n "$(git -C "$ADDONS" diff --name-only "$BASE" -- "$MODULE_DIR" 2>/dev/null | grep -vE '^\s*$' | grep -v '/tests/' | head -1)" ]; then
    VERSION_NOTE="⚠️ la version du manifest n'a pas bougé depuis l'ouverture de la release ($VERSION) alors que du code a changé"
fi
{
    echo "# Recette — \`$MODULE\` — $(date '+%d.%m.%Y %H:%M')"
    echo
    echo "Série **$ODOO_SERIES** · version \`$BASE_VERSION\` → \`$VERSION\`"
    [ -n "$BASE" ] && echo "· référence git \`${BASE:0:10}\`"
    echo "· base de test \`${TEST_DB:-$ODOO_TEST_DB}\`"
    echo
    echo "| Contrôle | Résultat | Détail |"
    echo "|---|---|---|"
    printf '%s\n' "${ROWS[@]}"
    echo
    [ -n "$VERSION_NOTE" ] && echo "$VERSION_NOTE" && echo
    if [ "${WARN:-0}" != "0" ] && [ -f "${TEST_LOG:-/dev/null}" ]; then
        echo "Avertissements liés au module les plus fréquents (sur $WARN) :"
        echo
        echo '```'
        grep -E "^[0-9-]+ [0-9:,]+ [0-9]+ WARNING" "$TEST_LOG" | grep "$MODULE" \
            | sed -E 's/^[0-9-]+ [0-9:,]+ [0-9]+ WARNING [^ ]+ //' | cut -c1-160 \
            | sort | uniq -c | sort -rn | head -5
        echo '```'
        echo
    fi
    echo "Verdict outillé : $([ "$STATUS" -eq 0 ] && echo "✅ tout est vert" || echo "❌ au moins un contrôle rouge ou non exécuté")"
    echo
    echo "Logs : \`$LINT_LOG\`, \`${TEST_LOG:-?}\`$([ -n "$CLIENT_DB" ] && echo ", \`$CLIENT_LOG\`")"
} > "$SUMMARY"
cat "$SUMMARY"
echo
echo "Résumé écrit : $SUMMARY"
exit "$STATUS"
