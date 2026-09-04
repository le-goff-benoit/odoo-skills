# Agents Odoo — Claude Code & Codex

Trois profils d'agents et trois commandes, partagés à l'identique entre Claude
Code et Codex, adossés à une base de connaissances extraite des sources Odoo,
**calée sur la série de chaque projet** (17.0, 18.0, 19.0, saas~19.x), et
alimentée par ce que les interventions précédentes ont appris.

## Installation sur un poste

```bash
git clone git@github.com:le-goff-benoit/odoo-skills.git ~/.odoo19-agents
~/.odoo19-agents/build.sh
```

`build.sh` génère les sous-agents et commandes Claude Code (`~/.claude/agents/`,
`~/.claude/commands/`, `~/.claude/skills/`), les skills Codex (`~/.codex/skills/`)
et injecte le bloc d'aiguillage dans `~/.claude/CLAUDE.md` et `~/.codex/AGENTS.md`.
Il vérifie en fin de course que les deux côtés portent le même texte. À relancer
après chaque `git pull`.

Prérequis :

- les sources Odoo en lecture seule dans `~/odoo-sources/<série>` et
  `~/odoo-sources/<série>-enterprise` (autre emplacement : `export ODOO_SOURCES_DIR=/chemin`) ;
- Docker (plugin compose) pour la QA réelle ;
- Python 3.10+.

Les fichiers générés ne s'éditent jamais à la main : toute modification se fait
dans `roles/`, `routing.md` ou le référentiel, puis `build.sh`, puis commit.

## Le premier réflexe : le briefing

```bash
python3 scripts/odoo_briefing.py <module_ou_projet>
```

Une commande, 3 à 8 Ko, qui remplace la lecture de quatre fichiers : la
**série** et son origine, les **formes attendues** dans cette série, le **release**
de changelog ouvert et ses points, ce que le projet **sait déjà** (compréhension
métier, décisions actées, pièges connus), les dernières entrées du **journal**
et les « Appris » plus anciens, les **leçons** du dispositif applicables. Chaque
rôle commence par là ; l'orchestrateur le passe aux sous-agents dans leur
consigne pour qu'ils ne le recalculent pas.

Le parc est mélangé et la majorité des modules est en 18.0 : la série n'est
jamais supposée, elle est lue (`.odoo-agents/config`, sinon le manifest).

## Les profils et les commandes

| Profil / commande | Rôle | Quand |
|---|---|---|
| `odoo-analyst` | Analyste fonctionnel **contradicteur** : problème réel derrière la demande, standard de la série et série suivante, configuration / Studio / code avec leur coût à la migration, contradictions, questions bloquantes, spec | avant de coder |
| `odoo-developer` | Développeur : code dans la ligne éditoriale de sa série, tests livrés avec, lint des fichiers touchés, tests ciblés | pendant la release |
| `odoo-studio` | Configurateur : réalise sans module (champs `x_`, automatisations, actions serveur et planifiées, vues, droits) sur la copie du client, prouve par scénarios RPC, livre un pack JSON versionné (`odoo_pack.py`) appliqué par identifiant externe ; annonce les limites de Studio | quand l'analyste choisit la voie Studio |
| `odoo-support` | Support : reproduit un ticket sur l'enregistrement réel (production en lecture seule, copie client), prouve la cause, classe (usage, configuration, données, bug, évolution), mesure l'impact, écrit le test rouge et le brouillon de réponse ; passe la main selon le verdict | à chaque ticket |
| `odoo-tester` | Relecteur & QA, deux modes : **tâche** (diff, lint `--changed`, install/update, tests ciblés) et **release** (`odoo-recette.sh` : base neuve, suite complète, tours, désinstallation, copie client) | chaque tâche, puis la clôture |
| `/odoo-new` | La chaîne sur une demande : briefing → release → fonctionnel → dev → QA de tâche → journal | chaque demande de dev |
| `/odoo-close` | Clôture de la release : recette complète, recette navigateur, captures, guide, README final, commit proposé, journal | quand la livraison est prête |
| `/odoo-feedback` | Retour d'expérience : relit les journaux et les recettes, vérifie le référentiel contre les sources, promeut les leçons | tous les dix journaux, ou sur incident |
| `camptocamp-docs` (skill) | Guide utilisateur / de décision DOCX + PDF à la charte, communication client, captures depuis la copie locale | à la clôture, ou sur demande |

