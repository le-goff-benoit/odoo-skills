#!/usr/bin/env bash
# Cycle de vie d'une release de changelog (une « release » livrable au client).
#
#   odoo-release.sh open    <racine_projet> "<titre>"     ouvre changelog/AAAA-MM-JJ_NN_titre/
#   odoo-release.sh current <racine_projet>               chemin de la release ouverte (vide sinon)
#   odoo-release.sh list    <racine_projet>               tous les releases, état en tête
#   odoo-release.sh points  <release>                         les points suivis dans le README de la release
#   odoo-release.sh add     <release> "<point>" [test ciblé]  ajoute un point au suivi (état : à faire)
#   odoo-release.sh done    <release> <n°> [résultat]         marque un point réalisé
#   odoo-release.sh changed <release>                         fichiers modifiés depuis l'ouverture
#   odoo-release.sh modules <release>                         modules Odoo touchés depuis l'ouverture
#   odoo-release.sh close   <release>                         retire le marqueur « ouvert »
#
# Une release est ouverte tant que son README.md porte le marqueur `<!-- release ouverte -->`.
# À l'ouverture, `.base` retient le commit git de départ : c'est la référence de
# `odoo-lint.sh --changed`, de `git diff` et du calcul de version à la clôture.
#
# Pendant que la release est ouverte, le suivi est léger (un point = une ligne du
# README, un test ciblé). La recette complète, les captures et les livrables
# client se font à la clôture : /odoo-close.

set -euo pipefail
shopt -s nullglob

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATES="$HERE/../docs/templates/changelog"
MARK="<!-- release ouverte -->"

usage() { sed -n '2,20p' "$0" >&2; exit 2; }

slugify() {
    printf '%s' "$1" | iconv -f utf-8 -t ascii//TRANSLIT 2>/dev/null \
        | tr 'A-Z' 'a-z' | sed 's/[^a-z0-9]\+/-/g; s/^-//; s/-$//' | cut -c1-40
}

lot_root() {   # racine du projet à partir d'un chemin de release
    cd "$1/../.." && pwd
}

is_open() { [ -f "$1/README.md" ] && grep -qE "<!-- (release ouverte|lot ouvert) -->" "$1/README.md"; }

