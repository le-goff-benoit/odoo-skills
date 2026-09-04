# Ligne éditoriale Odoo 19.0 — guide de référence

> Extrait par analyse directe des sources `~/odoo-sources/19.0`
> (`release.py` → `version_info = (19, 0, 0, FINAL, 0, '')`, 625 addons community)
> et comparaison 18.0 → 19.0. **C'est la source de vérité : en cas de doute, on relit
> le code d'Odoo, pas la documentation ni la mémoire.**
>
> ⚠️ **Ce guide décrit la 19.0, et elle seule.** Le parc de modules du poste est
> majoritairement en **18.0**, et les séries `saas~19.1` / `saas~19.4` déplacent
> certaines règles énoncées ici — dont la sécurité, refondue en 19.4. Avant
> d'appliquer une règle de ce guide, vérifier la série du module et consulter
> **[`SERIES_MATRIX.md`](SERIES_MATRIX.md)**, qui fait foi en cas de contradiction :
>
> ```bash
> python3 ~/.odoo19-agents/scripts/odoo_series.py <chemin_du_module>
> ```

Sources de référence disponibles en local :

| Chemin | Contenu |
|---|---|
| `~/odoo-sources/19.0` | Community 19.0 (`odoo/` core + `addons/`) |
| `~/odoo-sources/19.0-enterprise` | Enterprise 19.0 (772 addons) |
| `~/odoo-sources/18.0`, `17.0`, `14.0` | Versions antérieures (pour diff / migration) |
| `~/odoo-sources/19.0/ruff.toml` | Configuration lint **officielle** d'Odoo |
| `~/odoo-sources/19.0/odoo/upgrade_code/` | Scripts de migration automatiques (documentent les renommages) |

---

## 1. Réflexe n°1 : chercher le précédent dans les sources

Avant d'écrire une ligne, on trouve **le même problème déjà résolu dans un addon standard**
et on copie la forme. Commandes types :

```bash
S=~/odoo-sources/19.0
grep -rn "_inherit = \['mail.thread'" $S/addons/*/models/*.py | head
grep -rn "widget=\"monetary\"" $S/addons/sale/views/*.xml | head
grep -rln "models.Constraint(" $S/addons/*/models/*.py | head
comm -23 <(ls $S/../18.0/addons|sort) <(ls $S/addons|sort)   # modules disparus en 19
```

Modules à imiter selon le domaine : `sale`, `account`, `stock`, `project`, `hr`,
`mail` (mixins), `base` (ORM). Ce sont les plus tenus.

---

## 2. Structure d'un module

```
mon_module/
├── __init__.py                  # from . import models, wizard, controllers ...
├── __manifest__.py
├── controllers/
├── data/                        # <odoo> ou <odoo noupdate="1">
├── demo/
├── i18n/                        # .pot + .po
├── models/
│   ├── __init__.py
│   └── <nom_du_modele_avec_underscores>.py   # 1 fichier = 1 modèle
├── report/                      # modèles QWeb + ir.actions.report + modèles SQL de reporting
├── security/
│   ├── ir.model.access.csv
│   ├── <module>_security.xml    # res.groups.privilege + res.groups
│   └── ir_rules.xml             # ir.rule
├── static/
│   ├── description/icon.png
│   ├── src/{js,scss,xml}/
│   └── tests/                   # *.test.js (hoot) + tours/
├── tests/
│   ├── __init__.py
│   ├── common.py                # classe <Module>Common
│   └── test_*.py
├── views/
│   ├── <modele>_views.xml
│   └── <module>_menus.xml       # en DERNIER dans le manifest
└── wizard/                      # models.TransientModel + vues
```

Règles de nommage :

- Fichier modèle = nom du modèle avec `_` : `sale.order.line` → `models/sale_order_line.py`.
- Vues : `<modele>_views.xml`. Templates portail : `<module>_portal_templates.xml`.
- Menus : toujours dans un fichier séparé, chargé **en dernier** (il référence les actions).
- XML IDs : `view_<modele>_<type>` ou `<modele>_view_<type>`, `action_<...>`,
  `menu_<...>`, `group_<...>`, `<modele>_comp_rule` pour les règles multi-société.

### `__manifest__.py`

Toujours ouvert par la ligne de licence, dict littéral, clés dans cet ordre :

