#!/usr/bin/env bash
# Pilotage du stack Odoo de QA (docker compose), série par série.
#
# La série est déduite du module présent dans $ODOO_ADDONS_DIR, ou forcée par
# $ODOO_SERIES. Chaque série a son image, son projet compose, ses volumes et sa
# base : `odoo-stack.sh build` est donc à relancer une fois par série utilisée.
#
#   odoo-stack.sh build           construit l'image (odoo:<série> + chrome + ruff)
#   odoo-stack.sh up              démarre db + odoo
#   odoo-stack.sh down            arrête (conserve les volumes)
#   odoo-stack.sh reset           arrête ET supprime les volumes (base neuve)
#   odoo-stack.sh logs [n]        n dernières lignes des logs odoo (défaut 200)
#   odoo-stack.sh shell           shell dans le conteneur odoo
#   odoo-stack.sh psql [db]       psql sur la base (défaut $ODOO_TEST_DB)
#   odoo-stack.sh odoo-shell [db] shell Odoo (env, self, ...) sur la base
#   odoo-stack.sh status          état des services + URL
#
# Variables : ODOO_SERIES, ODOO_ADDONS_DIR, ODOO_HTTP_PORT, ODOO_DB_PORT, ODOO_TEST_DB
# (voir stack/.env.example)

set -euo pipefail

STACK="$(cd "$(dirname "${BASH_SOURCE[0]}")/../stack" && pwd)"
# shellcheck source=series-env.sh
. "$(dirname "${BASH_SOURCE[0]}")/series-env.sh"
DB="$ODOO_TEST_DB"
HTTP_PORT="${ODOO_HTTP_PORT:-8079}"

cd "$STACK"
[ -f .env ] || true   # docker compose charge .env automatiquement s'il existe

compose() { docker compose "$@"; }

case "${1:-status}" in
    build)
        compose build
        ;;
    up)
        compose up -d
        echo "Odoo : http://localhost:${HTTP_PORT}   (admin / admin)"
        echo "Série : ${ODOO_SERIES}   image : odoo-qa:${ODOO_SERIES}   base : ${DB}"
        echo "Addons custom montés depuis : ${ODOO_ADDONS_DIR:-(ODOO_ADDONS_DIR non défini)}"
        ;;
    down)
        compose down
        ;;
    reset)
        compose down -v
        echo "Volumes supprimés : la prochaine installation partira d'une base neuve."
        ;;
    logs)
        compose logs --tail "${2:-200}" odoo
        ;;
    shell)
        compose exec odoo bash
        ;;
    psql)
        compose exec db psql -U odoo -d "${2:-$DB}"
        ;;
    odoo-shell)
        compose run --rm odoo odoo shell \
            -c /etc/odoo/odoo.conf -d "${2:-$DB}" --no-http
        ;;
    status)
        compose ps
        echo
        echo "Série   : ${ODOO_SERIES}  (image odoo-qa:${ODOO_SERIES})"
        echo "URL     : http://localhost:${HTTP_PORT}"
        echo "Base    : ${DB}"
        echo "Addons  : ${ODOO_ADDONS_DIR:-(ODOO_ADDONS_DIR non défini)}"
        ;;
    *)
        sed -n '2,20p' "$0"
        exit 2
        ;;
esac
