# <Résultat métier de la release, en une ligne>

Release du <jj mois aaaa> : <ce que l'utilisateur obtient de nouveau, en une ou deux phrases,
sans vocabulaire technique>.

## Livraison

- Version de départ : `<série>.x.y.z`.
- Version livrée : `<série>.x.y.z+1`.
- <Point livré 1 : ce que l'utilisateur voit ou peut faire, où (menu, bouton), et le
  comportement par défaut>.
- <Point livré 2>.
- <Garde-fou : ce que le système refuse ou signale, et pourquoi c'est protecteur>.

## Arbitrage notable

<Une décision qui n'allait pas de soi, expliquée avec l'alternative écartée et la raison.
À supprimer si la release n'en comporte aucune.>

## Fichiers

| Fichier | Nature |
|---|---|
| `models/<fichier>.py` | <ce que la modification apporte, en une ligne> |
| `views/<fichier>.xml` | <…> |
| `tests/test_<sujet>.py` | <N> tests |

## Validation

| Contrôle | Résultat |
|---|---|
| Lint (config Odoo <série>, `--changed`) | ✅ 0 erreur |
| Installation base neuve | ✅ |
| Mise à jour `-u` | ✅ |
| Désinstallation | ✅ |
| Tests Python de la release | ✅ N/N |
| Tour navigateur (Chrome headless) | ✅ N/N étapes, `tour succeeded` |
| Logs | ✅ 0 ERROR lié au module |

Détail dans [`recette.md`](recette.md) (protocole outillé) et
[`tests_navigateur.md`](tests_navigateur.md) (recette navigateur). Cadrage dans
[`revue_fonctionnelle.md`](revue_fonctionnelle.md), revues de tâche dans [`qa.md`](qa.md).

## Réserves

<Ce qui est rouge, partiel ou non vérifié, avec la cause établie et ce qui le lèverait.
Ne jamais laisser cette section vide si quelque chose n'a pas été exécuté : écrire
« Aucune » seulement quand c'est vrai.>

## Reste à faire

- <Action en attente, qui la porte, ce qui la déclenche (feu vert, déploiement…)>.
- Déployer cette release en <production / staging>, puis le signaler à <prénom du contact>
  (voir [`communication_client.txt`](communication_client.txt)).
