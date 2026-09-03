#!/usr/bin/env bash
# Capture d'écran authentifiée d'une page Odoo, dans le Chrome du conteneur.
#
#   odoo-shot.sh <chemin> [options]
#
# Exemples :
#   odoo-shot.sh /odoo/sales
#   odoo-shot.sh /odoo/action-mon_module.action_x --out ecran_liste.png
#   odoo-shot.sh "/odoo/sales/12" --wait ".o_form_view" --full --out fiche.png
#   odoo-shot.sh /my/orders --login portal --password portal --wait "body"
#
# Options :
#   --out <fichier.png>   nom du PNG dans stack/artifacts (défaut shot.png)
#   --wait <sélecteur>    sélecteur CSS à attendre (défaut .o_action_manager)
#   --login/--password    identifiants (défaut admin/admin)
#   --db <base>           base (défaut $ODOO_TEST_DB)
#   --size <LxH>          viewport (défaut 1920x1080)
#   --full                capture toute la hauteur de la page
#   --timeout <s>         défaut 30
#
# Prérequis : le service odoo doit tourner (odoo-stack.sh up).

set -euo pipefail

STACK="$(cd "$(dirname "${BASH_SOURCE[0]}")/../stack" && pwd)"
# shellcheck source=series-env.sh
. "$(dirname "${BASH_SOURCE[0]}")/series-env.sh"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

URL="${1:-}"
if [ -z "$URL" ] || [[ "$URL" == --* ]]; then
    sed -n '2,22p' "$0" >&2
    exit 2
fi
shift

DB="${ODOO_TEST_DB:-odoo_qa}"
OUT="shot.png"; WAIT=""; LOGIN="admin"; PASSWORD="admin"
WIDTH=1920; HEIGHT=1080; FULL=""; TIMEOUT=30

while [ $# -gt 0 ]; do
    case "$1" in
        --out)      shift; OUT="$1" ;;
        --wait)     shift; WAIT="$1" ;;
        --login)    shift; LOGIN="$1" ;;
        --password) shift; PASSWORD="$1" ;;
        --db)       shift; DB="$1" ;;
        --size)     shift; WIDTH="${1%x*}"; HEIGHT="${1#*x}" ;;
        --timeout)  shift; TIMEOUT="$1" ;;
        --full)     FULL=1 ;;
        *) echo "option inconnue : $1" >&2; exit 2 ;;
    esac
    shift
done

cd "$STACK"
mkdir -p artifacts && chmod 777 artifacts

if ! docker compose ps --status running --services 2>/dev/null | grep -qx odoo; then
    echo "Le service odoo ne tourne pas — démarrage…"
    docker compose up -d odoo
    # Attendre que le serveur réponde avant de lancer Chrome.
    for _ in $(seq 1 60); do
        docker compose exec -T odoo python3 -c \
            "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8069/web/login',timeout=2)" \
            >/dev/null 2>&1 && break
        sleep 1
    done
fi

docker compose exec -T \
    -e SHOT_URL="$URL" \
    -e SHOT_DB="$DB" \
    -e SHOT_LOGIN="$LOGIN" \
    -e SHOT_PASSWORD="$PASSWORD" \
    -e SHOT_OUT="$OUT" \
    -e SHOT_WAIT="$WAIT" \
    -e SHOT_WIDTH="$WIDTH" \
    -e SHOT_HEIGHT="$HEIGHT" \
    -e SHOT_FULL="$FULL" \
    -e SHOT_TIMEOUT="$TIMEOUT" \
    odoo python3 - < "$HERE/odoo_shot.py"

echo "→ $STACK/artifacts/$OUT"
