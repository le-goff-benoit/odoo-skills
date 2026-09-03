#!/usr/bin/env bash
# Lint « syntaxe pure » d'un module Odoo, calé sur la série cible du module.
#
#   odoo-lint.sh [--series X] [--changed [<ref-git>]] <chemin_du_module> [...]
#
# --series : force la série (18.0, 19.0, 19.4…). Par défaut elle est déduite du
#   module lui-même (`.odoo-agents/config`, puis le préfixe de `version` du
#   manifest). Linter un module 18.0 avec les règles de la 19.0 fabrique de
#   fausses erreurs : `_sql_constraints` y est la forme correcte.
#
# --changed : ne remonte que les anomalies portées par les fichiers modifiés
#   (diff vs <ref-git>, défaut HEAD, plus les fichiers non suivis). Les contrôles
#   tournent toujours sur tout le module ; seul l'affichage est restreint.
#   C'est la façon de traiter un module historique sans se noyer dans la dette.
#
# Enchaîne :
#   1. ruff, avec la configuration OFFICIELLE d'Odoo (odoo-sources/<série>/ruff.toml,
#      repli sur la plus proche disponible : seule la 19.0 en publie une)
#      — passe BLOQUANTE : règles réellement respectées par le code d'Odoo
#      — passe CONSEIL   : configuration complète, informative
#   2. odoo_lint.py : manifest, XML, sécurité, tests, motifs datés par série
#
# ruff est cherché dans cet ordre : binaire hôte -> module python hôte -> image
# Docker odoo-qa de la série (qui l'embarque). Si aucun n'est disponible, l'étape est
# signalée comme non exécutée — jamais silencieusement passée.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Règles présentes dans le ruff.toml d'Odoo mais que le code d'Odoo lui-même viole
# massivement — donc non bloquantes pour un module custom.
#   - COM812, I001, RUF021, RET, E741 : listées comme « pas encore activées sur
#     runbot » dans l'en-tête du ruff.toml officiel.
#   - PLW0642 : `order = order.with_company(...)` est un idiome Odoo courant.
#   - E265 / E261 / E262 : les marqueurs de section `#=== FIELDS ===#` du style Odoo.
# Mesuré sur addons/{sale,account,project,hr,stock}/models de la 19.0 :
# 543 COM812, 82 I001, 73 RUF021, ~180 RET, 58 E741, 44 PLW0642, 55 E26x.
NOT_ENFORCED="lint.extend-ignore = ['COM812','I001','RUF021','RET','E741','PLW0642','E265','E261','E262']"

STATUS=0

SERIES_ARG=()
if [ "${1:-}" = "--series" ]; then
    SERIES_ARG=(--series "$2"); shift 2
fi