cmd="${1:-}"; shift || true
case "$cmd" in
    open)
        ROOT="${1:-}"; TITLE="${2:-}"
        [ -d "$ROOT" ] && [ -n "$TITLE" ] || usage
        ROOT="$(cd "$ROOT" && pwd)"
        if current="$("$0" current "$ROOT")" && [ -n "$current" ]; then
            echo "Une release est déjà ouverte : $current" >&2
            echo "Le clôturer (/odoo-close) avant d'en ouvrir un autre, ou y ajouter le point." >&2
            exit 1
        fi
        DAY="$(date +%F)"
        existing=("$ROOT/changelog/${DAY}_"*/)
        NN=$(( ${#existing[@]} + 1 ))
        RELEASE="$ROOT/changelog/${DAY}_$(printf '%02d' "$NN")_$(slugify "$TITLE")"
        mkdir -p "$RELEASE/captures"
        if [ ! -d "$ROOT/inbox" ]; then
            mkdir -p "$ROOT/inbox"
            printf '# Dépôt pour l'"'"'humain : sauvegardes (.zip/.dump/.sql) et mails (.eml)\n# à l'"'"'attention des agents. Jamais versionné.\n*\n!.gitignore\n' > "$ROOT/inbox/.gitignore"
        fi
        git -C "$ROOT" rev-parse HEAD 2>/dev/null > "$RELEASE/.base" || echo "sans-git" > "$RELEASE/.base"
        date -u +%Y-%m-%dT%H:%M:%S > "$RELEASE/.opened"    # pour odoo_pack.py export --since
        LABEL="$(sed -n 's/^ *lot_label *[=:] *\([^ ]*\).*/\1/p' "$ROOT/.odoo-agents/config" 2>/dev/null | head -1)"
        LABEL="${LABEL:-release}"
        sed -e "s/<Titre de la release>/$TITLE/" -e "s/<jj mois aaaa>/$(date '+%d.%m.%Y')/" \
            -e "s/<release>/$LABEL/g" -e "s/<Release>/${LABEL^}/g" \
            "$TEMPLATES/suivi.md" > "$RELEASE/README.md"
        printf '# Demande\n\n<!-- Copier chaque demande telle quelle, datée. Ne pas reformuler. -->\n\n' \
            > "$RELEASE/demande.md"
        echo "$RELEASE"
        ;;
    current)
        ROOT="${1:-}"; [ -d "$ROOT" ] || usage
        releases=("$ROOT"/changelog/*/)
        for (( i=${#releases[@]}-1; i>=0; i-- )); do
            release="${releases[$i]%/}"
            if is_open "$release"; then echo "$release"; exit 0; fi
        done
        exit 0
        ;;
    list)
        ROOT="${1:-}"; [ -d "$ROOT" ] || usage
        releases=("$ROOT"/changelog/*/)
        for (( i=${#releases[@]}-1; i>=0; i-- )); do
            release="${releases[$i]%/}"
            if is_open "$release"; then state="OUVERT "; elif [ -f "$release/README.md" ]; then state="clos   "; else state="?      "; fi
            echo "$state $(basename "$release")"
        done
        ;;
    points)
        RELEASE="${1:-}"; [ -f "$RELEASE/README.md" ] || exit 0
        # Tolère les tableaux de suivi maison (colonnes supplémentaires) : n°, libellé, dernière colonne = état.
        awk -F'|' '/^\| *[0-9]+ *\|/ {
            n=$2; gsub(/^ +| +$/, "", n); lib=$3; gsub(/^ +| +$/, "", lib);
            etat=$(NF-1); gsub(/^ +| +$/, "", etat);
            printf "%s. %s [%s]\n", n, lib, etat }' "$RELEASE/README.md"
        ;;
    add)
        RELEASE="${1:-}"; POINT="${2:-}"; TEST="${3:-—}"
        [ -f "$RELEASE/README.md" ] && [ -n "$POINT" ] || usage
        is_open "$RELEASE" || { echo "Release clos : $RELEASE" >&2; exit 1; }
        N=$(( $(awk '/^\| *[0-9]+ *\|/' "$RELEASE/README.md" | wc -l) + 1 ))
        # Insère la ligne juste avant la première ligne vide qui suit le tableau des points.
        python3 - "$RELEASE/README.md" "$N" "$POINT" "$TEST" <<'PY'
import re, sys
path, n, point, test = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
text = open(path, encoding="utf-8").read()
row = f"| {n} | {point} | {test} | à faire |\n"
m = list(re.finditer(r"(?m)^\|.*\|\n", text))
# dernière ligne du premier tableau (celui des points)
header = re.search(r"(?m)^\| *(#|N°|n°|No) *\|", text)
if not header:
    sys.exit("tableau des points introuvable dans " + path)
pos = header.end()
while True:
    nxt = text.find("\n", pos) + 1
    if nxt <= 0 or not text[nxt:].startswith("|"):
        break
    pos = nxt
end = text.find("\n", pos) + 1
text = text[:end] + row + text[end:]
open(path, "w", encoding="utf-8").write(text)
PY
        echo "$N"
        ;;
    done)
        RELEASE="${1:-}"; N="${2:-}"; RESULT="${3:-fait}"
        [ -f "$RELEASE/README.md" ] && [ -n "$N" ] || usage
        python3 - "$RELEASE/README.md" "$N" "$RESULT" <<'PY'
import re, sys
path, n, result = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(path, encoding="utf-8").read()
pattern = re.compile(r"(?m)^(\| *%s *\|[^|]*\|[^|]*\|)[^|]*\|" % re.escape(n))
if not pattern.search(text):
    sys.exit(f"point {n} introuvable")
text = pattern.sub(lambda m: f"{m.group(1)} {result} |", text, count=1)
open(path, "w", encoding="utf-8").write(text)
PY
        ;;
    changed)
        RELEASE="${1:-}"; [ -d "$RELEASE" ] || usage
        ROOT="$(lot_root "$RELEASE")"
        BASE="$(cat "$RELEASE/.base" 2>/dev/null || echo HEAD)"
        [ "$BASE" = "sans-git" ] && { echo "projet sans git : périmètre indéterminable" >&2; exit 1; }
        {
            git -C "$ROOT" diff --name-only "$BASE" 2>/dev/null
            git -C "$ROOT" ls-files --others --exclude-standard 2>/dev/null
        } | grep -v "^changelog/" | sort -u
        ;;
    modules)
        RELEASE="${1:-}"; [ -d "$RELEASE" ] || usage
        ROOT="$(lot_root "$RELEASE")"
        "$0" changed "$RELEASE" | while IFS= read -r f; do
            d="$ROOT/$(dirname "$f")"
            while [ "$d" != "$ROOT" ] && [ "$d" != "/" ]; do
                if [ -f "$d/__manifest__.py" ]; then echo "$d"; break; fi
                d="$(dirname "$d")"
            done
        done | sort -u
        ;;
    close)
        RELEASE="${1:-}"; [ -f "$RELEASE/README.md" ] || usage
        sed -i -E '/<!-- (release ouverte|lot ouvert) -->/d' "$RELEASE/README.md"
        echo "Release clos : $RELEASE"
        ;;
    *) usage ;;
esac
