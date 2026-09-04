#!/usr/bin/env bash
# Cycle de vie d'un lot de changelog (une « release » livrable au client).
#
#   odoo-lot.sh open    <racine_projet> "<titre>"     ouvre changelog/AAAA-MM-JJ_NN_titre/
#   odoo-lot.sh current <racine_projet>               chemin du lot ouvert (vide sinon)
#   odoo-lot.sh list    <racine_projet>               tous les lots, état en tête
#   odoo-lot.sh points  <lot>                         les points suivis dans le README du lot
#   odoo-lot.sh add     <lot> "<point>" [test ciblé]  ajoute un point au suivi (état : à faire)
#   odoo-lot.sh done    <lot> <n°> [résultat]         marque un point réalisé
#   odoo-lot.sh changed <lot>                         fichiers modifiés depuis l'ouverture
#   odoo-lot.sh modules <lot>                         modules Odoo touchés depuis l'ouverture
#   odoo-lot.sh close   <lot>                         retire le marqueur « ouvert »
#
# Un lot est ouvert tant que son README.md porte le marqueur `<!-- lot ouvert -->`.
# À l'ouverture, `.base` retient le commit git de départ : c'est la référence de
# `odoo-lint.sh --changed`, de `git diff` et du calcul de version à la clôture.
#
# Pendant que le lot est ouvert, le suivi est léger (un point = une ligne du
# README, un test ciblé). La recette complète, les captures et les livrables
# client se font à la clôture : /odoo-cloture.

set -euo pipefail
shopt -s nullglob

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATES="$HERE/../docs/templates/changelog"
MARK="<!-- lot ouvert -->"

usage() { sed -n '2,20p' "$0" >&2; exit 2; }

slugify() {
    printf '%s' "$1" | iconv -f utf-8 -t ascii//TRANSLIT 2>/dev/null \
        | tr 'A-Z' 'a-z' | sed 's/[^a-z0-9]\+/-/g; s/^-//; s/-$//' | cut -c1-40
}

lot_root() {   # racine du projet à partir d'un chemin de lot
    cd "$1/../.." && pwd
}

is_open() { [ -f "$1/README.md" ] && grep -qF "$MARK" "$1/README.md"; }

cmd="${1:-}"; shift || true
case "$cmd" in
    open)
        ROOT="${1:-}"; TITLE="${2:-}"
        [ -d "$ROOT" ] && [ -n "$TITLE" ] || usage
        ROOT="$(cd "$ROOT" && pwd)"
        if current="$("$0" current "$ROOT")" && [ -n "$current" ]; then
            echo "Un lot est déjà ouvert : $current" >&2
            echo "Le clôturer (/odoo-cloture) avant d'en ouvrir un autre, ou y ajouter le point." >&2
            exit 1
        fi
        DAY="$(date +%F)"
        existing=("$ROOT/changelog/${DAY}_"*/)
        NN=$(( ${#existing[@]} + 1 ))
        LOT="$ROOT/changelog/${DAY}_$(printf '%02d' "$NN")_$(slugify "$TITLE")"
        mkdir -p "$LOT/captures"
        git -C "$ROOT" rev-parse HEAD 2>/dev/null > "$LOT/.base" || echo "sans-git" > "$LOT/.base"
        sed -e "s/<Titre du lot>/$TITLE/" -e "s/<jj mois aaaa>/$(date '+%d.%m.%Y')/" \
            "$TEMPLATES/suivi.md" > "$LOT/README.md"
        printf '# Demande\n\n<!-- Copier chaque demande telle quelle, datée. Ne pas reformuler. -->\n\n' \
            > "$LOT/demande.md"
        echo "$LOT"
        ;;
    current)
        ROOT="${1:-}"; [ -d "$ROOT" ] || usage
        lots=("$ROOT"/changelog/*/)
        for (( i=${#lots[@]}-1; i>=0; i-- )); do
            lot="${lots[$i]%/}"
            if is_open "$lot"; then echo "$lot"; exit 0; fi
        done
        exit 0
        ;;
    list)
        ROOT="${1:-}"; [ -d "$ROOT" ] || usage
        lots=("$ROOT"/changelog/*/)
        for (( i=${#lots[@]}-1; i>=0; i-- )); do
            lot="${lots[$i]%/}"
            if is_open "$lot"; then state="OUVERT "; elif [ -f "$lot/README.md" ]; then state="clos   "; else state="?      "; fi
            echo "$state $(basename "$lot")"
        done
        ;;
    points)
        LOT="${1:-}"; [ -f "$LOT/README.md" ] || exit 0
        # Tolère les tableaux de suivi maison (colonnes supplémentaires) : n°, libellé, dernière colonne = état.
        awk -F'|' '/^\| *[0-9]+ *\|/ {
            n=$2; gsub(/^ +| +$/, "", n); lib=$3; gsub(/^ +| +$/, "", lib);
            etat=$(NF-1); gsub(/^ +| +$/, "", etat);
            printf "%s. %s [%s]\n", n, lib, etat }' "$LOT/README.md"
        ;;
    add)
        LOT="${1:-}"; POINT="${2:-}"; TEST="${3:-—}"
        [ -f "$LOT/README.md" ] && [ -n "$POINT" ] || usage
        is_open "$LOT" || { echo "Lot clos : $LOT" >&2; exit 1; }
        N=$(( $(awk '/^\| *[0-9]+ *\|/' "$LOT/README.md" | wc -l) + 1 ))
        # Insère la ligne juste avant la première ligne vide qui suit le tableau des points.
        python3 - "$LOT/README.md" "$N" "$POINT" "$TEST" <<'PY'
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
        LOT="${1:-}"; N="${2:-}"; RESULT="${3:-fait}"
        [ -f "$LOT/README.md" ] && [ -n "$N" ] || usage
        python3 - "$LOT/README.md" "$N" "$RESULT" <<'PY'
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
        LOT="${1:-}"; [ -d "$LOT" ] || usage
        ROOT="$(lot_root "$LOT")"
        BASE="$(cat "$LOT/.base" 2>/dev/null || echo HEAD)"
        [ "$BASE" = "sans-git" ] && { echo "projet sans git : périmètre indéterminable" >&2; exit 1; }
        {
            git -C "$ROOT" diff --name-only "$BASE" 2>/dev/null
            git -C "$ROOT" ls-files --others --exclude-standard 2>/dev/null
        } | grep -v "^changelog/" | sort -u
        ;;
    modules)
        LOT="${1:-}"; [ -d "$LOT" ] || usage
        ROOT="$(lot_root "$LOT")"
        "$0" changed "$LOT" | while IFS= read -r f; do
            d="$ROOT/$(dirname "$f")"
            while [ "$d" != "$ROOT" ] && [ "$d" != "/" ]; do
                if [ -f "$d/__manifest__.py" ]; then echo "$d"; break; fi
                d="$(dirname "$d")"
            done
        done | sort -u
        ;;
    close)
        LOT="${1:-}"; [ -f "$LOT/README.md" ] || usage
        sed -i "/$(printf '%s' "$MARK" | sed 's/[][\/.*^$]/\\&/g')/d" "$LOT/README.md"
        echo "Lot clos : $LOT"
        ;;
    *) usage ;;
esac
