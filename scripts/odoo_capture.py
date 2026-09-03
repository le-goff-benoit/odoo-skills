#!/usr/bin/env python3
"""Captures d'écran Odoo pour la documentation — Playwright sur le poste, contre le stack QA.

Complète `odoo-shot.sh` (une page, Chrome du conteneur) pour les besoins d'un guide :
parcours scripté (clics, saisies, assistants), recadrage sur un élément, échelle 2x
pour des images nettes, bandeau de neutralisation masqué, langue de l'utilisateur.

Ligne de commande — une capture :

    odoo_capture.py /odoo/action-project.open_view_project_all --db stucki_test --out 01_projets.png
    odoo_capture.py "/odoo/sales/12" --clip ".o_form_view .o_form_sheet" --out 02_devis.png
    odoo_capture.py /odoo/project --lang fr_FR --size 1600x900 --full --out 03.png

Bibliothèque — un parcours :

    from odoo_capture import OdooCapture
    with OdooCapture(db="stucki_test", lang="en_US") as cap:
        project_id = cap.rpc("project.project", "create", {"name": "Demo — Bern"})
        cap.goto(f"/odoo/project/{project_id}", wait=".o_form_view")
        cap.page.get_by_role("button", name="Add Coordination Tasks").click()
        cap.page.wait_for_selector(".o_notification")
        cap.shot("02_notification.png", clip=".o_notification_manager")
        cap.rpc("project.project", "unlink", [project_id])

Prérequis sur le poste : `pip install playwright && playwright install chromium`.
La base visée doit tourner sur le stack (`odoo-stack.sh up`, `odoo-restore.sh`).
"""

from __future__ import annotations

import argparse
import os
import sys
import xmlrpc.client
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sys.exit("playwright manquant : pip install playwright && playwright install chromium")

DEFAULT_BASE_URL = f"http://localhost:{os.environ.get('ODOO_HTTP_PORT', '8079')}"
DEFAULT_DB = os.environ.get("ODOO_TEST_DB", "")

# Le bandeau rouge « Database neutralized for testing » ne doit jamais apparaître
# dans un guide. Odoo ne lui donne pas de classe stable : on cache par le texte.
HIDE_BANNER_JS = """
() => {
  for (const el of document.querySelectorAll('body *')) {
    if (el.children.length === 0 && /neutralized for testing/i.test(el.textContent || '')) {
      let node = el;
      for (let i = 0; i < 3 && node.parentElement && node.parentElement !== document.body; i++) {
        node = node.parentElement;
      }
      node.style.display = 'none';
    }
  }
  for (const el of document.querySelectorAll('.o_neutralize_banner, .o_database_neutralized')) {
    el.style.display = 'none';
  }
}
"""


