# Recette — <sujet du lot>

## Environnement

- Base : `<nom>` sur le stack Docker local (`~/.odoo19-agents/stack`), Odoo <série>
  — <base neuve | copie neutralisée de la sauvegarde du jj.mm.aaaa>.
- Module : `<nom_technique>` `<version>`, <installé sur base neuve | mis à jour sur la copie>.
- Navigateur : Chrome headless <version> (dans le conteneur) — ou Chromium Playwright sur le poste.
- Session : `admin` ; langue de l'interface : <fr_FR / de_CH / en_US> ; fuseau Europe/Zurich.

## Jeu de données

<Les enregistrements créés ou utilisés pour la recette, avec des noms explicitement de
test (« — recette », « (demo) »), et ce qu'ils reproduisent de la situation réelle.>

## Scénario 1 — <parcours principal, automatisé si un tour existe>

| # | Étape | Attendu | Observé |
|---|---|---|---|
| 1 | <Clic / saisie, libellé exact à l'écran> | <ce qui doit se produire> | ✅ |
| 2 | … | … | ✅ |

Signal final : `tour succeeded` — `0 failed, 0 error(s) of 1 tests`.

Contrôle serveur après le parcours : <la valeur persistante vérifiée, pas seulement l'écran>.

## Scénario 2 — <vérification manuelle du résultat métier, rechargement inclus>

- avant : <état> — capture `captures/01_<sujet>_avant.png` ;
- action : <…> ;
- après : <état> — capture `captures/02_<sujet>_apres.png` ;
- après rechargement de la page : <l'état tient>.

## Anomalie découverte pendant la recette

<Ce qui a cassé au premier passage, la cause établie, la correction, le retest. Section à
supprimer si rien n'a été découvert — ne pas l'inventer.>

## Nettoyage

- <Enregistrements de test supprimés / conservés, et pourquoi>.

## Limites de l'environnement

- <Ce que le stack local ne permet pas de vérifier (mail sortant, paiement, imprimante,
  volume de données…) et ce qui reste à faire en staging>.