```python
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "Nom lisible",
    'version': '19.0.1.0.0',      # <série odoo>.<major>.<minor>.<patch>  pour un custom
    'category': 'Sales/Sales',
    'summary': "Une ligne",
    'description': """ ... """,   # ou README.md
    'depends': ['base'],
    'data': [
        'security/...',           # sécurité d'abord
        'report/...',
        'data/...',
        'wizard/...',
        'views/...',
        'views/..._menus.xml',    # menus en dernier
    ],
    'demo': [],
    'installable': True,
    'assets': {
        'web.assets_backend': ['mon_module/static/src/**/*'],
        'web.assets_frontend': [],
        'web.assets_tests': ['mon_module/static/tests/tours/**/*'],
        'web.assets_unit_tests': ['mon_module/static/tests/**/*.test.js'],
    },
    'author': "…",
    'license': 'LGPL-3',
}
```

Clés **obligatoires** (aucune valeur par défaut) : `name`, `author`, `license`.
Liste complète des clés valides : `odoo/modules/module.py` → `_DEFAULT_MANIFEST`.
Hooks disponibles : `pre_init_hook`, `post_init_hook`, `uninstall_hook`, `post_load`.

---

## 3. Python — la forme canonique

### En-tête et imports

```python
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import logging
from collections import defaultdict
from datetime import timedelta

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command, Domain
from odoo.tools import SQL, float_is_zero, format_amount

from odoo.addons.payment import utils as payment_utils
```

Ordre isort imposé (`ruff.toml`) : `future` → `stdlib` → `third-party` →
`first-party` (`odoo`) → `local-folder` (`odoo.addons`), séparés par une ligne vide.
**Une ligne vide entre le bloc `odoo` et le bloc `odoo.addons`.**

### Squelette de modèle

```python
class SaleOrder(models.Model):
    _name = 'sale.order'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']
    _description = "Sales Order"
    _order = 'date_order desc, id desc'
    _check_company_auto = True

    _date_order_conditional_required = models.Constraint(
        "CHECK((state = 'sale' AND date_order IS NOT NULL) OR state != 'sale')",
        "A confirmed sales order requires a confirmation date.",
    )

    #=== FIELDS ===#
    #=== COMPUTE METHODS ===#
    #=== CONSTRAINT METHODS ===#
    #=== ONCHANGE METHODS ===#
    #=== CRUD METHODS ===#
    #=== ACTION METHODS ===#
    #=== BUSINESS METHODS ===#
```

Le nom de classe est le nom du modèle en CamelCase, sans préfixe module.
`_description` est **obligatoire** sur tout nouveau modèle.