## Tâche légère, release lourde

Une demande de développement s'inscrit dans une **release** de changelog
(`changelog/AAAA-MM-JJ_NN_titre/`) qui regroupe les demandes d'une même
livraison. Le cycle :

```
odoo-release.sh open  ──▶  /odoo-new ×n  ──▶  /odoo-close  ──▶  commit, déploiement
   demande.md          revue_fonctionnelle.md      recette.md, tests_navigateur.md
   README (suivi)      code + tests, qa.md         captures/, guide, communication
   .base (git)         journal (≤ 15 lignes)       README final, journal de release
```

- **Pendant la release**, chaque tâche reçoit une QA proportionnée : lint des
  fichiers modifiés depuis l'ouverture, un seul chargement d'Odoo (`--quick`)
  avec les tests ciblés sur une base par module gardée chaude. Pas de captures,
  pas de guide. Le testeur ajoute un **point de contrôle** (suite complète du
  module, base chaude, en arrière-plan) quand deux points se croisent, qu'un
  modèle partagé est touché, ou tous les trois points.
- **À la clôture**, tout est rejoué une fois sur l'état exact qui partira :
  `odoo-recette.sh` enchaîne lint, base neuve (clonée en secondes depuis un
  **gabarit** par module où les dépendances standard sont préinstallées,
  reconstruit quand le manifest change), `-u`, suite complète (tours compris),
  désinstallation, mise à niveau sur la copie du client, et écrit un tableau
  avec les durées. Puis recette navigateur, captures, livrables client, README final
  avec les versions lues dans les manifests, message de commit proposé.
- **Exception** : une tâche qui touche aux droits, à la compta, à la
  facturation ou aux données existantes se valide immédiatement au niveau de la release.
- La **version** du manifest s'incrémente une fois par release, à la clôture ; la
  version livrée est celle qui a été testée.

Les fichiers de la release sont le canal entre les étapes — pas la conversation. Côté
Claude Code, chaque étape est un sous-agent qui reçoit le briefing et les chemins ;
côté Codex, le même rôle est appliqué en séquence par l'agent principal.

### Utilisation

```
> /odoo-new ajoute un champ « référence chantier » sur la commande client
> /odoo-new corrige le calcul de la remise sur les lignes de kit      # même release
> /odoo-close
> utilise odoo-analyst pour challenger cette demande : …
> lance odoo-tester sur alamaison_customisation                     # mode release
> /odoo-feedback
```

Codex : mêmes noms, en skills (`/odoo-new …`, `/odoo-close`, `/odoo-feedback`,
`/odoo-analyst …`, `/odoo-developer …`, `/odoo-tester …`).

## Arborescence

