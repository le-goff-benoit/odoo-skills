# Leçons — mémoire longue des agents Odoo

<!-- dernier-retex: 2026-09-02 -->

> Le `JOURNAL.md` d'un projet retient ce qui s'est passé **sur ce projet**.
> Ce fichier retient ce qui doit changer **dans la façon de travailler**, tous
> projets confondus. Il est court par construction : une leçon n'y entre que si
> elle a coûté quelque chose au moins deux fois, ou une fois très cher.

## Comment une leçon entre ici

1. Le profil QA (ou l'humain) constate un défaut évitable et l'écrit dans le
   `JOURNAL.md` du projet, ligne **Appris**.
2. À la commande `/odoo-retex`, les journaux sont relus : ce qui revient est
   promu ici.
3. Une leçon promue **doit** produire un effet outillé, sinon elle sera oubliée :
   - une ligne dans `ODOO19_STYLE_GUIDE.md` ou `SERIES_MATRIX.md`, **ou**
   - un motif dans `scripts/odoo_lint.py`, **ou**
   - une règle dans le rôle concerné (`roles/*.md`).
   La colonne « Effet » dit lequel. Une leçon sans effet est une intention.

## Ce qui entre ici, et ce qui n'y entre pas

Le tri se fait avec une seule question : **qu'est-ce qui rendrait cette phrase
fausse ?**

| Ce qui la rend fausse | Où elle va |
|---|---|
| Une nouvelle version d'Odoo | `SERIES_MATRIX.md` |
| Un changement d'hébergement | `PLATEFORMES.md` |
| Rien, sauf reprendre une mauvaise habitude | **ici** |

Autrement dit : **une leçon change un comportement, un fait de plateforme ou de
série change une référence.** Ce fichier ne vaut que parce qu'il est court. Un
fait exact mais documentaire le dilue et le rend illisible — il va dans la
référence correspondante, où on le retrouvera au moment utile, pas dans la
mémoire longue.

Les deux axes ne sont pas indépendants : Odoo Online impose sa série. Quand une
entrée touche aux deux, elle vit dans `PLATEFORMES.md` et renvoie à
`SERIES_MATRIX.md` plutôt que de la recopier.

## Format

```markdown
### L<n> — <titre court>
**Portée** : universelle | série ≥ X | hébergement <lequel>
**Constat** : ce qui s'est réellement passé, avec le projet et la date.
**Cause** : pourquoi l'agent s'est trompé (information manquante, règle fausse,
raccourci).
**Règle** : ce qu'on fait désormais, en une phrase impérative.
**Effet** : guide § X / motif `odoo_lint.py` / rôle `<profil>` — ce qui a été modifié.
```

`Portée` se lit avant tout le reste : elle dit à un agent s'il doit continuer à
lire. Une leçon `universelle` s'applique toujours ; les autres ne valent que dans
leur contexte, et ailleurs elles font perdre du temps ou induisent en erreur.

---

### L1 — La série d'un module n'est jamais supposée, elle est lue
**Portée** : universelle
**Constat** : 2026-09-01, revue de l'outillage. Tout le dispositif était calé sur
la 19.0 alors que le module principal du poste (`alamaison_customisation`) est en
18.0, comme la majorité du parc. Le lint produisait 4 fausses erreurs sur du code
18.0 parfaitement correct (`_sql_constraints`, dépendance `hr_contract`, deux
dépendances enterprise cherchées dans les sources 19.0), et la doctrine de
développement poussait des formes 19.0 (`models.Constraint`, `Domain`,
`res.groups.privilege`) qui font planter un module 18.0 à l'installation.
**Cause** : une série de référence confondue avec la série cible du projet.
**Règle** : avant de lire ou d'écrire une ligne, établir la série cible du module
et n'appliquer que les règles de cette série.
**Effet** : `scripts/odoo_series.py` (résolution), motifs datés dans
`odoo_lint.py`, `SERIES_MATRIX.md`, série annoncée en tête de chaque script,
stack Docker par série.

### L2 — « Odoo 19 » ne désigne pas une seule version
**Portée** : hébergement Odoo Online / SaaS — voir `PLATEFORMES.md`
**Constat** : 2026-09-01. Les séries `saas~19.1` et `saas~19.4` sont sur le poste
et déplacent des règles réputées stables : en 19.4, `ir.model.access.csv` n'existe
plus dans le standard (223 modules portent un `ir.access.csv`) et les `ir.rule`
sont fusionnées dans le modèle `ir.access`. Le guide énonçait comme « erreur
bloquante » l'absence de ligne dans `ir.model.access.csv` — faux à partir de 19.4.
**Cause** : une photographie de la 19.0 prise pour une vérité durable.
**Règle** : pour un projet Odoo Online / SaaS, viser la dernière `saas~19.x`, pas
la 19.0 ; vérifier la forme de la sécurité dans les sources de **la** série visée.
**Effet** : `SERIES_MATRIX.md` § saas~19.x, contrôle sécurité daté dans
`odoo_lint.py` (`ir_access_csv`).

### L3 — Un contrôle qui se trompe de série est pire que pas de contrôle
**Portée** : universelle
**Constat** : 2026-09-01. Sur `alamaison_customisation`, 3 des 24 erreurs remontées
étaient fausses. Une erreur fausse fait perdre la confiance dans les 21 vraies.
**Cause** : motifs de lint non datés.
**Règle** : tout motif ajouté à `odoo_lint.py` porte sa portée (`since` / `before`)
et est vérifié par comptage dans les sources des deux séries concernées avant
d'être considéré comme vrai.
**Effet** : structure `(regex, sévérité, message, portée)` dans `odoo_lint.py`.

### L4 — Une option qui n'existe pas est ignorée sans erreur
**Portée** : universelle
**Constat** : 2026-09-02, relecture du projet `latitude_cartagane` (intervention de
décembre 2025). Pour réparer des chemins de pièces jointes, la séquence
`UPDATE ir_attachment SET store_fname = NULL` puis
`odoo -d <db> --stop-after-init --recompute-filestore` a été jouée.
`--recompute-filestore` n'existe pas. Odoo l'a ignorée sans broncher, la commande
s'est terminée normalement — et **27 000 pièces jointes sur 27 602** sont restées
sans pointeur de stockage. La base s'ouvrait, tous les documents étaient
invisibles. Découvert neuf mois plus tard, au moment de livrer.
**Cause** : une option inventée de mémoire, et un `UPDATE` destructif joué
**avant** d'avoir prouvé que la réparation fonctionnait. L'absence d'erreur a été
prise pour un succès.
**Règle** : vérifier toute option Odoo dans les sources de la série avant de la
lancer, et ne jamais détruire avant d'avoir prouvé que la réparation marche.
**Effet** : `roles/implementation.md` § Interdits (deux entrées : option non
vérifiée, ordre destruction/réparation) ; recette de rattrapage dans
`PLATEFORMES.md` § Reprise de données. Même famille, 2026-09-04 : `odoo -i
<module>` sur un module absent du chemin des addons écrit un `WARNING invalid
module names, ignored` et sort en 0 — `odoo-test.sh` affichait « installation
OK » sur du vide ; il traite désormais ce warning comme un échec.

### L5 — Reproduire dans l'outil du système cible, jamais dans le sien
**Portée** : universelle
**Constat** : 2026-09-02, `latitude_cartagane`. Le diagnostic « les modes du zip
cassent le filestore Odoo.sh » était exact et étayé par une preuve prise sur
l'instance. Il a été rétracté après un test montrant que `zipfile.extractall()`
de Python ignore les permissions des répertoires — vrai en Python, mais Odoo.sh
n'extrait pas avec Python. La rétractation a coûté un import inutile et deux
échanges de confusion au client. C'est l'horodatage `Jan  1  1980` du répertoire
distant, impossible ailleurs que dans un zip, qui a rétabli le diagnostic.
**Cause** : un test de réfutation mené dans l'environnement de l'agent au lieu de
celui du système cible, et jugé plus fiable qu'une preuve relevée sur le système.
**Règle** : reproduire avec l'outil du système cible ; quand un test contredit une
preuve prise sur ce système, suspecter le test avant de se rétracter.
**Effet** : `roles/qa-review.md` § Règles de conduite (deux entrées : outil de
reproduction, non-rétractation sur test indirect).

### L6 — Un relevé qui avale les sources vendorisées fabrique de la dette imaginaire
**Portée** : universelle
**Constat** : 2026-09-02, `latitude_cartagane`. `odoo_project_scan.py` a recensé
**379 « modules custom »** qui étaient en réalité la copie d'Odoo Enterprise 15.0
embarquée dans le projet, et leur a attribué de la dette en les lintant avec la
série du projet (19.0) : 8 erreurs sur `account_3way_match`, module officiel
Odoo. Fiche projet de 198 Ko, fausse et illisible, là où le projet ne contient
aucun module custom.
**Cause** : la découverte par `rglob("__manifest__.py")` ne distinguait pas le
code dont le projet est responsable des sources de référence qu'il embarque.
C'est la L3 rejouée par un autre outil — un contrôle qui se trompe de périmètre
plutôt que de série.
**Règle** : un relevé ne recense que le code dont le projet est responsable ;
toute copie de sources Odoo en est écartée, et le nombre d'écartés est annoncé
pour que l'omission reste visible.
**Effet** : `scripts/odoo_project_scan.py` — `VENDOR_DIRS` + détection d'un
`odoo/release.py` dans un sous-arbre, comptage des écartés sur stderr. Vérifié :
`latitude_cartagane` 379 → 0 modules (198 Ko → 1,5 Ko), `alamaison_smartcamp` et
`forpro-poc-19` inchangés à 1 module.
