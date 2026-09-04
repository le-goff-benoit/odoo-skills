#!/usr/bin/env python3
"""Gabarit de générateur de guide utilisateur Camptocamp — à copier à côté du guide à produire.

Copier dans `<projet>/changelog/<release>/generate_guide.py` (ou `<projet>/docs/scripts/`),
remplacer les textes, lancer :

    python3 generate_guide.py            → guide.docx + guide.pdf + relecture/<page>.png

Le guide est ainsi régénérable : une capture refaite, une phrase corrigée, et l'on relance.
La structure ci-dessous est celle des guides livrés à Stucki et RubixComm ; garder l'ordre,
supprimer les sections sans objet, ne pas ajouter de matrice technique ni d'historique.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".odoo19-agents" / "docs"))
from c2c_docx import SHOT_WIDTH_NARROW, Brand, Cm, Guide, pdf_page_count, pdf_pages_to_png  # noqa: E402

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "captures"            # captures numérotées dans l'ordre du parcours
ASSETS = HERE / "assets"             # logo du client (le logo Camptocamp est fourni)
OUTPUT = HERE / "guide_utilisateur_<sujet>_odoo<série>.docx"

brand = Brand(
    client="<Nom du client>",
    client_logo="<client_logo.png>",     # None si pas de logo fourni
    kind="Guide utilisateur",            # « User guide », « Guide de décision »…
    lang="fr",                           # fr | en | de : langue du client, pas du poste
    subject="<Sujet court>",             # pied de page : © Camptocamp | Client — Sujet
)


def build() -> Guide:
    g = Guide(brand, shots_dir=SHOTS, assets_dir=ASSETS)

    # --- Couverture + synthèse (page 1) -------------------------------------------------
    g.cover(
        "<Titre : ce que le guide permet de faire>",
        "<Sous-titre : les fonctions concernées, dans Odoo N>",
        "<Client> — <jj mois aaaa>",
        comments="<Provenance : déployé en production le … ; rejoué sur la copie locale du …>",
    )
    g.callout(
        "<Ce qui a changé, pourquoi vous l'aviez remarqué, ce que ça donne maintenant. "
        "Cinq lignes au plus, aucun mot technique.>"
    )
    g.heading("Ce que nous avons corrigé le <jj mois aaaa>", 2)
    g.matrix(
        ["Ce que vous observiez", "Ce que nous avons changé", "Statut"],
        [
            ("<symptôme vu par l'utilisateur>", "<effet visible de la correction>", "Déployé"),
            ("<…>", "<…>", "Déployé"),
        ],
        widths=[Cm(5.0), Cm(9.4), Cm(2.7)],
    )
    g.note(
        "Les corrections ont été vérifiées sur la base de production, puis chaque situation a été "
        "rejouée clic par clic sur une copie locale isolée de la sauvegarde du <date>. Les captures "
        "viennent de cette copie, avec des enregistrements temporaires ; rien n'a été ajouté en production."
    )
    g.page_break()

    # --- Une section par fonction : contexte → capture → étapes → tableau → bon à savoir -----
    g.heading("1. <Ce que fait la fonction, en mots d'utilisateur>")
    g.body("<Une ou deux phrases : où elle se trouve, à quoi elle sert.>")
    g.screenshot("01_<ecran>.png", "<Légende : ce que l'on voit, où cliquer.>")
    g.matrix(["Bouton", "Ce qu'il fait"], [("<Libellé exact>", "<effet>")], widths=[Cm(5.2), Cm(11.9)])
    g.heading("Comment l'utiliser", 2)
    g.steps([
        "Ouvrir <menu> puis <sous-menu>.",
        "Cliquer sur <Libellé exact du bouton> dans l'entête.",
        "Une confirmation verte apparaît en haut à droite ; la page se rafraîchit seule.",
    ])
    g.screenshot("02_<notification>.png", "<Légende.>", width=SHOT_WIDTH_NARROW)
    g.callout("<Garde-fou : ce que le système refuse ou protège, et pourquoi c'est une bonne nouvelle.>")
    g.heading("Bon à savoir", 2)
    g.bullets([
        "<Détail utile qui évite une question au support.>",
        "<Cas particulier et comportement attendu.>",
    ])
    g.page_break()

    # --- Point ouvert : la décision qui appartient au client ----------------------------
    g.heading("2. Un point reste ouvert")
    g.body("<La situation, l'effet aujourd'hui, pourquoi ce n'est pas une contrainte technique.>")
    g.matrix(
        ["Décision", "Effet", "Effort"],
        [
            ("<Option A>", "<ce que ça change pour l'utilisateur>", "<30 minutes>"),
            ("<Option B : garder la configuration actuelle>", "<…>", "rien à faire"),
        ],
        widths=[Cm(5.6), Cm(8.8), Cm(2.7)],
    )
    g.callout(
        "<Vérifié le jj mois aaaa : ce qui a été rejoué, sur quelle copie, avec quels cas.>",
        title="Vérification.",
    )
    return g


def main() -> None:
    guide = build()
    docx, pdf = guide.save(OUTPUT, pdf=True)
    pages = pdf_pages_to_png(pdf, HERE / "relecture")
    print(f"{docx}\n{pdf}\n{pdf_page_count(pdf)} pages → relire {len(pages)} images dans {HERE / 'relecture'}")


if __name__ == "__main__":
    main()