```
~/.odoo19-agents/
├── ODOO19_STYLE_GUIDE.md   ← la ligne éditoriale de la 19.0 (+ § 10 commits, versions, releases)
├── SERIES_MATRIX.md        ← ce qui change d'une série à l'autre (fait foi)
├── LESSONS.md              ← mémoire longue : les erreurs déjà payées (+ date du dernier retex)
├── PLATEFORMES.md          ← ce qui change d'un hébergement à l'autre (fait foi)
├── routing.md              ← aiguillage (→ CLAUDE.md et AGENTS.md), volontairement court
├── roles/                  ← les prompts, SOURCE UNIQUE
│   ├── functional-review.md
│   ├── implementation.md
│   ├── support.md          ← odoo-support (tickets)
│   ├── studio.md           ← odoo-studio (configuration en base, sans module)
│   ├── qa-review.md
│   ├── orchestration.md    ← /odoo-new
│   ├── release-close.md        ← /odoo-close
│   ├── retex.md            ← /odoo-feedback
│   └── docs.md             ← skill camptocamp-docs
├── docs/                   ← livrables documentaires (charte, gabarits du changelog)
│   └── templates/changelog/  suivi.md (release ouverte), README.md (final), demande.md,
│                             tests_navigateur.md, communication_client.txt
├── stack/                  ← Odoo local pour la QA, une image par série
├── scripts/
│   ├── odoo_briefing.py    briefing compact d'un projet — le premier réflexe
│   ├── odoo_series.py      résolution de la série cible d'un module
│   ├── odoo_project_scan.py écrit <projet>/.odoo-agents/PROJECT.md (relevé)
│   ├── odoo_pack.py        export / diff / apply d'un pack de configuration par XML-ID (Studio sans module)
│   ├── odoo_mail.py        verse un ou plusieurs .eml (demande, ticket) dans demande.md + pieces/
│   ├── odoo-release.sh         open / current / add / done / changed / modules / close
│   ├── odoo-lint.sh        ruff (config Odoo) + contrôles Odoo, --changed <ref>
│   ├── odoo_lint.py        manifest, XML, sécurité, tests, motifs datés par série
│   ├── odoo-test.sh        install + update + tests + tours + désinstall + logs, base par module
│   ├── odoo-recette.sh     le protocole complet de clôture, en un tableau
│   ├── odoo-stack.sh       build / up / down / reset / logs / psql / odoo-shell / dbs
│   ├── odoo-restore.sh     sauvegarde client → base locale neutralisée
│   ├── odoo-config-inventory.sh  Studio, automatisations, vues, rapports d'une base
│   ├── odoo_instance.py    accès déclaré aux bases distantes (prod en lecture seule)
│   ├── odoo-shot.sh / odoo_capture.py / odoo-pdf.sh   captures et PDF réels
│   └── series-env.sh       bootstrap de série pour les scripts du stack
├── build.sh                régénère les profils Claude et Codex depuis roles/
└── README.md
```

Fichiers **générés**, à ne pas éditer :

```
~/.claude/agents/odoo-*.md                 ~/.codex/skills/odoo-*/SKILL.md
~/.claude/commands/odoo-{feature,release-close,retex}.md
~/.claude/skills/camptocamp-docs/          ~/.codex/skills/camptocamp-docs/
~/.claude/CLAUDE.md   ~/.codex/AGENTS.md   (bloc délimité uniquement)
```

## Les consignes d'un projet : `AGENTS.md` et `CLAUDE.md`

Le scan crée, s'ils n'existent pas, un `AGENTS.md` canonique (gabarit
`docs/templates/project_AGENTS.md` : série, première commande, tableau des
commandes, release, inbox, mémoire, données réelles, conventions propres au
projet à compléter) et un `CLAUDE.md` qui y renvoie. Un projet qui a déjà ses
consignes n'est pas touché : on y ajoute à la main la section « Outillage ».

Pour travailler sur le dispositif lui-même, voir [`AGENTS.md`](AGENTS.md) à la
racine de ce dépôt.

## Le dossier `inbox/` d'un projet

Créé par le scan ou à l'ouverture d'une release, ignoré par git : l'humain y
dépose une **sauvegarde** (`.zip` Odoo.sh ou gestionnaire de bases, `.dump`,
`.sql`) ou des **mails** (`.eml`) à l'attention des agents. Le briefing en liste
le contenu avec la commande qui va avec (`odoo-restore.sh`, `odoo_mail.py`) ;
les rôles y regardent à l'étape 0.

## Le dossier `.odoo-agents/` d'un projet

