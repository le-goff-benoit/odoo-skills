# Chaîne de développement Odoo — une demande, dans un lot

Enchaîne les profils dans l'ordre logique sur une demande de développement,
**sans redemander l'autorisation entre les étapes**. La demande à traiter suit
cette consigne (ou est celle que l'utilisateur vient de formuler).

Référentiel commun dans `~/.odoo19-agents/` : `ODOO19_STYLE_GUIDE.md` (19.0),
`SERIES_MATRIX.md` (les autres séries, fait foi), `LESSONS.md`. Réponds en
français.

## Le principe : tâche légère, lot lourd

Une demande de développement s'inscrit dans un **lot** de changelog
(`changelog/AAAA-MM-JJ_NN_titre/`), qui regroupe les demandes d'une même
livraison. Pendant que le lot est ouvert, chaque tâche reçoit une **QA de
tâche** proportionnée (lint des fichiers touchés, tests ciblés, installation
sur la base de QA). La **recette complète** — base neuve, suite entière, tours,
désinstallation, mise à niveau sur la copie du client, captures, guide,
communication — se joue **une fois, à la clôture du lot** (`/odoo-close`).
Cette chaîne ne clôture jamais un lot : c'est un acte de l'humain.

Exception : une demande qui touche aux droits, à la comptabilité, à la
facturation ou aux données existantes est validée **immédiatement** au niveau
nécessaire (recette sur la copie du client comprise), lot ouvert ou pas.

## Comment enchaîner les profils

- **Claude Code** : délègue chaque étape au sous-agent nommé (outil `Agent`,
  `subagent_type` = `odoo-analyst`, `odoo-developer`,
  `odoo-tester`). Le sous-agent ne voit pas cette conversation : sa
  consigne contient le **briefing** de l'étape 0, le chemin du lot, et le chemin
  des fichiers produits par l'étape précédente. Il rend un rapport court ; le
  détail vit dans les fichiers du lot.
- **Codex** (pas de sous-agents) : applique toi-même les rôles, dans l'ordre, en
  lisant `~/.odoo19-agents/roles/<rôle>.md` au début de chaque étape et en
  écrivant les mêmes fichiers. Le résultat doit être indiscernable.

Dans les deux cas, **les fichiers du lot sont le canal de transmission** entre
étapes, pas la conversation : `revue_fonctionnelle.md` → code → `qa.md`.

## Étape 0 — Situer (une commande, non négociable)

```bash
python3 ~/.odoo19-agents/scripts/odoo_briefing.py <module_ou_projet>
```

Le briefing donne la série et son origine, le lot ouvert et ses points, ce que
le projet sait déjà (métier, décisions, pièges), les dernières entrées du
journal, les leçons applicables et les formes attendues dans cette série. S'il
signale l'absence de `.odoo-agents/`, crée-le d'abord :
`~/.odoo19-agents/scripts/odoo_project_scan.py <racine_du_projet>`.

Annonce en une ligne : **projet, série, origine de la série, lot, modules
concernés**. Toutes les étapes suivantes travaillent dans cette série.

Puis le lot :

```bash
LOT=$(~/.odoo19-agents/scripts/odoo-lot.sh current <racine>)
# Aucun lot ouvert ? on en ouvre un — titre court, orienté résultat métier.
LOT=$(~/.odoo19-agents/scripts/odoo-lot.sh open <racine> "<titre>")
# La demande, telle quelle, datée, dans demande.md ; puis un point dans le suivi.
~/.odoo19-agents/scripts/odoo-lot.sh add "$LOT" "<point en une ligne>"
```

Copie la demande d'origine dans `$LOT/demande.md` **sans la reformuler**.

Cherche aussi une **copie du client** (le briefing liste les bases du stack et
les instances déclarées). Elle sert aux trois étapes. Si elle manque et que la
demande touche des données existantes, demande-la à l'utilisateur dès
maintenant — sans bloquer la revue fonctionnelle.

## Étape 1 — Revue fonctionnelle (`odoo-analyst`)

Rôle : `~/.odoo19-agents/roles/functional-review.md`. Il écrit sa revue dans
`$LOT/revue_fonctionnelle.md` (une section par point si le lot en a plusieurs)
et ses décisions durables dans `PROJECT.md`.

Puis **décide, et annonce ta décision** :

| Issue de la revue | Suite |
|---|---|
| Verdict **ÇA EXISTE** — le standard de la série (ou la base du client) couvre le besoin | **STOP.** Livre la revue, explique la configuration à faire, ne développe pas. Le point est marqué « configuration » dans le suivi du lot. |
| Au moins une **question bloquante** | **STOP.** Livre la revue et les questions. N'invente pas la réponse. |
| Contradiction **bloquante** non levable | **STOP.** Livre la revue avec le risque. |
| Spec saine (y compris demande triviale expédiée en une ligne) | **CONTINUE** à l'étape 2. |

Ne t'arrête pas pour une contradiction majeure ou mineure : consigne-la comme
hypothèse retenue dans la spec, et continue.

## Étape 2 — Implémentation (`odoo-developer`)

Rôle : `~/.odoo19-agents/roles/implementation.md`, avec la spec de
`revue_fonctionnelle.md` comme périmètre — ni plus, ni moins. Il livre le code,
les tests, et le lint vert sur les fichiers touchés :

```bash
~/.odoo19-agents/scripts/odoo-lint.sh --changed "$(cat $LOT/.base)" <module>
```

La version du manifest **ne bouge pas à chaque tâche** : elle s'incrémente une
fois par lot, à la clôture — sauf si le lot est constitué d'une seule tâche à
livrer tout de suite, auquel cas le développeur l'incrémente maintenant.

## Étape 3 — QA de tâche (`odoo-tester`, mode tâche)

Rôle : `~/.odoo19-agents/roles/qa-review.md`, **mode tâche** : relecture du
diff, lint `--changed`, installation/mise à jour du module sur la base de QA et
tests ciblés de la tâche.

```bash
export ODOO_ADDONS_DIR=<répertoire contenant le module>
~/.odoo19-agents/scripts/odoo-test.sh <module> --update --tags /<module>:<TestClasse>
```

Le QA écrit son verdict dans `$LOT/qa.md` (une section datée par tâche) et
vérifie explicitement chaque critère d'acceptation de la spec. Il marque le
point dans le suivi du lot :

```bash
~/.odoo19-agents/scripts/odoo-lot.sh done "$LOT" <n°> "<verdict — test ciblé>"
```

Pas de captures, pas de guide, pas de communication à ce stade : c'est la
clôture qui les produit, une fois pour tout le lot. Si un écran change, note-le
dans « Ce que l'utilisateur verra » de la revue, c'est ce que la clôture lira.

## Étape 4 — Capitaliser (deux minutes, ne se saute pas)

Une chaîne qui ne laisse pas de trace oblige la suivante à tout redécouvrir.

1. **Entrée de journal** dans `<projet>/.odoo-agents/JOURNAL.md` — **quinze
   lignes au plus** : date, demande, fait, verdict, **Appris**, reste ouvert.
   Le détail est dans le lot ; le journal est la mémoire courte, pas l'archive.
2. **Fiche projet** : si le métier ou un piège durable a été éclairci, complète
   `PROJECT.md` (« Compréhension métier », « Décisions actées », « Pièges
   connus »).
3. **Candidate à `LESSONS.md`** : si l'incident dépasse ce projet — une règle
   fausse dans le guide, un motif de lint absent, une confusion de série — dis-le
   dans le compte-rendu, section « Reste à faire ». C'est `/odoo-feedback` qui
   promeut.

## Boucle de reprise

Si la QA remonte des anomalies **bloquantes** : retour à l'étape 2 pour les
corriger, puis nouvelle QA. **Deux reprises au maximum.** Au-delà, arrête et
livre l'état réel avec ce qui reste rouge — ne boucle pas indéfiniment et ne
masque pas un échec.

Les anomalies majeures et mineures ne déclenchent pas de reprise : elles sont
listées dans le compte-rendu final pour arbitrage, et dans `qa.md`.

## Compte-rendu final (court : le détail est dans le lot)

```markdown
# <titre de la demande>

**Projet** <nom> · **série** <X.Y> · **lot** `<dossier>` (point n°<n>) · **modules** <…>

## Cadrage
<verdict standard, hypothèses retenues, hors périmètre — trois lignes>

## Réalisation
<fichiers créés / modifiés, choix techniques notables>

## QA de tâche
| Contrôle | Résultat |
<lint --changed, install/update, tests ciblés n/n>
| Critère d'acceptation | Couvert par | État |

## Reste à faire / arbitrages
<anomalies non corrigées, questions ouvertes, leçon candidate>

## Lot
<n> point(s) dans le lot, <m> réalisé(s). Clôture et recette complète : `/odoo-close`.
```

## Règles

- Annonce l'étape en cours avant de la commencer (`── Étape 2/4 : implémentation`).
- Annonce la série cible dès l'étape 0 et n'en change plus en cours de route.
- Un arrêt aux étapes 1 ou 3 est un résultat légitime, pas un échec : dis pourquoi.
- Ne déclare jamais « testé » ce qui n'a pas été exécuté. Si Docker n'est pas
  disponible, livre les étapes 1 et 2 et dis explicitement que l'étape 3 est partielle.
- Ne lis pas les logs Odoo en entier : `odoo-test.sh` en extrait les erreurs et
  termine par une ligne `RECETTE …`. Va dans le log complet seulement pour
  localiser une erreur déjà signalée.
