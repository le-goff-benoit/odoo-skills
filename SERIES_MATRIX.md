# Matrice des séries — ce qui change d'une version d'Odoo à l'autre

> Le guide `ODOO19_STYLE_GUIDE.md` décrit la **19.0**. Ce fichier dit ce qui
> vaut sur les autres séries. Un module ne s'écrit ni ne se relit avec les
> règles d'une série qui n'est pas la sienne : `_sql_constraints` est la forme
> **correcte** en 18.0 et une **erreur** en 19.0, `models.Constraint` l'inverse.
>
> Chiffres établis par comptage direct dans `~/odoo-sources/`.

## Série cible : comment elle est déterminée

`scripts/odoo_series.py`, dans cet ordre :

1. `--series` sur la ligne de commande, ou `$ODOO_SERIES` ;
2. `.odoo-agents/config` à la racine du projet (`series = 18.0`) ;
3. le préfixe de `version` dans le `__manifest__.py` (`18.0.3.13.1` → `18.0`) ;
4. `19.0` par défaut.

**Le premier réflexe d'un agent, avant de lire ou d'écrire une ligne, est de
connaître la série du module.** Tous les scripts l'affichent en tête de sortie.

## Matrice des formes attendues

| Sujet | 17.0 | 18.0 | 19.0 | 19.4 (saas~19.4) |
|---|---|---|---|---|
| Vue liste | `<tree>` | `<list>` | `<list>` | `<list>` |
| Conditions de vue | `invisible="expr"` | idem | idem | idem |
| `attrs=` / `states=` | supprimés | supprimés | supprimés | supprimés |
| Chatter | `<div class="oe_chatter">` | `<chatter/>` | `<chatter/>` | `<chatter/>` |
| Nom affiché | `_compute_display_name` | idem | idem | idem |
| Contrainte SQL | `_sql_constraints` | `_sql_constraints` | `models.Constraint` | `models.Constraint` |
| Index | `index=` sur le champ | idem | `models.Index` / `models.UniqueIndex` | idem |
| Domaines | listes polonaises | listes | objet `Domain` | objet `Domain` |
| Commandes x2many | `Command.*` | `Command.*` | `Command.*` | `Command.*` |
| Traduction contextuelle | `_()` | `_()` / `self.env._()` | idem | idem |
| RPC lecture seule | — | `@api.readonly` | `@api.readonly` | `@api.readonly` |
| Curseur / contexte | `self._cr`, `self._context` tolérés | tolérés | `self.env.cr`, `self.env.context` | idem |
| Catégorie de groupe | `category_id` | `category_id` | `res.groups.privilege` | idem |
| Groupes d'un utilisateur | `groups_id` | `groups_id` | `group_ids` | `group_ids` |
| Utilisateurs d'un groupe | `users` | `users` | `user_ids` | `user_ids` |
| Droits d'accès | `ir.model.access.csv` | idem | idem | **`ir.access.csv`** |
| Règles d'enregistrement | `ir.rule` | `ir.rule` | `ir.rule` | **fusionnées dans `ir.access`** |
| Contrat RH | `hr.contract` | `hr.contract` | **`hr.version`** | `hr.version` |
| Éditeur HTML | `web_editor` | `web_editor` | **`html_builder`** | `html_builder` |
| Frontend public | `publicWidget` | `publicWidget` | **`Interaction`** | `Interaction` |

Preuves de datation — **nombre de fichiers d'`addons/` contenant le motif**,
relevé le 2026-09-02. Unité homogène sur toute la table, reproductible par :

```bash
cd ~/odoo-sources
grep -rl "<motif>" <série>/addons --include="*.xml" | wc -l    # motifs de vue
grep -rl "<motif>" <série>/addons --include="*.py"  | wc -l    # motifs Python
```

| Motif | 17.0 | 18.0 | 19.0 | 19.4 |
|---|---|---|---|---|
| `<tree` (`*.xml`) | 389 | 0 | 0 | 0 |
| `oe_chatter` (`*.xml`) | 71 | 1 | 0 | 0 |
| `<chatter/>` (`*.xml`) | 0 | 64 | 68 | 69 |
| `_sql_constraints` (`*.py`) | 158 | 172 | 1 | 1 |
| `models.Constraint(` (`*.py`) | 0 | 0 | 176 | 195 |
| `self.env._(` (`*.py`) | 1 | 116 | 263 | 523 |
| `security/ir.model.access.csv` | 205 | 224 | 219 | **0** |
| `security/ir.access.csv` | 0 | 0 | 0 | **223** |
| `static/src/public/interaction.js` | absent | absent | présent | présent |