Marqueurs de section réellement utilisés dans 19.0 (fréquence décroissante) :
`#=== COMPUTE METHODS ===#`, `BUSINESS METHODS`, `CRUD METHODS`, `ACTION METHODS`,
`CONSTRAINT METHODS`, `ONCHANGE METHODS`, `FIELDS`, `TOOLING`, `DEFAULT METHODS`,
`HOOKS`, `CORE METHODS OVERRIDES`, `SELECTION METHODS`.
Format exact : `    #=== NOM ===#` (4 espaces, pas d'espace après `#`).

**Ordre imposé des membres** (guideline officielle, confirmée par les sources) :

1. attributs privés (`_name`, `_inherit`, `_description`, `_order`, `_rec_name`,
   `_check_company_auto`, `_inherits`)
2. objets de table déclaratifs (`models.Constraint`, `models.Index`, `models.UniqueIndex`)
3. `@property` (ex. `_rec_names_search` dynamique)
4. méthodes de défaut (`_default_*`) et `_selection_*`
5. déclarations de champs
6. compute / inverse / search
7. `@api.constrains` puis `@api.onchange`
8. CRUD (`create`, `write`, `unlink`, `copy_data`, `@api.ondelete`)
9. méthodes d'action (`action_*`)
10. méthodes métier

### Champs

```python
    name = fields.Char(
        string="Order Reference",
        required=True, copy=False, readonly=False,
        index='trigram',
        default=lambda self: _("New"))

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string="Customer",
        required=True, index=True,
        tracking=1,
        check_company=True)

    require_signature = fields.Boolean(
        string="Online signature",
        compute='_compute_require_signature',
        store=True, readonly=False, precompute=True,
        help="Request a online signature from the customer to confirm the order.")
```

- Suffixes obligatoires : `_id` (Many2one), `_ids` (One2many/Many2many).
  Un `Date`/`Datetime` se nomme `date_*` ou `*_date`.
- `comodel_name=` explicite en keyword pour les relationnels.
- `string=` en **double quotes**, omis si le libellé se déduit du nom du champ.
- Champ *stored computed editable* : `compute=` + `store=True` + `readonly=False`
  (+ `precompute=True` si calculable à la création). C'est le remplaçant idiomatique
  de l'`onchange` depuis la 16 — **préférer ça à `@api.onchange`**.
- `help=` en phrase complète ponctuée ; `string=` sans point final.
- `groups=` sur le champ pour restreindre par droit.

### Contraintes — la 19 est déclarative

`_sql_constraints` est **mort** (1 seule occurrence résiduelle dans tout 19.0).
On écrit :

```python
    _name_uniq = models.Constraint(
        'UNIQUE(name, company_id)',
        "The name must be unique per company.",
    )
    _partner_index = models.Index("(partner_id) WHERE state = 'sale'")
    _code_unique = models.UniqueIndex("(code)")
```

Définition : `odoo/orm/table_objects.py`. 243 `models.Constraint`, 53 `models.Index`,
29 `models.UniqueIndex` dans 19.0.

Contraintes Python :

```python
    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for record in self:
            if record.date_end < record.date_start:
                raise ValidationError(_("End date must be after start date."))
```

### Compute / CRUD

```python
    @api.depends('order_line.product_id')
    def _compute_has_archived_products(self):
        for order in self:
            order.has_archived_products = any(
                not product.active for product in order.order_line.product_id
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            ...
        return super().create(vals_list)

    def write(self, vals):
        ...
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_confirmed(self):
        if any(o.state != 'draft' for o in self):
            raise UserError(_("You can not delete a confirmed order."))

    def copy_data(self, default=None):
        default = dict(default or {})
        vals_list = super().copy_data(default=default)
        ...
        return vals_list
```

- **Toujours** `super()` nu, jamais `super(MaClasse, self)`.
- `create` est **toujours** `@api.model_create_multi(vals_list)`.
- Suppression : `@api.ondelete` plutôt qu'un override de `unlink`.
- Une méthode compute itère **toujours** sur `self` et assigne **tous** les
  enregistrements de `self` sur **tous** les chemins.
- `@api.readonly` sur les méthodes appelées par le web qui ne modifient rien
  (nouveau en 19, évite un curseur en écriture) : `odoo/orm/decorators.py:341`.
- Décorateurs disponibles (`odoo/api/__init__.py`) : `autovacuum`, `constrains`,
  `depends`, `depends_context`, `deprecated`, `model`, `model_create_multi`,
  `onchange`, `ondelete`, `private`, `readonly`.

### Traductions

```python
raise UserError(_("You cannot change the pricelist of a confirmed order!"))
order.note = _("Terms & Conditions: %s", baseurl)     # placeholders en args, PAS de %  ni f-string
```

`_()` reste majoritaire (5146 occurrences) mais `self.env._()` progresse (758) : il
utilise la langue de l'environnement courant plutôt que celle de l'utilisateur.
**Dans une méthode qui rend du contenu pour un tiers (mail, portail, rapport),
utiliser `self.env._()` ou `with_context(lang=partner.lang)`.**
Jamais de f-string ni de concaténation dans `_()`.

### Domaines — nouveauté 19

`Domain` est un objet composable (`odoo/orm/domains.py`), importé depuis `odoo.fields` :

```python
from odoo.fields import Domain

domain = Domain('is_downpayment', '=', False)
domain &= Domain('product_id', 'not in', ids)
domain = Domain.AND([d1, d2])       # / Domain.OR([...]) / Domain.TRUE / Domain.FALSE
return super()._get_product_catalog_domain() & Domain('sale_ok', '=', True)
```

Préférer `Domain` à la manipulation de listes polonaises `['&', ...]` dans tout code
nouveau. Les listes restent acceptées partout (compatibilité).

### Commandes x2many

```python
from odoo.fields import Command

'order_line': [Command.create({...}), Command.clear(), Command.set(ids),
               Command.link(id), Command.unlink(id), Command.delete(id),
               Command.update(id, {...})]
```

Jamais les tuples `(0, 0, {...})` dans du code neuf.

### Erreurs, logs, perfs

- `UserError` = erreur métier attendue ; `ValidationError` = contrainte ;
  `AccessError` = droits. Jamais `Exception` nue (ruff `BLE`).
- `_logger = logging.getLogger(__name__)` en tête de module ; `_logger.info("x %s", y)`
  — jamais de f-string dans un log (ruff `G`).
- Jamais de `print` (ruff `T`).
- Pas de requête ni de `search`/`browse` dans une boucle : pré-charger via
  `mapped()`, `grouped()`, `read_group`/`_read_group`, ou un `defaultdict`.
- `self.env.cr.execute` uniquement en dernier recours et **toujours** avec
  `odoo.tools.SQL` pour l'interpolation, jamais de `%` sur la chaîne.

---

## 4. XML — vues et données

### Enveloppe

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_order_form" model="ir.ui.view">
        <field name="name">sale.order.form</field>
        <field name="model">sale.order</field>
        <field name="inherit_id" ref="sale.view_order_form"/>
        <field name="arch" type="xml">
            ...
        </field>
    </record>
</odoo>
```

`<odoo noupdate="1">` pour les données que l'utilisateur peut modifier
(règles, séquences, paramètres) ; sans `noupdate` pour tout ce qui doit être
remis à jour à chaque upgrade (vues, actions, menus, templates).

### Règles de syntaxe 19

| Interdit (≤16) | Attendu en 19 |
|---|---|
| `<tree>` | `<list>` |
| `attrs="{'invisible': [...]}"` | `invisible="state != 'draft'"` (expression Python) |
| `states="draft,sent"` | `invisible="state not in ('draft', 'sent')"` |
| `<div class="oe_chatter">…` | `<chatter/>` |
| `name_get()` | `_compute_display_name()` |
| `view_mode="tree,form"` | `view_mode="list,form"` |
| `<page>`/`<group>` bruts dans settings | `<block>` / `<setting>` |

Conditions dans les vues : expression Python évaluée sur l'enregistrement, opérateurs
`not`, `in`, `and`, `or`. Sur une `<list>`, masquer une colonne entière =
`column_invisible="True"`.

### Vue liste

```xml
<list class="o_sale_order" string="Sales Orders" sample="1"
      decoration-muted="state == 'cancel'">
    <header>
        <button string="Create Invoices" name="%(action_x)d" type="action" class="btn-secondary"/>
    </header>
    <field name="currency_id" column_invisible="True"/>
    <field name="name" string="Number" readonly="1" decoration-bf="1"/>
    <field name="amount_total" widget="monetary" optional="show"/>
</list>
```

### Vue formulaire

```xml
<form string="…" class="o_sale_order">
    <header>
        <button string="Confirm" name="action_confirm" type="object"
                class="btn-primary" data-hotkey="q" invisible="state != 'draft'"/>
        <field name="state" widget="statusbar" statusbar_visible="draft,sale"/>
    </header>
    <sheet>
        <div class="oe_button_box" name="button_box">…</div>
        <widget name="web_ribbon" title="Archived" bg_color="text-bg-danger" invisible="active"/>
        <div class="oe_title">
            <h1><field name="name" readonly="1"/></h1>
        </div>
        <group>
            <group name="order_details">…</group>
            <group name="dates">…</group>
        </group>
        <notebook>
            <page string="Order Lines" name="order_lines">…</page>
        </notebook>
    </sheet>
    <chatter/>
</form>
```

Boutons `<header>` : `data-hotkey` sur les actions principales, `confirm="…"` sur les
actions destructives, `groups="…"` pour la restriction.

### Héritage

```xml
<record id="view_order_form_inherit_x" model="ir.ui.view">
    <field name="name">sale.order.form.inherit.x</field>
    <field name="model">sale.order</field>
    <field name="inherit_id" ref="sale.view_order_form"/>
    <field name="arch" type="xml">
        <field name="partner_id" position="after">
            <field name="x_new_field"/>
        </field>
        <xpath expr="//page[@name='order_lines']" position="inside">…</xpath>
        <list position="attributes">
            <attribute name="decoration-danger">is_late</attribute>
        </list>
    </field>
</record>
```

Ancrer sur un `name=` ou un `id=` existant. `<xpath>` uniquement quand aucun ancrage
nommé n'existe, et le plus court possible. Jamais un xpath positionnel (`div[3]`).

---

## 5. Sécurité

### `res.groups` — modèle 19

La catégorisation passe par **`res.groups.privilege`** (nouveau en 19) :

```xml
<record id="res_groups_privilege_sales" model="res.groups.privilege">
    <field name="name">Sales</field>
    <field name="sequence">1</field>
    <field name="category_id" ref="base.module_category_sales"/>
</record>

<record id="group_sale_salesman" model="res.groups">
    <field name="name">User: Own Documents Only</field>
    <field name="privilege_id" ref="res_groups_privilege_sales"/>
    <field name="implied_ids" eval="[(4, ref('base.group_user'))]"/>
    <field name="comment">the user will have access to his own data.</field>
</record>
```

⚠️ Renommages 19 : `res.groups.users` → **`user_ids`**, `res.users.groups_id` → **`group_ids`**
(+ `all_group_ids` calculé, incluant les groupes impliqués).

### `ir.model.access.csv`

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_my_model_user,my.model user,model_my_model,base.group_user,1,1,1,0
```

Une ligne par couple modèle × groupe. `id` en snake_case préfixé `access_`.
**Tout modèle non transient sans ligne d'accès est une erreur bloquante.**

⚠️ **À partir de la saas~19.4**, `ir.model.access.csv` n'existe plus dans le
standard : droits d'accès et règles d'enregistrement sont fusionnés dans le modèle
`ir.access` (`odoo/addons/base/models/ir_access.py`), déclaré en
`security/ir.access.csv` :

```csv
id,name,model_id,group_id/id,operation,domain
access_my_model_user,my.model user,my.model,base.group_user,cru,
```

`operation` est un sous-ensemble de `crud`, et la colonne `domain` remplace
l'`ir.rule`. Migration officielle : `odoo/upgrade_code/19.4-00-ir-access.py`.

### `ir.rule`

```xml
<record id="my_model_comp_rule" model="ir.rule">
    <field name="name">My Model multi-company</field>
    <field name="model_id" ref="model_my_model"/>
    <field name="domain_force">[('company_id', 'in', company_ids)]</field>
</record>
```

Multi-société : toujours `[('company_id', 'in', company_ids)]`, jamais `company_id`.
Fichier dans `<odoo noupdate="1">`.

---

## 6. JavaScript / OWL

ES modules, imports absolus par alias `@module/...` :

```js
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";
```

- Indentation 4 espaces, double quotes, point-virgules.
- Un composant = un dossier `static/src/<snake_case>/` avec `.js` + `.xml` (+ `.scss`).
- Templates OWL : `<t t-name="module.ComponentName">`, `static.template = "..."`.
- Extension de code standard : `patch(Class.prototype, { ... })` depuis `@web/core/utils/patch`.
- Frontend public : **`Interaction`** (`@web/public/interaction`) avec
  `static selector`, `dynamicContent`, `setup()` — remplace `publicWidget`.
- Enregistrement : `registry.category("fields"|"services"|"actions"|"views"|"web_tour.tours").add(...)`.
- Traductions JS : `_t("…")`.

### Assets

Bundles : `web.assets_backend`, `web.assets_frontend`, `web.assets_tests` (tours),
`web.assets_unit_tests` (hoot), `web.report_assets_common`.
Globs `module/static/src/**/*` privilégiés aux listes de fichiers.

---

## 7. Tests

### Python

```python
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import Form, HttpCase, tagged

from odoo.addons.sale.tests.common import SaleCommon


@tagged('post_install', '-at_install')
class TestMyFeature(SaleCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': "Partner"})

    def test_something(self):
        order = self._create_so()
        order.action_confirm()
        self.assertEqual(order.state, 'sale')

        with self.assertRaises(UserError):
            order.write({'pricelist_id': other.id})
```

- Un `tests/common.py` par module avec une classe `<Module>Common` héritant des
  `Common` des modules dépendants (`ProductCommon`, `SaleCommon`, `MailCommon`,
  `AccountTestInvoicingCommon`) ; les données partagées sont créées en `setUpClass`.
- `TransactionCase` par défaut, `HttpCase` pour les tours, `Form` pour tester les onchange.
- Tags : `@tagged('post_install', '-at_install')` pour tout ce qui a besoin du
  registre complet (le standard pour le code métier).
- Helpers : `cls.quick_ref('xml.id')`, `new_test_user(env, login=…, groups=…)`,
  `RecordCapturer`, décorateurs `@users('login')`, `@warmup`, `freeze_time`.
- Un test = un comportement, nom `test_<ce_qui_est_vérifié>`, assertions explicites.

### JS unitaires (hoot)

`static/tests/*.test.js`, bundle `web.assets_unit_tests` :

```js
import { expect, test } from "@odoo/hoot";
import { defineModels, models, fields, onRpc, contains } from "@web/../tests/web_test_helpers";
```

### Tours (e2e)

`static/tests/tours/*.js`, bundle `web.assets_tests` :

```js
import { registry } from "@web/core/registry";
import { stepUtils } from "@web_tour/tour_utils";

registry.category("web_tour.tours").add("my_tour", {
    url: "/odoo",
    steps: () => [
        { content: "…", trigger: "…", run: "click" },
    ],
});
```

Déclenché côté Python par `self.start_tour("/odoo", "my_tour", login="admin")`
dans un `HttpCase` — nécessite un binaire `chromium`/`google-chrome` dans le conteneur.

---

## 8. Lint — configuration officielle

`ruff` avec **le `ruff.toml` d'Odoo** (`~/odoo-sources/19.0/ruff.toml`,
target `py310`, `preview = true`). Familles sélectionnées : `BLE C COM E EM EXE F FA
FLY G I ICN INT ISC LOG PGH PIE PLC PLE PLW PYI RET RUF SIM SLOT T TC TID TRY UP W YTT`.
Notablement **ignorées** : `E501` (longueur de ligne), `C901`, `TRY003`, `SIM108`,
`RUF012`, `TID252`. `F401` toléré dans les `__init__.py`.