CHANGED=0
CHANGED_REF="HEAD"
if [ "${1:-}" = "--changed" ]; then
    CHANGED=1
    shift
    if [ $# -gt 0 ] && [[ "$1" != -* ]] && [ ! -e "$1" ]; then
        CHANGED_REF="$1"; shift
    fi
fi

if [ $# -eq 0 ]; then
    echo "usage: $(basename "$0") [--series X] [--changed [<ref-git>]] <chemin> [...]" >&2
    exit 2
fi

# Série cible et configuration ruff associée, déduites du premier module visé.
eval "$(python3 "$HERE/odoo_series.py" "$1" "${SERIES_ARG[@]}" 2>/dev/null \
        | sed 's/^/LINT_/')"
SERIES="${LINT_ODOO_SERIES:-19.0}"
RUFF_CONFIG="${LINT_ODOO_RUFF_CONFIG:-${ODOO_SOURCES_DIR:-$HOME/odoo-sources}/19.0/ruff.toml}"
# Image QA de la série, avec repli sur l'ancien tag mono-version : ruff n'y sert
# qu'au style Python pur, n'importe laquelle des deux fait l'affaire.
QA_IMAGE="odoo-qa:${SERIES}"
if command -v docker >/dev/null 2>&1 \
        && ! docker image inspect "$QA_IMAGE" >/dev/null 2>&1 \
        && docker image inspect odoo19-qa:latest >/dev/null 2>&1; then
    QA_IMAGE="odoo19-qa:latest"
fi
echo "Série cible : $SERIES  (${LINT_ODOO_ORIGIN:-défaut})"

# Liste des fichiers modifiés, restreinte aux modules ciblés.
FILES=()
if [ "$CHANGED" -eq 1 ]; then
    for target in "$@"; do
        abs="$(cd "$target" && pwd)"
        repo="$(git -C "$abs" rev-parse --show-toplevel 2>/dev/null)" || {
            echo "--changed : $abs n'est pas dans un dépôt git" >&2; exit 2; }
        while IFS= read -r rel; do
            [ -n "$rel" ] || continue
            f="$repo/$rel"
            [ -f "$f" ] || continue
            case "$f" in "$abs"/*) FILES+=("$f") ;; esac
        done < <(
            git -C "$repo" diff --name-only "$CHANGED_REF" 2>/dev/null
            git -C "$repo" ls-files --others --exclude-standard 2>/dev/null
        )
    done
    if [ "${#FILES[@]}" -eq 0 ]; then
        echo "Aucun fichier modifié depuis $CHANGED_REF dans le périmètre demandé."
        exit 0
    fi
    echo "Périmètre --changed ($CHANGED_REF) : ${#FILES[@]} fichier(s)"
fi

# Cibles ruff : les fichiers .py modifiés en mode --changed, sinon les modules.
ruff_targets() {
    if [ "$CHANGED" -eq 1 ]; then
        local py=()
        for f in "${FILES[@]}"; do
            case "$f" in *.py) py+=("$f") ;; esac
        done
        printf '%s\n' "${py[@]}"
    else
        printf '%s\n' "$@"
    fi
}

# run_ruff <inline-config-ou-vide> <cible...>
run_ruff() {
    local overlay="$1"; shift
    local -a extra=()
    [ -n "$overlay" ] && extra=(--config "$overlay")

    if command -v ruff >/dev/null 2>&1; then
        ruff check --no-cache --config "$RUFF_CONFIG" "${extra[@]}" \
            --output-format concise "$@"
    elif python3 -c "import ruff" >/dev/null 2>&1; then
        python3 -m ruff check --no-cache --config "$RUFF_CONFIG" "${extra[@]}" \
            --output-format concise "$@"
    elif command -v docker >/dev/null 2>&1 \
            && docker image inspect "$QA_IMAGE" >/dev/null 2>&1; then
        # Les cibles peuvent être des dossiers (mode normal) ou des fichiers
        # (mode --changed) : on monte leur ancêtre commun une seule fois.
        local rc=0 out root
        root="$(python3 -c '
import os, sys
paths = [os.path.abspath(p) for p in sys.argv[1:]]
root = os.path.commonpath(paths) if len(paths) > 1 else paths[0]
print(root if os.path.isdir(root) else os.path.dirname(root))
' "$@")"
        local -a rel=()
        for target in "$@"; do
            rel+=("/src/$(realpath --relative-to="$root" "$target")")
        done
        out="$(mktemp)"
        docker run --rm \
            -v "$root":/src:ro \
            -v "$RUFF_CONFIG":/ruff.toml:ro \
            "$QA_IMAGE" \
            ruff check --no-cache --config /ruff.toml "${extra[@]}" \
                --output-format concise "${rel[@]}" >"$out" 2>&1 || rc=1
        # ruff imprime des chemins relatifs au cwd du conteneur (`src/...`) :
        # on les réécrit en chemins hôte pour qu'ils restent localisables.
        sed -e "s|^/src/|$root/|" -e "s|^src/|$root/|" "$out"
        rm -f "$out"
        return "$rc"
    else
        return 127
    fi
}

echo "══ 1/3  ruff — règles bloquantes (config Odoo $(basename "$(dirname "$RUFF_CONFIG")")) ══"
mapfile -t RUFF_TARGETS < <(ruff_targets "$@")
if [ "${#RUFF_TARGETS[@]}" -eq 0 ]; then
    RUFF_TARGETS=("$@")
fi
RUFF_OUT="$(run_ruff "$NOT_ENFORCED" "${RUFF_TARGETS[@]}")"
RUFF_RC=$?
if [ "$RUFF_RC" -eq 127 ]; then
    echo "IGNORÉ : ruff introuvable (ni sur l'hôte, ni dans l'image $QA_IMAGE)."
    echo "         pip install --user ruff   OU   odoo-stack.sh build"
    STATUS=2
else
    echo "$RUFF_OUT"
    [ "$RUFF_RC" -eq 0 ] || STATUS=1
fi

if [ "$RUFF_RC" -ne 127 ]; then
    echo
    echo "══ 2/3  ruff — conseils (config complète, non bloquant) ═════════════════"
    ADVICE="$(run_ruff "" "${RUFF_TARGETS[@]}" \
        | grep -E '^[^ ]+:[0-9]+:[0-9]+: ' \
        | sed -E 's/^[^ ]+: //; s/:.*//' | sort | uniq -c | sort -rn)"
    if [ -n "$ADVICE" ]; then
        echo "$ADVICE" | head -15
        echo "(détail : ruff check --config $RUFF_CONFIG <module>)"
    else
        echo "aucun."
    fi
fi

echo
echo "══ 3/3  contrôles Odoo (manifest, XML, sécurité, tests) ═════════════════"
if [ "$CHANGED" -eq 1 ]; then
    python3 "$HERE/odoo_lint.py" "${SERIES_ARG[@]}" "$@" \
        --only-files "${FILES[@]}" || STATUS=1
else
    python3 "$HERE/odoo_lint.py" "${SERIES_ARG[@]}" "$@" || STATUS=1
fi

echo
case "$STATUS" in
    0) echo "✅ lint OK" ;;
    2) echo "⚠️  lint partiel : ruff n'a pas pu s'exécuter" ;;
    *) echo "❌ lint en échec" ;;
esac
exit "$STATUS"