La bascule des droits d'accès en 19.4 est la plus nette de la table : 219 → 0
d'un côté, 0 → 223 de l'autre. Elle est confirmée par le script de migration
officiel `19.4/odoo/upgrade_code/19.4-00-ir-access.py`.

## 19.0 n'est pas figée : les séries saas~19.x

Le poste héberge aussi `19.1` (`saas~19.1`) et `19.4` (`saas~19.4`). Elles ne
sont pas de simples correctifs : elles déplacent des règles du guide.

| Changement | Série | Effet sur un module custom |
|---|---|---|
| **`ir.access` unifie ACL et record rules** | 19.4 | `security/ir.model.access.csv` → `security/ir.access.csv`, colonnes `id,name,model_id,group_id/id,operation,domain` où `operation` est un sous-ensemble de `crud` et `domain` remplace l'`ir.rule`. 223 modules 19.4 en portent un ; plus aucun `ir.model.access.csv` dans le standard. Migration : `odoo/upgrade_code/19.4-00-ir-access.py`. |
| `registry.clear_cache` → `transaction.invalidate_ormcache` | 19.4 | tout appel de vidage de cache est à renommer. |
| `type="base64"` → `type="bytes"` dans les données XML | 19.3 | champs binaires chargés depuis un fichier. |
| Auto-fermeture des `<t>` et xpath sur `t-call` | 19.1 | templates QWeb. |
| Refonte des groupes de comptes | 19.3 | plans comptables localisés. |
| `ruff.toml` différent de celui de la 19.0 | 19.1+ | la config lint officielle a bougé. |

Conséquence pratique : **écrire « Odoo 19 » ne suffit pas.** Un module destiné à
Odoo Online / SaaS tourne sur la dernière saas~19.x, pas sur la 19.0.

## Modules supprimés

`19.0` (par rapport à 18.0) : `hr_contract`, `hr_holidays_contract`,
`hr_work_entry_contract`, `web_editor`, `membership`, `website_membership`,
`product_images`, `sale_async_emails`, `hw_*`, `pos_six`, `pos_paytm`,
`pos_viva_wallet`, `pos_epson_printer`, `auth_totp_mail_enforce`,
`payment_razorpay_oauth`, `website_jitsi`, `website_event_meet*`.

`19.4` retire encore, entre autres : `base_iban`, `hr_org_chart`, `hr_hourly_cost`,
`hr_homeworking*`, `hr_work_entry_holidays`, `iot_base`, `iot_box_image`,
`delivery_mondialrelay`, `website_sale_wishlist` et ses satellites,
`account_peppol_response`. Et en ajoute : `printer`, `populate`, `mail_tracking`,
`pos_stock`, `purchase_alternative*`, `base_report_paper_muncher`…

La liste exacte se recalcule, elle ne se mémorise pas :

```bash
comm -23 <(ls odoo-sources/19.0/addons|sort) <(ls odoo-sources/19.4/addons|sort)
```

## Ce que l'outillage fait de la série

| Script | Comportement |
|---|---|
| `odoo_lint.py` | chaque motif est daté (`since` / `before`) : `_sql_constraints` n'est une erreur qu'à partir de la 19.0, `models.Constraint` en est une avant. `--series X` force la comparaison — utile pour chiffrer une migration. |
| `odoo-lint.sh` | annonce la série, choisit le `ruff.toml` de la série (repli sur le plus proche publié). |
| `odoo-stack.sh` / `odoo-test.sh` | image `odoo-qa:<série>`, projet compose, volumes, base et sources enterprise propres à la série. Deux séries cohabitent. |
| `odoo-project-scan.py` | inscrit la série détectée dans le `PROJECT.md` du projet. |

Chiffrer une migration revient donc à comparer deux passes :

```bash
odoo-lint.sh <module>                 # dette réelle, dans sa série
odoo-lint.sh --series 19.0 <module>   # ce que coûterait la montée en 19.0
```
