# Travailler sur le dispositif lui-même

Ce dépôt n'est pas un projet Odoo : c'est l'outillage des agents (rôles,
référentiel, scripts, stack). L'aiguillage Odoo de `~/.claude/CLAUDE.md` et
`~/.codex/AGENTS.md` ne s'applique pas ici.

## Source unique et génération

- `roles/*.md` et `routing.md` sont la **source unique** des profils, commandes
  et skills. Les fichiers de `~/.claude/agents`, `~/.claude/commands`,
  `~/.claude/skills`, `~/.codex/skills` et les blocs délimités de
  `~/.claude/CLAUDE.md` / `~/.codex/AGENTS.md` sont **générés** par `build.sh` :
  ne jamais les éditer.
- Après toute modification : `./build.sh`, qui vérifie que Claude et Codex
  portent le même texte. Une divergence (`≠`) est un défaut à corriger avant
  de commiter.
- Les noms : rôles `odoo-analyst`, `odoo-developer`, `odoo-tester`,
  `odoo-support` ; commandes `/odoo-new`, `/odoo-close`, `/odoo-feedback` ;
  skill `camptocamp-docs`. Le vocabulaire est « release », pas « lot ».
- Un renommage passe par `build.sh` (liste des anciens noms à retirer) et par
  les `AGENTS.md` des projets qui citent les commandes.

## Référentiel

- `ODOO19_STYLE_GUIDE.md` décrit la 19.0 ; `SERIES_MATRIX.md` fait foi sur ce
  qui change par série ; `PLATEFORMES.md` sur l'hébergement ; `LESSONS.md` est
  la mémoire longue, courte par construction, avec un marqueur `dernier-retex`.
- Toute affirmation sur les sources se vérifie par comptage dans
  `~/odoo-sources/<série>` avant d'être écrite. Pas de règle de mémoire.

## Scripts

- Un script se teste **en bac à sable** : copie d'un projet dans le scratchpad,
  `chmod -R o+rX` pour que l'uid 101 du conteneur lise les fichiers, base par
  module (`odoo_qa_<série>_<module>`) ; jamais sur un projet réel, jamais sur
  une base partagée. Nettoyer les bases de test créées.
- `odoo-test.sh` ne coupe jamais PostgreSQL s'il tournait avant l'appel, et
  traite `invalid module names, ignored` comme un échec.
- Les secrets d'accès aux instances vivent dans le trousseau GNOME via
  `odoo_instance.py` ; rien de tel n'entre dans ce dépôt.

## Livraison

- Commit avec un message en français, impératif, qui dit ce qui change pour les
  agents. `git push origin main` ; sur un autre poste : `git pull` puis
  `./build.sh`.
- Le fichier de mémoire de Claude sur ce dispositif est
  `~/.claude/projects/-home-blegoff/memory/odoo19-agents.md` : le mettre à jour
  quand la structure ou les noms changent.