Conséquences pratiques : pas de `print`, pas de `except:` nu, pas de f-string dans
les logs, virgules finales obligatoires sur les littéraux multi-lignes, imports triés.

---

## 9. Ce qui a changé en 19.0 (checklist anti-régression)

### Core réorganisé

- `odoo/fields.py` → package `odoo/fields/` (ré-exporte `odoo.orm.fields_*`).
- `odoo/models.py` → package `odoo/models/`; `odoo/api.py` → `odoo/api/`.
- Nouveau package **`odoo/orm/`** : `domains.py`, `commands.py`, `decorators.py`,
  `table_objects.py`, `fields_*.py`, `model_classes.py`, `registry.py`.
- Il n'y a plus de `odoo/__init__.py` : l'initialisation est dans `odoo/init.py`.
- Import public inchangé : `from odoo import api, fields, models, _`.

### API

- `Domain` composable (`from odoo.fields import Domain`).
- `models.Constraint` / `models.Index` / `models.UniqueIndex` remplacent `_sql_constraints`.
- `@api.readonly` pour les appels RPC en lecture seule.
- `self.env._()` à côté de `_()`.
- `self._cr` / `self._uid` / `self._context` → `self.env.cr` / `self.env.uid` / `self.env.context`
  (cf. `odoo/upgrade_code/18.5-00-deprecated-properties.py`).

