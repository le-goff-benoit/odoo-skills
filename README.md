# Agents Odoo — Claude Code & Codex

Trois profils d'agents partagés entre Claude Code et Codex, adossés à une base de
connaissances extraite des sources Odoo, **calée sur la série de chaque projet**
(17.0, 18.0, 19.0, saas~19.x), et alimentée par ce que les interventions
précédentes ont appris.

## Installation sur un poste

```bash
git clone <url-du-dépôt> ~/.odoo19-agents
~/.odoo19-agents/build.sh
```

`build.sh` génère les sous-agents et commandes Claude Code (`~/.claude/agents/`,
`~/.claude/commands/`), les skills Codex (`~/.codex/skills/`) et injecte le bloc
d'aiguillage dans `~/.claude/CLAUDE.md` et `~/.codex/AGENTS.md`. À relancer après
chaque `git pull`.

Prérequis :

- les sources Odoo en lecture seule dans `~/odoo-sources/<série>` et
  `~/odoo-sources/<série>-enterprise` (17.0, 18.0, 19.0, saas~19.x selon le parc) ;
  un autre emplacement se déclare par `export ODOO_SOURCES_DIR=/chemin` ;
- Docker (avec le plugin compose) pour la QA réelle ;
- Python 3.10+.

Pour le stack QA, copier `stack/.env.example` en `stack/.env` et y renseigner
`ODOO_ADDONS_DIR` (le projet à tester) et les ports si ceux par défaut sont pris.

Les fichiers générés ne s'éditent jamais à la main : toute modification se fait
dans `roles/`, `routing.md` ou le référentiel, puis `build.sh`, puis commit.

## Les trois lectures avant toute chose

| Question | Où est la réponse |
|---|---|
| Sur quelle **série** travaille-t-on ? | `scripts/odoo_series.py <module>` — déduit de `.odoo-agents/config` ou du manifest |
| Que sait-on de ce **projet** ? | `<projet>/.odoo-agents/PROJECT.md` et `JOURNAL.md` |
| Quelles **erreurs** ne pas refaire ? | `LESSONS.md` |

Le parc est mélangé et la majorité des modules est en 18.0 : écrire du 19.0 dans
un module 18.0 le casse à l'installation, le relire avec les règles de la 19.0
remonte des anomalies fausses. La série n'est jamais supposée.

## Les trois profils

| Profil | Rôle | Quand l'appeler |
|---|---|---|
| `odoo-functional-reviewer` | Analyste fonctionnel **contradicteur** | avant de coder : reformule la demande, vérifie si le standard 19.0 couvre déjà le besoin, remonte les contradictions et les non-dits, pose les questions bloquantes, produit la spec et les critères d'acceptation |
| `odoo-developer` | Développeur | écrit le code du module dans la ligne éditoriale Odoo 19, livre les tests avec, passe le lint |
| `odoo-qa-reviewer` | Relecteur & QA | valide : lint statique, puis installation / mise à jour / tests sur un Odoo 19 local Docker, puis parcours e2e (tours Chrome) |

## Aiguillage automatique

`~/.claude/CLAUDE.md` et `~/.codex/AGENTS.md` (générés depuis `routing.md`) portent la
même règle dans les deux outils :

