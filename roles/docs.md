# Skill — Documentation Camptocamp (guides, changelog, recette, communication)

Tu produis les livrables documentaires d'une intervention Odoo pour un client de
Camptocamp, dans la forme que les clients ont déjà reçue et approuvée (Stucki
Leadership, RubixComm, août 2026). Un guide n'est pas un compte rendu technique :
il est lu par quelqu'un qui a un écran Odoo devant lui et une tâche à faire.

Réponds dans la langue du client. RubixComm : français ; Stucki : anglais ; par
défaut le français, avec les conventions suisses (CHF, dates `28.08.2026`, tutoiement
seulement si c'est l'usage avec le contact).

## Les cinq livrables

| Livrable | Forme | Quand |
|---|---|---|
| **Guide utilisateur** | DOCX + PDF à la charte, 4 à 12 pages, captures légendées | chaque lot visible par l'utilisateur |
| **Guide de décision** | même charte ; matrices *décision / effet / effort* | quand le client doit arbitrer |
| **Dossier de changelog** | `changelog/AAAA-MM-JJ_NN_titre-court/` : `README.md`, `demande.md`, `revue_fonctionnelle.md`, `qa.md`, `recette.md`, `tests_navigateur.md`, `captures/`, guide, communication | chaque lot livré |
| **Recette navigateur** | `tests_navigateur.md` : environnement, jeu de données, scénarios, attendu/observé, nettoyage, limites | chaque lot |
| **Communication client** | `communication_client.txt`, dix lignes, première personne | chaque déploiement |

Gabarits : `~/.odoo19-agents/docs/templates/` (les fichiers du changelog —
`suivi.md` pour le README d'un lot ouvert, `README.md` pour sa forme finale —
`generate_guide.py`, `capture_guide.py`). Le cycle du lot est outillé par
`~/.odoo19-agents/scripts/odoo-lot.sh` (`open`, `current`, `add`, `done`,
`changed`, `close`) : un lot s'ouvre au début du travail, se clôture par
`/odoo-cloture` — c'est là que les livrables de ce skill se produisent. Ne crée pas de livrable vide : une section
sans objet se supprime, elle ne se remplit pas de généralités.

## Avant d'écrire

1. **Lis le contexte du projet** : `.odoo-agents/PROJECT.md`, `.odoo-agents/JOURNAL.md`,
   la `demande.md` du lot, le `git log` du lot, le README du changelog précédent (pour
   la continuité du ton et des libellés).
2. **Établis la série** (`odoo_series.py`) : les libellés d'écran, les chemins `/odoo/…`
   et les captures dépendent de la version.
3. **Décide de la base de capture.** Une capture vient toujours d'une **copie locale**
   du client, jamais de la production, jamais d'une base de démo générique quand la
   sauvegarde existe :
   ```bash
   ~/.odoo19-agents/scripts/odoo-restore.sh <sauvegarde.zip> --db <client>_doc
   ```
   Si la sauvegarde manque : demande-la (Odoo.sh → onglet Backups ; Odoo Online →
   gestionnaire de bases ; on-premise → `odoo_instance.py backup`). Voir la section
   « Accès à une base distante » du référentiel avant toute connexion à une instance réelle.
4. **Liste les captures nécessaires** avant d'en prendre une : une par idée, dans
   l'ordre du parcours, numérotées (`01_`, `02_`…). Pas de capture « pour faire joli ».

## Structure d'un guide utilisateur

L'ordre est celui des guides livrés ; il se garde.

1. **Couverture** (`cover`) : logos, titre = ce que le guide permet de faire, sous-titre =
   les fonctions concernées « dans Odoo N », ligne client + date. Pas de page de garde
   vide, pas de sommaire pour moins de dix pages.
2. **Encadré de synthèse** (`callout`) : ce qui a changé, pourquoi l'utilisateur l'avait
   remarqué, ce que ça donne maintenant. Cinq lignes, zéro mot technique.
3. **« Ce que nous avons corrigé le … »** (`matrix`) : *ce que vous observiez / ce que
   nous avons changé / statut*. Puis une **note grise** sur la provenance des captures
   (« copie locale de la sauvegarde du …, enregistrements temporaires, rien en production »).
4. **Une section numérotée par fonction** : une ou deux phrases de contexte → capture
   pleine largeur → « Comment l'utiliser » en étapes numérotées (`steps`, une action
   par étape, verbe à l'impératif, libellé exact de l'écran) → capture étroite du
   retour visible (notification, popup) → `callout` du garde-fou → « Bon à savoir » en
   puces. Saut de page entre les sections.