Créé par `scripts/odoo_project_scan.py`, à la racine du projet client :

| Fichier | Contenu | Écrit par |
|---|---|---|
| `config` | `series = 18.0` — fait autorité sur la détection ; `lot_label = release` si le projet dit « release » | le scan, puis l'humain |
| `PROJECT.md` | **relevé** régénérable (modules, modèles, dépendances, sécurité, tests, dette lint, zones chaudes git, releases) + **compréhension** écrite à la main (métier, décisions actées, pièges connus), jamais écrasée | le scan / les agents |
| `JOURNAL.md` | une entrée par intervention, **quinze lignes au plus** : demande, fait, verdict, **Appris**, reste ouvert | le QA, la clôture |

Le journal est la mémoire courte ; l'analyse détaillée vit dans le dossier du
release. Le briefing ne montre que les dernières entrées et extrait les « Appris »
des autres : un journal qui gonfle ne coûte plus de tokens, mais reste lisible
par l'humain s'il tient ses quinze lignes.

La boucle d'amélioration : le QA écrit ce qu'il a appris → `/odoo-feedback` relit
tous les journaux et les recettes, garde ce qui est récurrent ou coûteux, le
promeut dans `LESSONS.md` **avec un effet obligatoire** (motif de lint,
correction du guide, règle de rôle, ou réglage du briefing) → `build.sh` rediffuse.

## Outillage

```bash
# Briefing, série, fiche de contexte
python3 scripts/odoo_briefing.py ~/mon_projet
python3 scripts/odoo_series.py /chemin/vers/mon_module
scripts/odoo_project_scan.py ~/mon_projet

# Release
scripts/odoo-release.sh open ~/mon_projet "Contrats à facturer"
scripts/odoo-release.sh current ~/mon_projet
scripts/odoo-release.sh add <release> "Filtre corrigé" "TestContractsToInvoice"
scripts/odoo-release.sh done <release> 1 "vert"
scripts/odoo-release.sh modules <release>
python3 scripts/odoo_mail.py ~/Downloads/ticket.eml --release <release> --section "Ticket #3720"

# Configuration en base sans module (voie Studio) : pack versionné, appliqué par XML-ID
python3 scripts/odoo_pack.py export --db client_test --module cfg_client --out <release>/studio/pack.json
python3 scripts/odoo_pack.py diff  <release>/studio/pack.json --instance client staging
python3 scripts/odoo_pack.py apply <release>/studio/pack.json --instance client staging

# Lint : tout, ou seulement ce qui a changé depuis l'ouverture de la release
scripts/odoo-lint.sh /chemin/vers/mon_module
scripts/odoo-lint.sh --changed "$(cat <release>/.base)" /chemin/vers/mon_module
scripts/odoo-lint.sh --series 19.0 /chemin/vers/mon_module   # chiffrer une migration

# Stack de test (une image par série)
export ODOO_ADDONS_DIR=~/mon_projet   # dossier CONTENANT le module
scripts/odoo-stack.sh build           # UNE FOIS PAR SÉRIE
scripts/odoo-stack.sh up              # http://localhost:8079  (admin/admin)

# QA de tâche : un seul chargement, tests ciblés (base odoo_qa_<série>_<module>, jamais partagée)
scripts/odoo-test.sh mon_module --quick --tags /mon_module:TestMaClasse
# Point de contrôle : suite complète du module, base chaude
scripts/odoo-test.sh mon_module --quick

# QA de release : le protocole complet, en un tableau (recette.md dans la release)
scripts/odoo-recette.sh mon_module --release <release> --db client_test

# Sauvegarde client → base locale neutralisée, inventaire de ce qui vit en base
scripts/odoo-restore.sh ~/Downloads/client-2026-08-19.zip --db client_test
scripts/odoo-config-inventory.sh client_test

# Accès déclaré à une base distante : secret dans le trousseau GNOME (libsecret),
# métadonnées dans ~/.odoo-agents/instances/<projet>.json ; production en lecture seule
scripts/odoo_instance.py add mon_projet
scripts/odoo_instance.py check mon_projet staging
scripts/odoo_instance.py migrate mon_projet      # secrets JSON existants → trousseau

# Captures, PDF réels
scripts/odoo-shot.sh "/odoo/action-mod.action_x/3" --wait ".o_form_view" --full
scripts/odoo_capture.py /odoo/project --db client_test --lang fr_FR --clip .o_form_view --out 01.png
scripts/odoo-pdf.sh sale.action_report_saleorder 12 --out devis.pdf --html
```