class OdooCapture:
    """Session authentifiée : un navigateur Playwright + un client XML-RPC sur la même base."""

    def __init__(
        self,
        db: str = DEFAULT_DB,
        *,
        base_url: str = DEFAULT_BASE_URL,
        login: str = "admin",
        password: str = "admin",
        size: tuple[int, int] = (1600, 900),
        scale: int = 2,
        lang: str | None = None,
        tz: str = "Europe/Zurich",
        out_dir: Path | str = ".",
        headless: bool = True,
    ):
        if not db:
            raise ValueError("base non précisée : --db ou ODOO_TEST_DB")
        self.db, self.base_url = db, base_url.rstrip("/")
        self.login_, self.password = login, password
        self.size, self.scale, self.lang, self.tz = size, scale, lang, tz
        self.out_dir = Path(out_dir)
        self.headless = headless
        self._pw = self._browser = self._context = self.page = None
        self._uid = None
        self._models = None

    # -- RPC -----------------------------------------------------------------------
    def _connect_rpc(self) -> None:
        common = xmlrpc.client.ServerProxy(f"{self.base_url}/xmlrpc/2/common", allow_none=True)
        self._uid = common.authenticate(self.db, self.login_, self.password, {})
        if not self._uid:
            raise RuntimeError(f"authentification XML-RPC refusée sur {self.db} ({self.login_})")
        self._models = xmlrpc.client.ServerProxy(f"{self.base_url}/xmlrpc/2/object", allow_none=True)

    def rpc(self, model: str, method: str, *args, **kwargs):
        """`execute_kw` ; les kwargs sont passés tels quels (context=…, fields=…, limit=…)."""
        if self._models is None:
            self._connect_rpc()
        return self._models.execute_kw(self.db, self._uid, self.password, model, method, list(args), kwargs)

    def ref(self, xmlid: str) -> int:
        module, name = xmlid.split(".", 1)
        rows = self.rpc("ir.model.data", "search_read",
                        [["module", "=", module], ["name", "=", name]], fields=["res_id"], limit=1)
        if not rows:
            raise RuntimeError(f"identifiant externe introuvable : {xmlid}")
        return rows[0]["res_id"]

    def set_user_lang(self, lang: str) -> None:
        """Langue et fuseau de l'utilisateur de capture : la langue du client, pas celle du poste."""
        if self._models is None:
            self._connect_rpc()
        installed = self.rpc("res.lang", "search_count", [["code", "=", lang]])
        if not installed:
            raise RuntimeError(f"langue {lang} non installée sur {self.db} (Paramètres → Langues)")
        self.rpc("res.users", "write", [self._uid], {"lang": lang, "tz": self.tz})

    # -- navigateur ----------------------------------------------------------------
    def __enter__(self) -> "OdooCapture":
        self._connect_rpc()
        if self.lang:
            self.set_user_lang(self.lang)
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(
            viewport={"width": self.size[0], "height": self.size[1]},
            device_scale_factor=self.scale,
            locale=(self.lang or "fr_FR").replace("_", "-"),
            timezone_id=self.tz,
        )
        self.page = self._context.new_page()
        self._login()
        return self

    def __exit__(self, *exc) -> None:
        for closer in (self._context, self._browser):
            try:
                closer.close()
            except Exception:  # noqa: BLE001
                pass
        if self._pw:
            self._pw.stop()

    def _login(self) -> None:
        self.page.goto(f"{self.base_url}/web/login?db={self.db}", wait_until="domcontentloaded")
        self.page.fill("input[name=login]", self.login_)
        self.page.fill("input[name=password]", self.password)
        self.page.click("button[type=submit]")
        self.page.wait_for_selector(".o_web_client, .o_portal", timeout=60_000)

    def goto(self, path: str, wait: str = ".o_action_manager", timeout: int = 30_000) -> None:
        """Ouvre un chemin (`/odoo/...`) ou une URL complète et attend que la vue soit rendue."""
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        self.page.goto(url, wait_until="domcontentloaded")
        if wait:
            self.page.wait_for_selector(wait, timeout=timeout)
        self.settle()

    def settle(self, ms: int = 600) -> None:
        """Laisse retomber les animations et les requêtes en cours avant une capture."""
        try:
            self.page.wait_for_load_state("networkidle", timeout=5_000)
        except Exception:  # noqa: BLE001
            pass
        self.page.wait_for_timeout(ms)
        self.page.evaluate(HIDE_BANNER_JS)

    def shot(
        self,
        name: str,
        *,
        clip: str | None = None,
        full: bool = False,
        padding: int = 0,
        mask: list[str] | None = None,
    ) -> Path:
        """PNG dans `out_dir`. `clip` recadre sur un sélecteur (formulaire, popup, notification),
        `padding` ajoute une marge autour, `mask` grise des zones (données à ne pas montrer)."""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / name
        self.settle(200)
        masks = [self.page.locator(sel) for sel in (mask or [])]
        if clip:
            target = self.page.locator(clip).first
            target.wait_for(state="visible")
            if padding:
                box = target.bounding_box()
                self.page.screenshot(
                    path=str(path), mask=masks,
                    clip={"x": max(box["x"] - padding, 0), "y": max(box["y"] - padding, 0),
                          "width": box["width"] + 2 * padding, "height": box["height"] + 2 * padding},
                )
            else:
                target.screenshot(path=str(path), mask=masks)
        else:
            self.page.screenshot(path=str(path), full_page=full, mask=masks)
        print(f"  ✓ {path}")
        return path

    def form(self, model: str, res_id: int, wait: str = ".o_form_view") -> None:
        self.goto(f"/odoo/{model.replace('.', '-')}/{res_id}", wait=wait)

    def action(self, xmlid: str, res_id: int | None = None, wait: str = ".o_action_manager") -> None:
        """Ouvre une action par identifiant externe : `/odoo/action-<xmlid>[/<id>]`."""
        self.goto(f"/odoo/action-{xmlid}" + (f"/{res_id}" if res_id else ""), wait=wait)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("path", help="chemin Odoo (/odoo/...) ou URL complète")
    parser.add_argument("--out", default="shot.png", help="fichier PNG (défaut shot.png)")
    parser.add_argument("--db", default=DEFAULT_DB, help="base (défaut $ODOO_TEST_DB)")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--login", default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--lang", help="langue de l'utilisateur de capture, ex. fr_FR, de_CH, en_US")
    parser.add_argument("--wait", default=".o_action_manager", help="sélecteur à attendre")
    parser.add_argument("--clip", help="sélecteur sur lequel recadrer")
    parser.add_argument("--padding", type=int, default=0)
    parser.add_argument("--full", action="store_true", help="toute la hauteur de la page")
    parser.add_argument("--size", default="1600x900", help="viewport LxH (défaut 1600x900)")
    parser.add_argument("--scale", type=int, default=2, help="facteur de netteté (défaut 2)")
    parser.add_argument("--mask", action="append", default=[], help="sélecteur à griser (répétable)")
    args = parser.parse_args(argv)

    width, height = (int(v) for v in args.size.lower().split("x"))
    out = Path(args.out)
    with OdooCapture(
        args.db, base_url=args.base_url, login=args.login, password=args.password,
        size=(width, height), scale=args.scale, lang=args.lang, out_dir=out.parent,
    ) as cap:
        cap.goto(args.path, wait=args.wait)
        cap.shot(out.name, clip=args.clip, full=args.full, padding=args.padding, mask=args.mask)
    return 0


if __name__ == "__main__":
    sys.exit(main())
