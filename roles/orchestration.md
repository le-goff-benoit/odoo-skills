# Chaîne de développement Odoo 19

Enchaîne les trois profils dans l'ordre logique sur une demande de développement,
**sans redemander l'autorisation entre les étapes**. La demande à traiter suit cette
consigne (ou est celle que l'utilisateur vient de formuler).

Référentiel commun : `ODOO19_STYLE_GUIDE.md` (19.0), `SERIES_MATRIX.md` (les autres
séries), `LESSONS.md` (les erreurs déjà payées), tous dans
`~/.odoo19-agents/`. Réponds en français.

## Étape 0 — Situer le projet (30 secondes, non négociable)

Le parc de modules est mélangé : 17.0, 18.0, 19.0, saas~19.x. Une chaîne lancée
avec la mauvaise série produit du code qui ne s'installe pas et une QA qui remonte
des anomalies fausses.

```bash
python3 ~/.odoo19-agents/scripts/odoo_series.py <module_ou_projet>
# Pas de fiche projet ? on la crée, elle sert aux trois étapes :
~/.odoo19-agents/scripts/odoo_project_scan.py <racine_du_projet>
```

Lis ensuite `<projet>/.odoo-agents/PROJECT.md` et les dernières entrées de
`JOURNAL.md`. Annonce en une ligne : **projet, série, origine de la série,
modules concernés**. Toutes les étapes suivantes travaillent dans cette série.

Cherche aussi une **copie du client** : sauvegarde dans le projet, base déjà
restaurée (`odoo-stack.sh dbs`), instance déclarée (`odoo_instance.py list`).
Elle sert aux trois étapes (existant en base, reproduction, mise à niveau réelle).
Si elle manque et que la demande touche des données existantes, demande-la à
l'utilisateur dès maintenant — sans bloquer la revue fonctionnelle.

## Étape 1 — Revue fonctionnelle (`odoo-functional-reviewer`)

Applique le rôle `~/.odoo19-agents/roles/functional-review.md`.

Puis **décide, et annonce ta décision** :

| Issue de la revue | Suite |
|---|---|
| Verdict **ÇA EXISTE** — le standard de la série couvre le besoin | **STOP.** Livre la revue, explique la configuration à faire, ne développe pas. |
| Au moins une **question bloquante** | **STOP.** Livre la revue et les questions. N'invente pas la réponse. |
| Contradiction **bloquante** non levable | **STOP.** Livre la revue avec le risque. |
| Spec saine (y compris demande triviale expédiée en une ligne) | **CONTINUE** à l'étape 2. |

Ne t'arrête pas pour une contradiction majeure ou mineure : consigne-la comme
hypothèse retenue dans la spec, et continue.

## Étape 2 — Implémentation (`odoo-developer`)

Applique le rôle `~/.odoo19-agents/roles/implementation.md`, en prenant
la spec de l'étape 1 comme périmètre — ni plus, ni moins.

Le lint doit être vert avant de passer à l'étape 3 :

```bash
~/.odoo19-agents/scripts/odoo-lint.sh <chemin_du_module>
```

## Étape 3 — Revue & QA (`odoo-qa-reviewer`)

Applique le rôle `~/.odoo19-agents/roles/qa-review.md` : lint, puis
exécution réelle sur le stack Docker de la série, puis parcours e2e.

```bash
export ODOO_ADDONS_DIR=<répertoire contenant le module>
~/.odoo19-agents/scripts/odoo-stack.sh build   # une fois par série
~/.odoo19-agents/scripts/odoo-stack.sh up
~/.odoo19-agents/scripts/odoo-test.sh <module> --fresh --update

# Preuves visuelles quand la demande touche l'écran ou un rapport :
~/.odoo19-agents/scripts/odoo-shot.sh <url> --out avant_apres.png
~/.odoo19-agents/scripts/odoo-pdf.sh <report_ref> <ids> --out rapport.pdf
```

Sur un module existant, linte avec `--changed` : la dette antérieure n'est pas le
sujet de cette livraison.

Vérifie explicitement chaque critère d'acceptation de la spec de l'étape 1.

## Étape 3b — Documenter (skill `camptocamp-docs`) quand l'utilisateur voit quelque chose

Si la section « Ce que l'utilisateur verra » de la spec n'est pas vide, la
livraison comprend le dossier `changelog/AAAA-MM-JJ_NN_titre-court/` du projet :
`README.md`, `demande.md`, `tests_navigateur.md` (la recette de l'étape 3),
`captures/`, et — pour un changement d'usage — le guide illustré DOCX + PDF et la
communication client. Applique `~/.odoo19-agents/roles/docs.md` : captures depuis
la copie locale restaurée, jamais depuis la production.

Sans écran modifié, un `README.md` de changelog suffit.

Une chaîne qui ne laisse pas de trace oblige la suivante à tout redécouvrir.

1. **Entrée de journal** dans `<projet>/.odoo-agents/JOURNAL.md` : date, demande,
   ce qui a été fait, verdict QA, ligne **Appris**, ce qui reste ouvert.
2. **Fiche projet** : si le métier ou un piège durable a été éclairci, complète
   `PROJECT.md` (« Compréhension métier », « Décisions actées », « Pièges connus »),
   puis rafraîchis le relevé :
   ```bash
   ~/.odoo19-agents/scripts/odoo_project_scan.py <racine_du_projet>
   ```
3. **Candidate à `LESSONS.md`** : si l'incident dépasse ce projet — une règle
   fausse dans le guide, un motif de lint absent, une confusion de série — dis-le
   explicitement dans le compte-rendu final, section « Reste à faire ». C'est
   `/odoo-retex` qui décide de la promotion.

Cette étape prend deux minutes et ne se saute pas au prétexte que la QA est verte.

## Boucle de reprise

Si la QA remonte des anomalies **bloquantes** : retour à l'étape 2 pour les corriger,
puis nouvelle QA. **Deux reprises au maximum.** Au-delà, arrête et livre l'état réel
avec ce qui reste rouge — ne boucle pas indéfiniment et ne masque pas un échec.

Les anomalies majeures et mineures ne déclenchent pas de reprise : elles sont listées
dans le compte-rendu final pour arbitrage.

## Compte-rendu final

```markdown
# <titre de la demande>

**Projet** <nom> · **série** <X.Y> · **modules** <…>

## 1. Cadrage fonctionnel
<verdict standard, contradictions retenues, hypothèses, hors périmètre>

## 2. Réalisation
<fichiers créés / modifiés, choix techniques notables>

## 3. Validation
<tableau des contrôles QA, résultat des tests et des tours>

## 4. Critères d'acceptation
| Critère | Couvert par | État |

## 5. Reste à faire / arbitrages
<anomalies majeures et mineures non corrigées, angles morts, questions ouvertes>

## 6. Livrables documentaires
<dossier de changelog, guide (pages), communication — ou « aucun écran modifié »>

## 7. Capitalisation
<entrée de journal écrite, sections de PROJECT.md mises à jour, leçon candidate>
```

## Règles

- Annonce l'étape en cours avant de la commencer (`── Étape 2/4 : implémentation`).
- Annonce la série cible dès l'étape 0 et n'en change plus en cours de route.
- Un arrêt aux étapes 1 ou 3 est un résultat légitime, pas un échec : dis pourquoi.
- Ne déclare jamais « testé » ce qui n'a pas été exécuté. Si Docker n'est pas
  disponible, livre les étapes 1 et 2 et dis explicitement que l'étape 3 est partielle.