Ports par défaut : `8079` (HTTP), `8082` (gevent), `5439` (PostgreSQL). Chaque
série a son projet compose (`odoo-qa-18_0`, `odoo-qa-19_0`), son image, ses
volumes ; chaque module a sa base de test. Deux séries cohabitent (ports à
régler) ; deux agents sur la même série aussi, tant qu'ils ne partagent pas de
base.

## Pièges déjà traités dans l'outillage

- L'image `odoo:19.0` est basée sur **Ubuntu 24.04** : `apt install chromium`
  n'y installe qu'un stub vers le snap → le Dockerfile installe `google-chrome-stable`.
- Sans **`websocket-client`**, `HttpCase` *skippe* tous les tours sans échouer
  → installé dans l'image, et un test ignoré faute de dépendance est un échec.
- Le `ruff.toml` officiel d'Odoo est **plus strict que le code d'Odoo lui-même**
  → `odoo-lint.sh` fait une passe bloquante (règles réellement respectées) et une
  passe « conseil ».
- Le conteneur tourne en uid 101 : `stack/artifacts/` est en 777 ; un module
  dans un dossier non lisible par cet uid est **ignoré** par Odoo.
- **`odoo -i <module>` sur un module introuvable sort en 0** avec un simple
  `WARNING invalid module names, ignored` → `odoo-test.sh` le traite comme un échec.
- **Base de test partagée** : deux projets de la même série se droppaient la
  base l'un de l'autre avec `--fresh` → une base par module, et PostgreSQL n'est
  jamais arrêté s'il tournait déjà avant l'appel.
- Chrome refuse les connexions CDP dont l'`Origin` n'est pas autorisée
  (`--remote-allow-origins=*`).
- **PDF QWeb** : `_render_qweb_pdf` retombe sur du HTML en contexte de test ;
  sans serveur HTTP, wkhtmltopdf ne charge pas les CSS ; les bundles sont
  produits par le processus serveur → `odoo-pdf.sh` passe par la route réelle
  `/report/pdf/<report>/<ids>`. Un PDF nu embarque `NimbusSans`, un PDF correct `Lato`.
- Un relevé pris depuis un **worktree git** inscrit un chemin qui disparaîtra
  avec lui → le scan et le briefing le signalent.

## Ce que les agents ont réellement à disposition

Tout est **dans le conteneur**, pas sur l'hôte :

| Capacité | Où | Comment y accéder |
|---|---|---|
| Google Chrome (tours, captures) | image `odoo-qa:<série>` | `odoo-test.sh --tours`, `odoo-shot.sh` |
| wkhtmltopdf 0.12.6 (patched qt) | image `odoo-qa:<série>` | `odoo-pdf.sh` |
| poppler-utils (`pdffonts`, `pdftotext`) | image `odoo-qa:<série>` | `odoo-stack.sh shell` |
| ruff | image `odoo-qa:<série>` | `odoo-lint.sh` (bascule automatique) |
| Sources community + Enterprise de la série | volumes `:ro` | `odoo-stack.sh psql` / `odoo-shell` |

## Sources

`~/odoo-sources/{14.0,17.0,18.0,19.0,19.1,19.4}` (+ `-enterprise`),
**en lecture seule**. Le stack les monte en `:ro`.
