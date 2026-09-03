#!/usr/bin/env bash
# Inventaire de la configuration « hors code » d'une base restaurée sur le stack QA.
#
#   odoo-config-inventory.sh <base>
#
# Le relevé de projet (odoo_project_scan.py) ne voit que le code. Or une grande part
# de ce qu'un client a déjà vit dans sa base : champs Studio, automatisations,
# actions serveur, vues modifiées, rapports personnalisés, modules tiers. Une revue
# fonctionnelle qui l'ignore conclut « à développer » pour ce qui existe déjà.
#
# Sort, en texte, dans l'ordre : modules non Odoo installés, champs manuels (Studio),
# automatisations, actions serveur personnalisées, vues Studio / personnalisées,
# rapports personnalisés, sociétés, langues actives, utilisateurs actifs.
#
# Prérequis : la base tourne sur le stack (odoo-restore.sh, odoo-stack.sh up).

set -euo pipefail

DB="${1:-}"
[ -n "$DB" ] || { sed -n '2,15p' "$0" >&2; exit 2; }

STACK="$(cd "$(dirname "${BASH_SOURCE[0]}")/../stack" && pwd)"
# shellcheck source=series-env.sh
. "$(dirname "${BASH_SOURCE[0]}")/series-env.sh"
cd "$STACK"

q() { docker compose exec -T db psql -U odoo -d "$DB" -X -q -P pager=off -v ON_ERROR_STOP=0 "$@"; }
section() { printf '\n== %s ==\n' "$1"; }

echo "ODOO_SERIES=$ODOO_SERIES  base=$DB"

section "Modules installés hors Odoo S.A."
q -c "SELECT name, latest_version AS version, author
      FROM ir_module_module
      WHERE state IN ('installed','to upgrade')
        AND coalesce(author,'') NOT ILIKE 'Odoo%'
      ORDER BY name;"

section "Champs manuels (Studio / créés en base) — modèle, champ, type, libellé"
q -c "SELECT model, name, ttype, COALESCE(field_description->>'en_US', field_description::text) AS label
      FROM ir_model_fields WHERE state = 'manual' ORDER BY model, name;" 2>/dev/null \
 || q -c "SELECT model, name, ttype FROM ir_model_fields WHERE state = 'manual' ORDER BY model, name;"

section "Automatisations (base.automation)"
q -c "SELECT a.id, COALESCE(s.name->>'en_US', s.name::text) AS name, a.trigger, m.model, a.active
      FROM base_automation a
      JOIN ir_act_server s ON s.id = a.action_server_id
      JOIN ir_model m ON m.id = a.model_id
      ORDER BY m.model, a.id;" 2>/dev/null || echo "(module base_automation absent)"

section "Actions serveur créées par des utilisateurs (hors données de module)"
q -c "SELECT s.id, COALESCE(s.name->>'en_US', s.name::text) AS name, s.state, m.model
      FROM ir_act_server s
      JOIN ir_model m ON m.id = s.model_id
      WHERE NOT EXISTS (SELECT 1 FROM ir_model_data d
                        WHERE d.model = 'ir.actions.server' AND d.res_id = s.id
                          AND d.module NOT IN ('__export__','studio_customization'))
      ORDER BY m.model, s.id;"

section "Vues Studio ou personnalisées en base"
q -c "SELECT v.id, v.model, v.type, COALESCE(v.name->>'en_US', v.name::text) AS name, v.inherit_id
      FROM ir_ui_view v
      WHERE v.key LIKE 'studio_customization.%'
         OR EXISTS (SELECT 1 FROM ir_model_data d WHERE d.model='ir.ui.view' AND d.res_id=v.id
                    AND d.module IN ('studio_customization','__export__'))
      ORDER BY v.model, v.id;" 2>/dev/null \
 || q -c "SELECT v.id, v.model, v.type, v.name FROM ir_ui_view v WHERE v.key LIKE 'studio_customization.%' ORDER BY v.model, v.id;"

section "Rapports personnalisés (ir.actions.report hors données de module)"
q -c "SELECT r.id, COALESCE(r.name->>'en_US', r.name::text) AS name, r.model, r.report_name
      FROM ir_act_report_xml r
      WHERE NOT EXISTS (SELECT 1 FROM ir_model_data d
                        WHERE d.model = 'ir.actions.report' AND d.res_id = r.id
                          AND d.module NOT IN ('__export__','studio_customization'))
      ORDER BY r.model, r.id;" 2>/dev/null \
 || q -c "SELECT r.id, r.name, r.model, r.report_name FROM ir_act_report_xml r
          WHERE NOT EXISTS (SELECT 1 FROM ir_model_data d WHERE d.model='ir.actions.report' AND d.res_id=r.id
                            AND d.module NOT IN ('__export__','studio_customization')) ORDER BY r.model, r.id;"

section "Sociétés"
q -c "SELECT c.id, p.name, c.currency_id FROM res_company c JOIN res_partner p ON p.id = c.partner_id ORDER BY c.id;"

section "Langues actives"
q -Atc "SELECT string_agg(code, ', ' ORDER BY code) FROM res_lang WHERE active;"

section "Utilisateurs actifs (hors système)"
q -Atc "SELECT count(*) || ' utilisateurs internes actifs, ' ||
        (SELECT count(*) FROM res_users WHERE active AND share) || ' comptes portail'
        FROM res_users WHERE active AND NOT share AND id > 2;"
