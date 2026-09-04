# Clôture d'un lot — recette complète et livrables

Un lot de changelog regroupe les tâches d'une même livraison. Pendant qu'il est
ouvert, chaque tâche n'a reçu qu'une QA proportionnée. **La clôture est le
moment où tout est rejoué, une fois, sur l'état exact qui partira** : base
neuve, suite complète, tours, désinstallation, mise à niveau sur la copie du
client, captures, guide, communication. C'est un acte de l'humain — cette
commande ne se lance pas toute seule en fin de `/odoo-demande`.

Réponds en français. Le lot à clôturer suit cette consigne ; sans précision,
c'est le lot ouvert du projet courant.

## Étape 0 — Situer et vérifier que le lot est clôturable

```bash
python3 ~/.odoo19-agents/scripts/odoo_briefing.py <racine_du_projet>
LOT=$(~/.odoo19-agents/scripts/odoo-lot.sh current <racine>)
~/.odoo19-agents/scripts/odoo-lot.sh points "$LOT"
~/.odoo19-agents/scripts/odoo-lot.sh modules "$LOT"      # modules touchés depuis l'ouverture
~/.odoo19-agents/scripts/odoo-lot.sh changed "$LOT"      # fichiers, pour le tableau « Fichiers »
git -C <racine> status --short                           # fichiers non suivis dont le code dépend ?
```

Annonce : **projet, série, lot, points (réalisés / à faire), modules touchés,
copie client disponible ou non.**

Un point encore « à faire » n'empêche pas la clôture : il est marqué
**différé** dans `demande.md` (« Décisions de périmètre ») et retiré de la
livraison. Un point « configuration » (le standard couvrait le besoin) est
livré comme tel : la configuration à faire est décrite dans le README.

Un `__init__.py` qui importe un fichier non suivi par git est un arrêt
immédiat : ce qui part en production est le commit, pas le répertoire.

## Étape 1 — Recette complète, module par module

```bash
export ODOO_ADDONS_DIR=<répertoire contenant les modules>
~/.odoo19-agents/scripts/odoo-recette.sh <module> --lot "$LOT" [--db <copie_client>]
```

Pour chaque module touché. La copie du client est celle du briefing (base
restaurée sur le stack) ; si elle manque, restaure la sauvegarde
(`odoo-restore.sh`) ou, à défaut, demande-la — et écris la réserve.

Le script écrit `$LOT/recette.md` et rend 0 seulement si tout est vert. Lis le
tableau, pas les logs. Il signale aussi :

- **un module sans test** → réserve bloquante pour un lot de code ;
- **une version de manifest qui n'a pas bougé** depuis l'ouverture alors que
  du code a changé → l'incrémenter maintenant (composante convenue avec le
  projet, lue dans le fichier), puis **relancer la recette** : la version
  livrée est celle qui a été testée.

Si un contrôle est rouge : **on ne clôture pas.** Applique le rôle
`~/.odoo19-agents/roles/qa-review.md` (mode lot) pour localiser, puis
`roles/implementation.md` pour corriger, puis recette à nouveau. Deux reprises
au maximum ; au-delà, livre l'état réel et arrête.

## Étape 2 — Recette navigateur et captures

Applique `~/.odoo19-agents/roles/qa-review.md` § Étape 3 : chaque critère
d'acceptation de `revue_fonctionnelle.md` est couvert par un tour, un test HTTP
ou un scénario manuel rejoué **sur la copie du client**, rechargement et
contrôle serveur compris. Résultat dans `$LOT/tests_navigateur.md` (gabarit
`~/.odoo19-agents/docs/templates/changelog/tests_navigateur.md`). Sans
interface concernée, le fichier le dit explicitement, avec les contrôles
réellement exécutés.

Captures finales dans `$LOT/captures/`, numérotées dans l'ordre du parcours,
depuis la copie locale neutralisée — jamais la production.

## Étape 3 — Livrables client (skill `camptocamp-docs`)

Si la section « Ce que l'utilisateur verra » d'au moins un point n'est pas
vide : guide illustré DOCX + PDF à la charte, `communication_client.txt`.
Applique `~/.odoo19-agents/roles/docs.md`. Le générateur du guide reste dans le
lot.

Sans écran modifié : `communication_client.txt` seul si le lot est déployé chez
le client, rien sinon.

## Étape 4 — README final, version, commit proposé

Réécris `$LOT/README.md` dans sa forme finale, d'après le gabarit
`~/.odoo19-agents/docs/templates/changelog/README.md` :

- résultat métier en une ligne, puis « Livraison » point par point (ce que
  l'utilisateur voit ou peut faire) ;
- **versions de départ et livrée lues dans les manifests** (`git show
  $(cat $LOT/.base):<module>/__manifest__.py` pour le départ) ;
- « Fichiers » d'après `odoo-lot.sh changed` ;
- « Validation » recopiée de `recette.md` — chaque ligne correspond à quelque
  chose qui a été exécuté ;
- « Réserves » : tout ce qui est rouge, partiel ou non exécuté, avec la cause.
  Jamais vide par oubli ; « Aucune » seulement si c'est vrai ;
- « Reste à faire » : déploiement, envoi, décision attendue.

`demande.md` : chaque demande d'origine y est, telle quelle ; les décisions de
périmètre (retenu / différé / hors périmètre) sont à jour.

Puis retire le marqueur :

```bash
~/.odoo19-agents/scripts/odoo-lot.sh close "$LOT"
```

Propose le **message de commit** du lot (`[TAG] module: sujet`, guide § 10 ;
un commit par lot, corps = les points livrés). Tu ne commites, ne pousses et ne
déploies pas sans qu'on te le demande.

## Étape 5 — Capitaliser

1. **Journal** : une entrée de lot dans `<projet>/.odoo-agents/JOURNAL.md`,
   quinze lignes au plus — les entrées de tâche existent déjà, celle-ci dit ce
   que la recette complète a révélé et ce qui part.
2. **`PROJECT.md`** : pièges durables, décisions actées, compréhension métier
   acquise pendant le lot. Puis `odoo_project_scan.py <racine>` pour
   rafraîchir le relevé.
3. **Candidats à `LESSONS.md`** : ce qui dépasse ce projet. Compte les entrées
   de journal écrites depuis le dernier retex (`grep -c '^## 20' JOURNAL.md`
   contre la date `dernier-retex` en tête de `LESSONS.md`) : au-delà de dix,
   ou dès qu'une candidate est sérieuse, recommande `/odoo-retex`.

## Compte-rendu final

```markdown
# Clôture — <titre du lot>

**Projet** <nom> · **série** <X.Y> · **lot** `<dossier>` · **modules** <…> · version <a> → <b>

## Recette
<tableau de recette.md, un par module>

## Livrables
<README, tests_navigateur, captures (n), guide (pages), communication — chemins>

## Réserves
<ce qui n'est pas vert ou pas exécuté, et ce qui le lèverait>

## Reste à faire
- commit proposé : `[TAG] module: …`
- déploiement <production / staging>, communication à <contact>
- <n> entrée(s) de journal depuis le dernier retex — /odoo-retex recommandé ou non
```

## Règles

- Ne clôture pas un lot dont la recette est rouge ; dis pourquoi et arrête.
- Ne déclare jamais « testé » ce qui n'a pas été exécuté ; la réserve est un
  résultat légitime.
- La version livrée est celle qui a été testée : tout incrément de version
  après la recette impose de la rejouer.
- Ne lis pas les logs Odoo d'un bloc : `recette.md`, la ligne `RECETTE …`, et
  `grep -n` pour localiser.