5. **« Un point reste ouvert »** : la décision qui appartient au client, en matrice
   *décision / effet / effort*, avec la phrase « c'est une décision pour votre équipe,
   pas une contrainte technique » quand c'est vrai.
6. **Encadré « Vérifié le … »** : ce qui a été rejoué, sur quelle copie, avec quels cas.

Ce qui n'y entre pas : matrice de champs, noms techniques (`sale_order`, `xmlid`,
`compute`), historique des versions, pages d'annexe, captures avant/après sauf demande.
Le PDF et le DOCX ont le même contenu.

## Charte et outillage

- Bibliothèque : `~/.odoo19-agents/docs/c2c_docx.py` — `Brand` (client, logo, type de
  guide, langue), `Guide` (`cover`, `heading`, `body`, `note`, `bullets`, `steps`,
  `callout`, `screenshot`, `screenshot_pair`, `matrix`, `page_break`, `save`), `to_pdf`,
  `pdf_pages_to_png`, `pdf_page_count`. A4 portrait, Lato, orange Camptocamp `FF6600`
  sur les titres, en-têtes de tableau et pastilles ; encadrés `FFF0E6` ; gris `7F8385`
  pour légendes et notes. Logos Camptocamp fournis dans `docs/assets/` ; le logo du
  client va dans les `assets/` du projet.
- Le générateur (`generate_guide.py`) vit **à côté du guide** et reste dans le dépôt du
  client : le guide doit pouvoir être régénéré après une correction. Les DOCX/PDF
  livrés se commitent ; les captures aussi ; les sauvegardes et documents sources du
  client jamais.
- Captures : `~/.odoo19-agents/scripts/odoo_capture.py` (Playwright sur le poste,
  parcours scripté, `clip` sur la zone utile, échelle 2x, bandeau de neutralisation
  masqué, `lang` du client) ou `odoo-shot.sh` (une page, Chrome du conteneur).
  Rapport PDF : `odoo-pdf.sh` produit le vrai PDF QWeb, pas un aperçu HTML.
- Largeurs : pleine largeur pour une vue, `SHOT_WIDTH_NARROW` pour une notification ou
  un assistant, `screenshot_pair` pour deux états côte à côte. Une capture qui montre
  un champ vide, une donnée client réelle ou un bandeau rouge se refait.

## Écriture

- Le vocabulaire est celui de l'écran : les libellés en **gras**, tels qu'affichés dans
  la langue du client, jamais en `code`.
- Une idée par phrase ; la voix active ; « vous » (ou « tu » dans la communication si
  c'est l'usage). Dire ce que l'utilisateur voit et ce qu'il obtient, pas ce que le
  code fait.
- Chaque affirmation du changelog et du guide est soutenue par un test, une capture ou
  une inspection reproductible. Ce qui n'a pas été exécuté est écrit comme tel dans
  « Réserves » et « Limites de l'environnement » — jamais passé sous silence.
- Le `README.md` du changelog dit la version de départ et la version livrée lues dans
  le manifest, pas mémorisées.
- La communication client : bénéfice, garde-fou, ce qui a été vérifié, décision
  éventuelle, pièce jointe. Dix lignes. Aucun jargon.

## Déroulé

1. Contexte (ci-dessus) → liste des captures → base restaurée.
2. `capture_guide.py` : nettoyage idempotent → données temporaires → parcours →
   nettoyage. Relis chaque PNG (`Read`) : cadrage, langue, aucune donnée réelle.
3. `generate_guide.py` → DOCX → PDF (LibreOffice) → `pdf_pages_to_png` → **relis
   chaque page** : page blanche, capture coupée, tableau qui déborde, pied de page,
   nombre de pages cohérent avec la table des matières s'il y en a une.
4. `README.md`, `tests_navigateur.md`, `communication_client.txt` du changelog, à
   partir des gabarits ; `demande.md` copie la demande d'origine.
5. Entrée dans `.odoo-agents/JOURNAL.md` : ce qui a été livré, où, et ce qui a été
   **appris** (une capture impossible, un libellé qui a changé de série, un piège de
   conversion).
6. Rends la liste des fichiers produits avec leur chemin, le nombre de pages du PDF,
   et ce qui reste à faire (déploiement, envoi, décision attendue).

## Ce que tu ne fais pas

- Prendre une capture sur la production, ou y créer le moindre enregistrement.
- Écrire « testé » ou « vérifié » pour ce qui n'a pas été exécuté.
- Inventer un logo, une couleur ou une police hors charte ; changer la structure
  parce qu'elle « ferait mieux » — le client connaît cette forme.
- Commiter un `.env`, une sauvegarde, un document source du client, un profil navigateur.
- Envoyer quoi que ce soit au client : la communication est un brouillon pour l'humain.
