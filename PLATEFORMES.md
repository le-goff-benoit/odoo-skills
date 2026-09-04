# Plateformes — ce qui change d'un hébergement à l'autre

> `SERIES_MATRIX.md` dit ce qui change d'une **version** d'Odoo à l'autre.
> Ce fichier dit ce qui change d'un **hébergement** à l'autre : Odoo.sh, Odoo
> Online / SaaS, on-premise et Docker local. Il **fait autorité** sur le guide
> pour tout ce qui touche au déploiement, à la restauration et à l'exploitation.
>
> Les deux axes ne sont pas indépendants : Odoo Online impose sa série. Sur ce
> point, ce fichier renvoie à la matrice et ne la recopie pas.

Chaque affirmation porte sa provenance :

- **[vérifié]** — constaté sur une instance réelle, à la date indiquée.
- **[doc]** — documentation Odoo, non reproduit sur le poste. À confirmer avant
  de s'en servir pour une décision destructive.

---

## Odoo.sh

### Environnement d'une instance

Relevé sur `camptocamp-latitude-cartagene-fclementi`, build 37362345, 2026-09-02.
**[vérifié]**

| | |
|---|---|
| Accès | `ssh <build_id>@<projet>.odoo.com` |
| Utilisateur | `odoo` |
| Base servie | `$PGDATABASE` — l'utiliser plutôt que le nom en dur, il change à chaque build |
| Type de branche | `$ODOO_STAGE` = `production` / `staging` / `development` |
| Série | `$ODOO_VERSION` |
| Sources | `~/src/odoo`, `~/src/enterprise`, `~/src/themes` |
| Dépôt client | `~/src/user` (checkout du dépôt Git de la branche) |
| Filestore | `/home/odoo/data/filestore/$PGDATABASE` |
| Conf | `~/.config/odoo/odoo.conf` |
| Base | `psql -d $PGDATABASE` fonctionne directement, sans identifiants |

### `$ODOO_STAGE` décide si un push détruit la base

**À vérifier avant tout push, y compris un commit vide.**

| Stage | Effet d'un nouveau build |
|---|---|
| `production` | mise à jour des modules **sur la base existante** — données conservées **[vérifié 2026-09-02]** |
| `staging` | nouveau build à partir d'une **copie de la production** — les données saisies sur la branche sont perdues **[doc]** |
| `development` | nouveau build sur une **base vierge** **[doc]** |

Conséquence directe : un commit vide « juste pour relancer un build » est
inoffensif en production et destructeur ailleurs. Lire `$ODOO_STAGE` d'abord.

### Format d'archive accepté à l'import

L'archive doit contenir `dump.sql` **et** `filestore/` **à la racine du zip**.
**[vérifié 2026-09-02]**

Refusé si le filestore manque :

```
Files found in zip archive: ['dump.sql']
ERROR: File of incorrect format, missing filestore, please make sure to either
use the /web/database/manager or the Odoo.sh plain backup format.
```

- Un `filestore/` **vide** suffit quand on ne veut pas embarquer les documents.
- Une archive imbriquée (`monprojet/dump.sql` + `monprojet/filestore/`) est
  refusée : le dossier parent n'est pas toléré.
- L'import se déroule en deux temps, `Restoring database from dump` puis
  `Replacing filestore`. Un échec sur le second laisse **la base correctement
  restaurée** malgré un statut « Finished with error(s) ». Vérifier en base avant
  de conclure à un échec et de tout recommencer.

### Odoo.sh préserve les permissions du zip à l'extraction

**[vérifié 2026-09-02]** Un répertoire extrait avec un mode sans bit `x` rend le
filestore inutilisable : Odoo ne peut plus y créer les sous-dossiers de ses
bundles d'assets, et toutes les pages renvoient 500.

```
PermissionError: [Errno 13] Permission denied: '/home/odoo/data/filestore/<db>/2d'
```

L'import suivant échoue à son tour sur la destination restée non traversable
(`Replacing filestore` → `Permission denied`). Réparation :

```bash
chmod 755 /home/odoo/data/filestore/$PGDATABASE
```

Voir `LESSONS.md` L4 pour la façon de construire l'archive correctement.

### Restauration d'une base migrée : les points de contrôle

Avant de livrer une base issue de la plateforme d'upgrade **[vérifié 2026-09-02]** :

- **`database.is_neutralized = true`** signale un upgrade lancé en mode `test` :
  crons désactivés, serveurs de mail sortants et entrants coupés et remplacés par
  un faux serveur pointant sur l'hôte `invalid`. Convient à une branche de test.
  Pour de la production, relancer l'upgrade en mode `production` plutôt que
  dé-neutraliser à la main.
