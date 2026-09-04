# Agents Odoo — consignes du projet <PROJET>

Ce dépôt est outillé par le dispositif partagé `~/.odoo19-agents/` (Claude Code
et Codex, mêmes rôles, mêmes commandes). Ce fichier dit ce qui est propre au
projet ; le reste est dans le dispositif (`~/.odoo19-agents/README.md`).

## Série et première commande

- Série Odoo cible : **<SERIE>** — lue dans `.odoo-agents/config`, jamais supposée.
- Première commande de toute intervention, avant de lire ou d'écrire du code :

```bash
python3 ~/.odoo19-agents/scripts/odoo_briefing.py .
```

## Comment on travaille ici

| Demande | Commande ou rôle |
|---|---|
| Comprendre, cadrer, « Odoo sait-il faire… » | `odoo-analyst` seul, aucun code |
| Ticket de support, « ça ne marche plus », « l'utilisateur voit… » | `odoo-support` : diagnostic prouvé, contournement, réponse client ; passe la main selon le verdict |
| Développement ou correction | `/odoo-new <demande>` : cadrage → code → QA de tâche → journal, dans la release ouverte |
| Livrer | `/odoo-close` : recette complète, captures, guide, README de release, commit proposé |
| Valider un module | `odoo-tester` seul |
| Remarque à retenir | `/odoo-feedback "<remarque>"` |

- **Release** : toute modification appartient à une release ouverte sous
  `changelog/AAAA-MM-JJ_NN_titre-court/` (marqueur `<!-- release ouverte -->`
  dans son README, `.base` = commit d'ouverture). Une release contient du dev
  et des tickets. Pendant qu'elle est ouverte : lint des fichiers touchés et
  tests ciblés (`odoo-test.sh --quick`). À la clôture : tout est rejoué.
- **Documentation client** (guide, captures, communication) : uniquement à la
  clôture, par `/odoo-close`, ou sur demande explicite.
- **`inbox/`** (ignoré par git) : déposez-y une sauvegarde (`.zip`, `.dump`,
  `.sql`) ou des mails (`.eml`) à l'attention des agents ; le briefing les liste.
- **Mémoire du projet** : `.odoo-agents/PROJECT.md` (relevé + compréhension
  métier, décisions actées, pièges connus) et `.odoo-agents/JOURNAL.md` (une
  entrée de quinze lignes au plus par intervention). À lire par le briefing, à
  compléter à chaque intervention.
- **Données réelles** : copie locale restaurée (`odoo-restore.sh`) ; production
  en lecture seule, toute écriture confirmée par l'humain opération par opération.

## Conventions propres au projet

<!-- À compléter par l'humain ou les agents : langue du code et des libellés,
     composante de version à incrémenter, format des commits, contact client,
     particularités d'hébergement. Ce qui est vide ici suit le dispositif. -->

- Format des commits : `[TAG] module: sujet` (guide § 10) sauf convention
  existante dans l'historique du dépôt.
