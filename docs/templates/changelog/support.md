# Ticket #NNNN — <symptôme en une ligne>

**Reçu le** <jj.mm.aaaa> de <auteur> · **projet** <nom> · **série** <X.Y> ·
**version en production** <lue par l'instance, ou « non déclarée »> · **dépôt** <version du manifest>

## Ce que l'utilisateur observe

<Le ticket tel quel est dans demande.md. Ici : le symptôme reformulé en une phrase,
avec l'enregistrement concerné (nom, identifiant) et le parcours suivi.>

## Reproduction

- Production (lecture seule, <date/heure>) : <état constaté, identifiants>.
- Copie locale `<base>` (sauvegarde du <date>) : <reproduit / non reproduit>, avec le compte <login>.
- <Ce qui distingue production et copie, si non reproduit.>

## Cause

**<USAGE | CONFIGURATION | DONNÉES | BUG CUSTOM | BUG STANDARD | ÉVOLUTION DÉGUISÉE>**

<La cause en deux phrases, avec la preuve : identifiant, ligne de log, `fichier.py:ligne`,
valeur en base.>

Pistes écartées :

- <piste> — <preuve qui l'écarte>.

## Impact et gravité

- Enregistrements touchés : <n> · utilisateurs : <n> · depuis : <date>.
- Effet : <comptable, légal, opérationnel — ou aucun>.
- Gravité : **<bloquant | majeur | mineur>**.

## Contournement immédiat

<Ce que l'utilisateur peut faire dès maintenant — ou « aucun ».>

## Suite

- <Réponse seule · réparation de données (prouvée sur la copie : avant <n>, après <n>) à
  confirmer pour la production · correction de code : test rouge `tests/test_support_NNNN.py`,
  point de la release, `/odoo-new` étape 2 · évolution : passage à l'analyste.>

## Réponse au client (brouillon)

Bonjour <Prénom>,

<Ce que vous observiez, ce que c'était, ce que vous pouvez faire maintenant, ce qui sera
corrigé et quand. Dix lignes, sans jargon. Jamais envoyé par l'agent.>

<Prénom>