### Renommages de champs à connaître

| 18.0 | 19.0 |
|---|---|
| `res.users.groups_id` | `res.users.group_ids` |
| `res.groups.users` | `res.groups.user_ids` |
| `res.groups.category_id` | `res.groups.privilege_id` → `res.groups.privilege` |
| `sale.order.line.product_uom` | `product_uom_id` |

### Après la 19.0 : les séries saas~19.x

La 19.0 n'est pas le dernier état d'Odoo 19. Les séries `saas~19.1` et `saas~19.4`
présentes sur le poste changent des règles de ce guide : sécurité unifiée dans
`ir.access` (19.4), `registry.clear_cache` → `transaction.invalidate_ormcache`
(19.4), `type="base64"` → `type="bytes"` dans les données XML (19.3), `ruff.toml`
différent (19.1+). Détail et datation : [`SERIES_MATRIX.md`](SERIES_MATRIX.md).

### Modules supprimés / fusionnés (community)

Disparus en 19.0 : `hr_contract`, `hr_holidays_contract`, `hr_work_entry_contract`,
`test_hr_contract_calendar`, `web_editor`, `membership`, `website_membership`,
`product_images`, `sale_async_emails`, `hw_drivers`, `hw_escpos`,
`hw_posbox_homepage`, `pos_six`, `pos_paytm`, `pos_viva_wallet`,
`pos_epson_printer`, `pos_self_order_epson_printer`, `auth_totp_mail_enforce`,
`payment_razorpay_oauth`, plusieurs `l10n_*`.

