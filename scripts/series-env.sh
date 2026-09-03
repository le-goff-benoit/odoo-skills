# Bootstrap de série, à sourcer par les scripts du stack.
#
# Détermine la série Odoo cible et exporte tout ce dont docker compose a besoin
# pour que deux séries cohabitent sans se marcher dessus : projet compose, image,
# volumes, base et sources enterprise sont tous suffixés par la série.
#
# Ordre : $ODOO_SERIES > .odoo-agents/config du projet > manifest du module
# trouvé dans $ODOO_ADDONS_DIR > 19.0.

_series_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_series_probe="${ODOO_ADDONS_DIR:-}"

if [ -z "${ODOO_SERIES:-}" ] && [ -n "$_series_probe" ] && [ -d "$_series_probe" ]; then
    ODOO_SERIES="$(python3 "$_series_here/odoo_series.py" "$_series_probe" 2>/dev/null \
                   | sed -n 's/^ODOO_SERIES=//p')"
fi
export ODOO_SERIES="${ODOO_SERIES:-19.0}"
export ODOO_SERIES_SLUG="${ODOO_SERIES//./_}"
export ODOO_ENTERPRISE_DIR="${ODOO_ENTERPRISE_DIR:-${ODOO_SOURCES_DIR:-$HOME/odoo-sources}/${ODOO_SERIES}-enterprise}"
export ODOO_TEST_DB="${ODOO_TEST_DB:-odoo_qa_${ODOO_SERIES_SLUG}}"

if [ ! -d "$ODOO_ENTERPRISE_DIR" ]; then
    echo "⚠️  sources enterprise absentes : $ODOO_ENTERPRISE_DIR" >&2
fi