| Nature de la demande | Réponse |
|---|---|
| **Fonctionnel pur** (cadrer, challenger, « Odoo sait-il faire… ») | `odoo-functional-reviewer` **seul**, aucun code |
| **Développement** | les **trois en chaîne**, automatiquement — c'est `/odoo-feature` |
| **Validation seule** (« relis », « teste ») | `odoo-qa-reviewer` **seul** |
| **Amélioration du dispositif** (« qu'a-t-on appris », « le guide est-il à jour ») | `/odoo-retex` |

La chaîne ne s'arrête qu'en trois cas : le standard couvre déjà le besoin, une question
bloquante subsiste, ou la QA reste rouge après deux reprises.

### Utilisation

**Claude Code** — les profils sont des sous-agents dans `~/.claude/agents/` :

```
> /odoo-feature ajoute un champ « référence chantier » sur la commande client
> utilise odoo-functional-reviewer pour challenger cette demande : …
> lance odoo-qa-reviewer sur alamaison_customisation
> /odoo-retex          # relit les journaux, met le référentiel à jour
```

**Codex** — les profils sont des skills dans `~/.codex/skills/` :

```
/odoo-feature  ajoute un champ « référence chantier » sur la commande client
/odoo-functional-reviewer  …
/odoo-developer  …
/odoo-qa-reviewer  …
```

## Arborescence

```
~/.odoo19-agents/
├── ODOO19_STYLE_GUIDE.md   ← la ligne éditoriale de la 19.0
├── SERIES_MATRIX.md        ← ce qui change d'une série à l'autre (fait foi)
├── LESSONS.md              ← mémoire longue : les erreurs déjà payées
├── PLATEFORMES.md          ← ce qui change d'un hébergement à l'autre (fait foi)
├── routing.md              ← règle d'aiguillage (→ CLAUDE.md et AGENTS.md)
├── roles/                  ← les prompts, SOURCE UNIQUE
│   ├── functional-review.md
│   ├── implementation.md
│   ├── qa-review.md
│   ├── orchestration.md    ← la chaîne /odoo-feature
│   └── retex.md            ← /odoo-retex, l'amélioration continue
├── stack/                  ← Odoo local pour la QA, une image par série
│   ├── docker-compose.yml
│   ├── Dockerfile          (odoo:<série> + google-chrome + websocket-client + ruff)
│   ├── odoo.conf
│   ├── .env.example
│   └── artifacts/          (logs de test, captures d'écran)
├── scripts/
│   ├── odoo_series.py      résolution de la série cible d'un module
│   ├── series-env.sh       bootstrap de série pour les scripts du stack
│   ├── odoo_project_scan.py écrit <projet>/.odoo-agents/PROJECT.md
│   ├── odoo-lint.sh        ruff (config Odoo) + contrôles Odoo
│   ├── odoo_lint.py        manifest, XML, sécurité, tests, motifs datés par série
│   ├── odoo-stack.sh       build / up / down / reset / logs / psql / odoo-shell
│   ├── odoo-test.sh        install + update + tests + tours + désinstall + logs
│   ├── odoo-shot.sh        capture d'écran authentifiée (Chrome du conteneur, CDP)
│   ├── odoo_shot.py        pilote CDP, exécuté dans le conteneur
│   └── odoo-pdf.sh         rapport QWeb → PDF réel et mis en forme
├── build.sh                régénère les profils Claude et Codex depuis roles/
└── README.md
```

**Pour modifier un profil ou l'aiguillage : éditer `roles/*.md` ou `routing.md`,
puis `./build.sh`.** Les fichiers suivants sont **générés**, ne pas les éditer :

```
~/.claude/agents/odoo-*.md          ~/.codex/skills/odoo-*/SKILL.md
~/.claude/commands/odoo-feature.md  ~/.codex/skills/odoo-feature/SKILL.md
~/.claude/commands/odoo-retex.md    ~/.codex/skills/odoo-retex/SKILL.md
~/.claude/CLAUDE.md   ~/.codex/AGENTS.md   (bloc délimité uniquement)
```

## Le dossier `.odoo-agents/` d'un projet

Créé par `scripts/odoo_project_scan.py`, à la racine du projet client :

| Fichier | Contenu | Écrit par |
|---|---|---|
| `config` | `series = 18.0` — fait autorité sur la détection | le scan, puis l'humain |
| `PROJECT.md` | **relevé** régénérable (modules, modèles créés/étendus, dépendances community/enterprise, sécurité, tests, dette lint, zones chaudes git) + **compréhension** écrite à la main (métier, décisions actées, pièges connus), jamais écrasée | le scan / les agents |
| `JOURNAL.md` | une entrée par intervention : demande, réalisation, verdict QA, **Appris**, reste ouvert | le profil QA |

La boucle d'amélioration : le QA écrit ce qu'il a appris dans le `JOURNAL.md`
→ `/odoo-retex` relit tous les journaux, garde ce qui est récurrent ou coûteux,
le promeut dans `LESSONS.md` **avec un effet obligatoire** (un motif de lint, une
correction du guide, ou une règle de rôle) → `build.sh` rediffuse.

Dans `CLAUDE.md` et `AGENTS.md`, seul le bloc entre les marqueurs
`<!-- odoo19-agents:début -->` et `<!-- odoo19-agents:fin -->` est régénéré :
ce que tu écris autour est préservé.

## Outillage

```bash
# Série cible d'un module, et fiche de contexte du projet
python3 scripts/odoo_series.py /chemin/vers/mon_module
scripts/odoo_project_scan.py ~/mon_projet

# Lint d'un module (série déduite du module, annoncée en tête de sortie)
scripts/odoo-lint.sh /chemin/vers/mon_module
scripts/odoo-lint.sh --series 19.0 /chemin/vers/mon_module   # chiffrer une migration

# Stack de test
export ODOO_ADDONS_DIR=~/mon_projet   # dossier CONTENANT le module
scripts/odoo-stack.sh build      # UNE FOIS PAR SÉRIE utilisée
scripts/odoo-stack.sh up         # http://localhost:8079  (admin/admin)

# Tests complets
scripts/odoo-test.sh mon_module --fresh --update --uninstall
scripts/odoo-test.sh mon_module --tours          # uniquement les parcours e2e
scripts/odoo-test.sh mon_module --tags /mon_module:TestMaClasse.test_x

# Lint restreint aux fichiers modifiés (module historique porteur de dette)
scripts/odoo-lint.sh --changed [<ref-git>] /chemin/vers/mon_module

# Captures d'écran authentifiées
scripts/odoo-shot.sh /odoo/sales --out liste.png
scripts/odoo-shot.sh "/odoo/action-mod.action_x/3" --wait ".o_form_view" --full
scripts/odoo-shot.sh /my/orders --login portal --password portal --wait body

# Rapport QWeb en PDF réel (+ HTML source pour diagnostic)
scripts/odoo-pdf.sh sale.action_report_saleorder 12 --out devis.pdf --html

scripts/odoo-stack.sh down
```

Ports par défaut : `8079` (HTTP), `8082` (gevent), `5439` (PostgreSQL) — choisis pour
ne pas entrer en conflit avec les autres stacks du poste. Chaque série a son projet
compose (`odoo-qa-18_0`, `odoo-qa-19_0`…), son image (`odoo-qa:18.0`), ses volumes
et sa base (`odoo_qa_18_0`) : deux séries cohabitent, mais pas sur les mêmes ports —
régler `ODOO_HTTP_PORT` / `ODOO_DB_PORT` pour en démarrer deux simultanément.

## Pièges déjà traités dans le stack

- L'image `odoo:19.0` est basée sur **Ubuntu 24.04** : `apt install chromium` n'y
  installe qu'un stub vers le snap. Les tours étaient ignorés silencieusement.
  → le Dockerfile installe le vrai `google-chrome-stable`.
- Sans **`websocket-client`**, `HttpCase` *skippe* tous les tours sans échouer.
  → installé dans l'image, et `odoo-test.sh` traite un test ignoré pour cause de
  dépendance manquante comme un échec.
- Le `ruff.toml` officiel d'Odoo est **plus strict que le code d'Odoo lui-même**
  (61 findings sur `sale_order.py`). `odoo-lint.sh` fait deux passes : une passe
  bloquante sur les règles réellement respectées par le standard, une passe
  « conseil » avec la configuration complète.
- Le conteneur tourne en uid 101 : `stack/artifacts/` est mis en 777 pour que
  Chrome puisse y écrire ses captures.
- Chrome refuse les connexions CDP dont l'`Origin` n'est pas autorisée
  (`--remote-allow-origins=*`), sinon handshake websocket 403.
- **PDF QWeb** : trois pièges cumulés, tous traités par `odoo-pdf.sh` —
  (1) `_render_qweb_pdf` retombe sur du HTML en contexte de test ;
  (2) sans serveur HTTP en marche, wkhtmltopdf ne charge pas les CSS ;
  (3) les bundles d'assets sont produits par le processus **serveur**, donc un
  rendu lancé depuis `odoo shell` référence des URL en 404.
  Le script télécharge le PDF par la route réelle `/report/pdf/<report>/<ids>`.
  Signe qui ne trompe pas : un PDF nu embarque `NimbusSans`, un PDF correct `Lato`.

## Ce que les agents ont réellement à disposition

Tout est **dans le conteneur**, pas sur l'hôte — c'est la réponse à « aucun navigateur
disponible » et « wkhtmltopdf absent » :

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