Nouveaux : `html_builder` (remplace `web_editor`), `iot_base` / `iot_drivers` /
`iot_box_image`, `rpc`, `api_doc`, `partnership`, `auth_timeout`,
`auth_passkey_portal`, `google_address_autocomplete`, `stock_maintenance`,
`website_timesheet`, `pos_repair`, nombreux `payment_*` / `pos_*`.

### ⚠️ Refonte RH majeure

**`hr.contract` n'existe plus.** Le contrat est absorbé par le versionnage employé :
modèle **`hr.version`** (`addons/hr/models/hr_version.py`), avec
`hr.contract.type` conservé. Tout module custom qui dépend de `hr_contract` ou
manipule `hr.contract` doit être repensé sur `hr.version`.

---

## 10. Commits, versions et releases

Un commit Odoo se lit sans ouvrir le diff. Convention d'Odoo S.A.
(`git log --oneline -300` sur `~/odoo-sources/19.0` : 299 messages sur 300) :

```
[TAG] module: sujet à l'impératif, sans point final

Corps : le pourquoi, ce que l'utilisateur observait, ce qui change. Référence
au ticket ou à la release (`changelog/2026-09-04_01_…`).
```

| Tag | Quand |
|---|---|
| `[FIX]` | correctif de bug |
| `[IMP]` | amélioration d'une fonction existante |
| `[ADD]` | nouvelle fonction, nouveau module |
| `[REM]` | suppression |
| `[REF]` | refactorisation sans changement fonctionnel |
| `[MOV]` | déplacement de code ou de fichiers |
| `[REL]` | livraison, incrément de version |
| `[I18N]` | traductions |
| `[PERF]` | performance |
| `[CLA]` | accord de contribution |

