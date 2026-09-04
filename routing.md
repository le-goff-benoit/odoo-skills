Sources Odoo en lecture seule : `~/odoo-sources/{14.0,17.0,18.0,19.0,19.1,19.4}`
(+ `-enterprise`). Ne jamais y écrire : tout code va dans le module custom du projet.

Référentiel `~/.odoo19-agents/` : `ODOO19_STYLE_GUIDE.md` (ligne éditoriale,
décrit la **19.0**), `SERIES_MATRIX.md` (ce qui change par série, **fait foi**
sur le guide), `PLATEFORMES.md` (Odoo.sh / Online / on-premise / Docker, fait
foi sur déploiement et restauration), `LESSONS.md` (les erreurs déjà payées).

## La série d'abord, le briefing ensuite

Le parc est mélangé (17.0, 18.0, 19.0, saas~19.1, saas~19.4). Écrire du 19.0
dans un module 18.0 le casse ; le relire avec les règles 19.0 remonte des
anomalies fausses. **Avant toute lecture ou écriture de code Odoo**, une commande :

```bash
python3 ~/.odoo19-agents/scripts/odoo_briefing.py <module_ou_projet>
```

Elle donne la série (de `.odoo-agents/config`, sinon du manifest) et tout ce
que le projet sait déjà : `PROJECT.md` (relevé + compréhension métier,
décisions actées, pièges connus), dernières entrées de `JOURNAL.md`, lot de
changelog ouvert, leçons applicables. Si `.odoo-agents/` manque :
`~/.odoo19-agents/scripts/odoo_project_scan.py <racine>`.

## Aiguillage

| Nature de la demande | Réponse |
|---|---|
| **Fonctionnel pur** — comprendre, cadrer, challenger, chiffrer, « Odoo sait-il faire… », arbitrer une règle métier | `odoo-functional-reviewer` **seul**, aucun code |
| **Développement** — créer, modifier, corriger, étendre du code | **`/odoo-feature`** : fonctionnel → dev → QA de tâche → journal, dans le lot ouvert (ouvert au besoin) |
| **Clôture / livraison** — « ferme le lot », « prépare la livraison », « recette complète » | **`/odoo-lot-close`** : recette entière, captures, guide, README, commit proposé |
| **Validation seule** — « relis », « valide », « ce module est-il propre ? » | `odoo-qa-reviewer` **seul** (mode lot) |
| **Documentation** — guide utilisateur ou de décision, communication client | skill **`camptocamp-docs`** |
| **Amélioration du dispositif** — « qu'a-t-on appris », « le guide est-il à jour » | **`/odoo-retex`** |

Règles :

- La chaîne se déroule **sans redemander l'autorisation entre les étapes** ;
  elle ne s'arrête que si le standard couvre le besoin, sur question bloquante,
  ou QA rouge après deux reprises.
- **Tâche légère, lot lourd** : pendant un lot ouvert, chaque tâche reçoit lint
  des fichiers touchés, install/update et tests ciblés ; la recette complète
  se joue une fois, à la clôture. Une tâche qui touche aux droits, à la compta,
  à la facturation ou aux données existantes se valide tout de suite.
- Une demande de dev triviale ne dispense pas de la revue fonctionnelle,
  expédiée en une ligne quand la demande est saine.
- Une question purement technique (« où est défini X ») se répond directement,
  sans agent — dans la série du projet.
- Toute intervention se termine par une entrée (≤ 15 lignes) dans le
  `JOURNAL.md` du projet ; le détail vit dans le dossier du lot.
- Claude Code délègue aux sous-agents ; Codex applique les rôles
  (`~/.odoo19-agents/roles/*.md`) lui-même, en séquence. Résultat identique.
- Hors Odoo, cet aiguillage ne s'applique pas.

## Données réelles

La voie normale est une **copie locale** de la sauvegarde client :
`~/.odoo19-agents/scripts/odoo-restore.sh <sauvegarde.zip> --db <client>_test`
(neutralisée, `admin/admin`, tout y est permis). Sans sauvegarde, l'accès à une
base distante se **déclare** (`odoo_instance.py add <projet>` : secret dans le
trousseau du bureau, le reste dans `~/.odoo-agents/instances/`, rien dans un
dépôt) plutôt que de coller des identifiants dans la conversation ; clé API et
compte en lecture seule recommandés.

**Production — règles absolues** : annonce en clair *« Vous me donnez accès à
la PRODUCTION de <client>. Je n'y ferai que de la lecture. Toute écriture vous
sera demandée explicitement, opération par opération. »* ; lecture seule par
défaut (`odoo_instance.py` refuse `create`/`write`/`unlink` en production) ;
une écriture exige la confirmation humaine de **cette** opération, puis
`--allow-write` et `ODOO_PRODUCTION_CONFIRMED=<nom>` ; jamais en lot ; aucun
test, capture ni reprise en production ; aucun identifiant affiché, journalisé
ou commité. Staging et test : écriture permise, annoncée, nettoyée derrière.