- **Le compte `admin` (id=2) peut être désactivé** dans la base client, au profit
  de comptes nommés. Sans réactivation, aucun accès administrateur après
  restauration. `__system__` (id=1) est inactif nativement, c'est normal.
- **Les modules restés en état `to upgrade` et absents des sources** ne bloquent
  pas le démarrage mais salissent chaque mise à jour. Les basculer en
  `uninstalled` dans le dump avant import.
- **Extensions Postgres** : un dump 19.0 fait `CREATE EXTENSION vector`. Toute
  cible sans pgvector refuse la restauration.

---

## Reprise de données — commun à tous les hébergements

### Reconstruire des `store_fname` perdus

**[vérifié 2026-09-02]** Odoo nomme ses fichiers de filestore d'après le sha1 du
contenu : `sha[:2] + '/' + sha` — voir `_get_path()` dans
`odoo/addons/base/models/ir_attachment.py`. Tant que la colonne `checksum`
survit, un `store_fname` effacé se recalcule :

```sql
UPDATE ir_attachment
SET store_fname = substr(checksum, 1, 2) || '/' || checksum
WHERE type = 'binary'
  AND (store_fname IS NULL OR store_fname = '')
  AND checksum IS NOT NULL;
```

Sur le cas latitude_cartagane : 20 744 des 20 745 fichiers attendus retrouvés,
28 pièces jointes sans chemin ni checksum donc définitivement perdues.

Deux précautions :

- **Vérifier le schéma dans les sources de la série visée** avant d'appliquer :
  c'est une forme stable de longue date, pas une garantie.
- **Un `store_fname` renseigné ne prouve pas que le fichier existe.** Sur ce même
  cas, 466 des 467 chemins déjà remplis pointaient vers des fichiers absents,
  créés par la plateforme d'upgrade et jamais rapatriés. Comparer aux fichiers
  réellement présents avant de conclure.

---

## Odoo Online / SaaS

La série n'est pas choisie : la plateforme impose la dernière `saas~19.x`, et
celle-ci déplace des règles réputées stables. **Ne pas viser la 19.0.**

Le détail des formes concernées est dans `SERIES_MATRIX.md` § saas~19.x — il n'est
pas recopié ici. Voir aussi `LESSONS.md` L2.

Pas de shell, pas d'accès Postgres, pas de module custom : toute leçon supposant
un `psql` ou un `ssh` ne s'y applique pas.

---

## On-premise et Docker local

**[vérifié 2026-09-02]** Pièges relevés en montant une base restaurée en local :

- **Le `data_dir` déclaré n'est pas toujours celui qu'Odoo utilise.** Sur l'image
  officielle, le filestore réel a été trouvé sous
  `/var/lib/odoo/.local/share/Odoo/filestore/<db>` alors que la conf annonçait
  `/var/lib/odoo`. Vérifier où Odoo écrit réellement avant de réécrire des
  `store_fname` en base.
- **Propriété du volume** : le filestore doit appartenir à l'utilisateur de
  l'image (`101:101` sur `odoo:15.0`).
- **Une base 19.0 exige pgvector** — `postgres:N` nu ne suffit pas, il faut une
  image type `pgvector/pgvector:pgN`.
- La stack d'un projet peut être restée à la série d'origine d'une migration.
  Se fier à `.odoo-agents/config`, pas au `docker-compose.yml`.

---

## Ce que l'outillage fait de la plateforme

- `scripts/odoo-restore.sh` remonte n'importe quelle sauvegarde (zip Odoo.sh ou
  gestionnaire de bases, `.sql`, `.dump`) dans le stack de la bonne série, dépose le
  filestore, neutralise (`odoo neutralize`), remet `admin/admin` et liste les modules
  installés absents du chemin des addons. L'image Postgres du stack embarque pgvector.
- `scripts/odoo_instance.py` (commande `/odoo-env`) déclare les environnements d'un
  projet : métadonnées sans secret dans `<projet>/.odoo-agents/instances.json`
  (commitées, partagées), identifiant et clé dans le trousseau de la personne
  (libsecret ; repli fichier 600 ou `ODOO_INSTANCE_LOGIN`/`SECRET` en SSH), sait télécharger une sauvegarde par `/web/database/backup`
  (on-premise et Docker uniquement) et **refuse toute écriture sur une instance
  `production`** sans confirmation explicite.
- Rien ne lit encore `$ODOO_STAGE` sur Odoo.sh avant un push : c'est le premier
  réflexe à outiller si un second projet Odoo.sh arrive, car c'est le seul point de ce
  fichier dont l'oubli est destructeur.