Plusieurs modules : `[FIX] sale, stock: …`. Un commit par release est la norme de
livraison ; le corps liste les points livrés, dans les mots du README de la release.

**Version du manifest** : `<série>.<majeure>.<mineure>.<correctif>`, incrémentée
**une fois par release, à la clôture**, sur la composante convenue avec le projet,
lue dans le fichier — jamais mémorisée. Tout champ stocké ajouté rend
l'incrément obligatoire : Odoo.sh déploie le code sans mettre le module à jour
si `version` n'a pas bougé, la colonne n'est jamais créée, et l'écran casse en
production sur `column … does not exist`. Une modification purement
documentaire ne change pas la version. La version livrée est celle qui a été
testée : incrémenter après la recette impose de la rejouer.

**Release de changelog** (`changelog/AAAA-MM-JJ_NN_titre/`) : `demande.md` (les
demandes telles quelles), `revue_fonctionnelle.md`, `qa.md`, `recette.md`,
`tests_navigateur.md`, `README.md` (suivi vivant tant que la release est ouverte,
forme finale à la clôture), `captures/`, guide et communication quand un écran
change. Outillage : `scripts/odoo-release.sh`, `/odoo-new`, `/odoo-close`.

---

## 11. Anti-patterns rejetés en revue

1. `<tree>`, `attrs=`, `states=` dans une vue.
2. `_sql_constraints` au lieu de `models.Constraint`.
3. `super(MaClasse, self).method()`.
4. `create(self, vals)` sans `@api.model_create_multi`.
5. Un compute qui ne renseigne pas tous les enregistrements sur toutes les branches.
6. `search()` / `browse()` / `write()` dans une boucle `for`.
7. SQL brut évitable, ou construit par concaténation de chaînes.
8. `@api.onchange` là où un compute `store=True, readonly=False` suffit.
9. f-string dans `_()` ou dans un `_logger`.
10. Modèle sans `_description`, sans ligne dans `ir.model.access.csv`,
    ou sans règle multi-société alors qu'il porte un `company_id`.
11. `sudo()` posé pour contourner un problème de droits sans justification écrite.
12. Champ Many2one sans suffixe `_id`, ou fichier modèle mal nommé.
13. Menus/actions chargés avant les vues qu'ils référencent dans le manifest.
14. Dépendance à un module supprimé en 19 (`hr_contract`, `web_editor`, …).
15. XPath positionnel ou fragile dans un héritage de vue.
16. Champ stocké ajouté sans incrément de version du manifest.
17. Message de commit sans `[TAG] module:`, ou version incrémentée après la recette.
