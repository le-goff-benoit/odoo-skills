Sources Odoo en lecture seule sur ce poste :
`~/odoo-sources/{14.0,17.0,18.0,19.0,19.1,19.4}` (+ `-enterprise`).
Ne jamais y écrire : tout code va dans le module custom du projet.

Référentiel (`~/.odoo19-agents/`) :
- `ODOO19_STYLE_GUIDE.md` — ligne éditoriale, décrit la **19.0** ;
- `SERIES_MATRIX.md` — ce qui change d'une série à l'autre ; **fait foi** quand
  il contredit le guide ;
- `PLATEFORMES.md` — ce qui change d'un hébergement à l'autre (Odoo.sh, Odoo
  Online/SaaS, on-premise et Docker local) ; **fait foi** sur le déploiement, la
  restauration et l'exploitation ;
- `LESSONS.md` — les erreurs déjà payées, à ne pas refaire.

## La série d'abord

Le parc est mélangé : 17.0, 18.0, 19.0, saas~19.1, saas~19.4. Écrire du 19.0
dans un module 18.0 le casse à l'installation ; le relire avec les règles de la
19.0 remonte des anomalies fausses. **Avant toute lecture ou écriture de code
Odoo, établir la série cible** :

```bash
python3 ~/.odoo19-agents/scripts/odoo_series.py <chemin_du_module>
```

Elle vient de `.odoo-agents/config` du projet, sinon du préfixe de `version` du
manifest. Tous les scripts l'annoncent en tête de sortie.

## Le projet ensuite

Chaque projet outillé porte un dossier `.odoo-agents/` :

| Fichier | Contenu | Qui l'écrit |
|---|---|---|
| `config` | la série qui fait autorité | le scan, puis l'humain |
| `PROJECT.md` | relevé (modules, modèles, dépendances, dette, zones chaudes) + compréhension métier, décisions actées, pièges connus | le scan pour le relevé, les agents pour le reste |
| `JOURNAL.md` | une entrée par intervention, avec ce qui a été **appris** | le profil QA en fin de chaîne |

À lire **avant** d'analyser ou de coder. À créer s'il manque :

```bash
~/.odoo19-agents/scripts/odoo_project_scan.py <racine_du_projet>
```

## Aiguillage — quel agent pour quelle demande

Trois profils existent : `odoo-functional-reviewer`, `odoo-developer`, `odoo-qa-reviewer`,
plus le skill `camptocamp-docs` pour les livrables documentaires.
Le choix ne se discute pas, il découle de la nature de la demande :

| Nature de la demande | Réponse attendue |
|---|---|
| **Fonctionnel pur** — comprendre, cadrer, challenger, chiffrer, « est-ce qu'Odoo sait faire… », « comment configurer… », arbitrer une règle métier | **`odoo-functional-reviewer` seul.** Aucun code écrit. |
| **Développement** — créer, modifier, corriger, étendre du code (module, modèle, champ, vue, rapport, wizard, correctif de bug) | **La chaîne complète, automatiquement** : `odoo-functional-reviewer` → `odoo-developer` → `odoo-qa-reviewer`. C'est ce que fait `/odoo-feature`. |
| **Validation seule** — « relis », « valide », « teste », « ce module est-il propre ? » | **`odoo-qa-reviewer` seul.** |
| **Amélioration du dispositif** — « qu'est-ce qu'on a appris », « le guide est-il à jour », « fais un retex » | **`/odoo-retex`.** Relit les journaux, vérifie le référentiel contre les sources, promeut les leçons. |
| **Documentation & livraison** — guide utilisateur, guide de décision, changelog d'un lot, recette, communication client, captures d'écran | **Skill `camptocamp-docs`.** Copie locale du client restaurée, captures réelles, DOCX + PDF à la charte Camptocamp. |

Règles d'application :

- La chaîne de développement se déroule **sans redemander l'autorisation entre les
  étapes**. Elle ne s'interrompt que dans les cas prévus par `/odoo-feature`
  (question bloquante, besoin déjà couvert par le standard, QA rouge après reprise).
- Une demande de dev triviale ne dispense pas de la revue fonctionnelle : celle-ci
  est simplement expédiée en une ligne quand la demande est saine.
- Une question purement technique sur Odoo (« où est défini X », « comment marche Y »)
  se répond directement, sans agent — mais **dans la série du projet concerné**.
- Toute intervention de la chaîne se termine par une entrée dans le `JOURNAL.md`
  du projet. Ce qui n'est pas écrit sera redécouvert au prix fort.
- Hors Odoo, cet aiguillage ne s'applique pas.

## Données réelles : sauvegarde d'abord, base distante ensuite

Quand une tâche a besoin des données du client (reproduire un défaut, capturer des
écrans, reprendre des données, chiffrer une migration), la voie normale est une
**copie locale** : sauvegarde fournie par le client ou téléchargée, puis

```bash
~/.odoo19-agents/scripts/odoo-restore.sh <sauvegarde.zip> --db <client>_test
```

La base est neutralisée (mails, crons, paiements coupés, bandeau), `admin/admin`, et
tout y est permis.

Si aucune sauvegarde n'est disponible, ou qu'il faut lire une base distante, **guide
l'utilisateur** pour déclarer l'accès plutôt que de coller des identifiants dans la
conversation :

```bash
~/.odoo19-agents/scripts/odoo_instance.py add <projet>     # questions une à une, saisie masquée
~/.odoo19-agents/scripts/odoo_instance.py check <projet> <nom>
```

Les identifiants sont stockés dans `~/.odoo-agents/instances/<projet>.json` (mode 600,
hors de tout dépôt). Recommande une **clé API** (Préférences → Sécurité du compte)
plutôt qu'un mot de passe, et un compte en lecture seule pour la production.

**Production** — règles absolues, rappelées à l'utilisateur avant la première connexion :

- annonce l'avertissement en clair : *« Vous me donnez accès à la PRODUCTION de <client>.
  Je n'y ferai que de la lecture. Toute écriture vous sera demandée explicitement,
  opération par opération. »* ;
- lecture seule par défaut : `odoo_instance.py` refuse `create`, `write`, `unlink` et
  toute méthode d'action sur une instance `production` ;
- une écriture en production n'est possible qu'après **confirmation explicite de
  l'humain pour cette opération précise** (modèle, enregistrements, valeurs), puis
  `--allow-write` et `ODOO_PRODUCTION_CONFIRMED=<nom>` sur la commande. Jamais en lot,
  jamais « pendant qu'on y est » ;
- aucun test, aucune capture d'écran, aucune reprise de données en production : ça se
  fait sur la copie locale ;
- ne jamais afficher, journaliser ni commiter un identifiant ; `odoo_instance.py list`
  ne montre pas les secrets.

Staging et test : écriture permise, mais annonce ce que tu vas modifier et nettoie
derrière toi.
