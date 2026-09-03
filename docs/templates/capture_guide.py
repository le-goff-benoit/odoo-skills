#!/usr/bin/env python3
"""Gabarit de script de captures pour un guide — données temporaires, parcours, nettoyage.

Copier à côté du générateur, adapter les trois fonctions, lancer :

    ODOO_TEST_DB=<base_restaurée> python3 capture_guide.py

Principes (issus des guides Stucki et RubixComm) :
  - la base est une COPIE LOCALE restaurée (`odoo-restore.sh`), jamais la production ;
  - les enregistrements de démonstration portent des noms réalistes mais reconnaissables
    (« Coaching Workshop — Bern », « Transports publics — recette ») et sont supprimés à la fin ;
  - une capture par idée, recadrée sur la zone utile, numérotée dans l'ordre du parcours ;
  - la langue de l'utilisateur de capture est celle du client.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".odoo19-agents" / "scripts"))
from odoo_capture import OdooCapture  # noqa: E402

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "captures"
LANG = "fr_FR"                      # langue du client : fr_FR, de_CH, en_US…
DEMO_NAMES = ("<Projet démo A>", "<Projet démo B>")


def cleanup(cap: OdooCapture) -> None:
    """Idempotent : supprime ce qu'un passage précédent aurait laissé."""
    ids = cap.rpc("project.project", "search", [["name", "in", list(DEMO_NAMES)]],
                  context={"active_test": False})
    if ids:
        task_ids = cap.rpc("project.task", "search", [["project_id", "in", ids]], context={"active_test": False})
        if task_ids:
            cap.rpc("project.task", "unlink", task_ids)
        cap.rpc("project.project", "unlink", ids)


def create_demo(cap: OdooCapture) -> dict:
    """Le minimum pour montrer la situation réelle — pas un jeu de données complet."""
    ctx = {"tracking_disable": True, "mail_create_nolog": True}
    project_id = cap.rpc("project.project", "create", {"name": DEMO_NAMES[0]}, context=ctx)
    return {"project_id": project_id}


def capture(cap: OdooCapture, demo: dict) -> None:
    page = cap.page
    # 1. L'écran d'entrée, pleine largeur.
    cap.form("project.project", demo["project_id"])
    cap.shot("01_projet_entete.png", clip=".o_form_view .o_form_sheet_bg", padding=4)

    # 2. L'action, puis son retour visible (notification recadrée).
    page.get_by_role("button", name="<Libellé exact du bouton>").click()
    page.wait_for_selector(".o_notification", timeout=15_000)
    cap.shot("02_notification.png", clip=".o_notification_manager", padding=8)

    # 3. Le résultat après rechargement : la preuve que ça tient.
    page.reload()
    page.wait_for_selector(".o_form_view")
    cap.shot("03_resultat.png", clip=".o_form_view .o_form_sheet_bg", padding=4)


def main() -> None:
    with OdooCapture(lang=LANG, out_dir=SHOTS) as cap:
        cleanup(cap)
        demo = create_demo(cap)
        try:
            capture(cap, demo)
        finally:
            cleanup(cap)
    print(f"Captures dans {SHOTS}")


if __name__ == "__main__":
    main()
