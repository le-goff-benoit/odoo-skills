#!/usr/bin/env bash
# Rend un rapport QWeb en PDF RÉEL et MIS EN FORME, dans le conteneur.
#
#   odoo-pdf.sh <report_ref> <ids> [options]
#
# Exemples :
#   odoo-pdf.sh sale.action_report_saleorder 12
#   odoo-pdf.sh account.account_invoices "5,6,7" --out factures.pdf
#   odoo-pdf.sh mon_module.action_report_x 3 --html      # sort aussi le HTML source
#
# Options :
#   --out <fichier>       nom du fichier dans stack/artifacts (défaut <report>.pdf)
#   --db <base>           base (défaut $ODOO_TEST_DB)
#   --login/--password    identifiants (défaut admin/admin)
#   --html                écrit aussi le HTML rendu, pour diagnostiquer un QWeb cassé
#
# Trois pièges traités ici :
#  1. `_render_qweb_pdf` retombe silencieusement sur `_render_qweb_html` en contexte
#     de test (ir_actions_report.py::_pre_render_qweb_pdf) → on vérifie l'en-tête %PDF.
#  2. wkhtmltopdf récupère les feuilles de style sur le serveur HTTP d'Odoo. Depuis un
#     conteneur jetable, rien n'écoute : PDF sans mise en forme, simple WARNING.
#  3. Les bundles d'assets sont générés par le PROCESSUS SERVEUR. Un rendu lancé
#     depuis `odoo shell` produit des URL /web/assets/<hash> que le serveur ne connaît
#     pas encore → 404 et PDF nu.
#     → on télécharge donc le PDF par la route réelle `/report/pdf/<report>/<ids>`,
#       exactement comme le bouton « Imprimer » de l'interface.

set -euo pipefail

STACK="$(cd "$(dirname "${BASH_SOURCE[0]}")/../stack" && pwd)"
# shellcheck source=series-env.sh
. "$(dirname "${BASH_SOURCE[0]}")/series-env.sh"
CONF="/etc/odoo/odoo.conf"

REPORT="${1:-}"; IDS="${2:-}"
if [ -z "$REPORT" ] || [ -z "$IDS" ]; then
    sed -n '2,16p' "$0" >&2
    exit 2
fi
shift 2

DB="${ODOO_TEST_DB:-odoo_qa}"
OUT="${REPORT}.pdf"
LOGIN="admin"; PASSWORD="admin"; WITH_HTML=""

while [ $# -gt 0 ]; do
    case "$1" in
        --out)      shift; OUT="$1" ;;
        --db)       shift; DB="$1" ;;
        --login)    shift; LOGIN="$1" ;;
        --password) shift; PASSWORD="$1" ;;
        --html)     WITH_HTML=1 ;;
        *) echo "option inconnue : $1" >&2; exit 2 ;;
    esac
    shift
done

cd "$STACK"
mkdir -p artifacts && chmod 777 artifacts

if ! docker compose ps --status running --services 2>/dev/null | grep -qx odoo; then
    echo "Le service odoo ne tourne pas — démarrage…"
    docker compose up -d odoo
    for _ in $(seq 1 60); do
        docker compose exec -T odoo python3 -c \
            "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8069/web/login',timeout=2)" \
            >/dev/null 2>&1 && break
        sleep 1
    done
fi

OUTLOG="$(mktemp)"
trap 'rm -f "$OUTLOG"' EXIT

docker compose exec -T \
    -e REPORT="$REPORT" -e IDS="$IDS" -e OUT="$OUT" -e WITH_HTML="$WITH_HTML" \
    -e DB="$DB" -e LOGIN="$LOGIN" -e PASSWORD="$PASSWORD" \
    odoo odoo shell -c "$CONF" -d "$DB" --no-http 2>&1 <<'PY' | tee "$OUTLOG"
import os
import pathlib

import requests

BASE = 'http://127.0.0.1:8069'
report_ref = os.environ['REPORT']
res_ids = [int(i) for i in os.environ['IDS'].split(',') if i.strip()]
out = pathlib.Path('/mnt/artifacts') / os.environ['OUT']

actions = env['ir.actions.report']
state = actions.get_wkhtmltopdf_state()
print(f"ETAT_WKHTMLTOPDF: {state}")
if state not in ('ok', 'workers'):
    raise SystemExit(f"wkhtmltopdf inutilisable : {state}")

report = env.ref(report_ref, raise_if_not_found=False)
if not report:
    raise SystemExit(f"rapport introuvable : {report_ref}")
print(f"RAPPORT: {report.report_name}  modele={report.model}  type={report.report_type}")

missing = set(res_ids) - set(env[report.model].browse(res_ids).exists().ids)
if missing:
    raise SystemExit(f"enregistrements inexistants sur {report.model} : {sorted(missing)}")

if os.environ.get('WITH_HTML'):
    html, _ = actions._render_qweb_html(report_ref, res_ids)
    html_path = out.with_suffix('.html')
    html_path.write_bytes(html)
    print(f"HTML: {html_path} ({len(html)} octets)")

# Téléchargement par la route réelle : c'est le processus serveur qui rend le
# document, donc les bundles d'assets qu'il référence existent bien.
session = requests.Session()
auth = session.post(
    f'{BASE}/web/session/authenticate',
    json={'params': {
        'db': os.environ['DB'],
        'login': os.environ['LOGIN'],
        'password': os.environ['PASSWORD'],
    }},
    timeout=30,
).json()
if auth.get('error') or not auth.get('result', {}).get('uid'):
    raise SystemExit(f"authentification refusée pour {os.environ['LOGIN']}")

ids = ','.join(str(i) for i in res_ids)
response = session.get(f'{BASE}/report/pdf/{report.report_name}/{ids}', timeout=180)
if response.status_code != 200:
    raise SystemExit(f"/report/pdf a répondu {response.status_code}")

content = response.content
if not content.startswith(b'%PDF'):
    raise SystemExit("le contenu produit ne commence pas par %PDF")

out.write_bytes(content)
pages = content.count(b'/Type /Page') or content.count(b'/Type/Page')
print(f"PDF_OK: {out} ({len(content)} octets, ~{pages} page(s))")
PY

if grep -q "due to network error" "$OUTLOG"; then
    echo
    echo "❌ wkhtmltopdf n'a pas pu charger les assets : le PDF serait sans mise en forme."
    exit 1
fi
grep -q "PDF_OK" "$OUTLOG" || exit 1

echo "→ $STACK/artifacts/$OUT"
