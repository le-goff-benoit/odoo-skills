#!/usr/bin/env python3
"""Capture d'écran authentifiée d'une page Odoo — s'exécute DANS le conteneur odoo.

Pilote le Chrome headless de l'image via le Chrome DevTools Protocol : ouvre
/web/login, s'authentifie, navigue vers la page demandée, attend un sélecteur,
puis écrit un PNG dans /mnt/artifacts.

Paramètres par variables d'environnement (posés par odoo-shot.sh) :
    SHOT_URL       chemin ou URL complète  (ex. /odoo/sales)
    SHOT_DB        base de données
    SHOT_LOGIN     identifiant             (défaut admin)
    SHOT_PASSWORD  mot de passe            (défaut admin)
    SHOT_OUT       nom du fichier PNG      (défaut shot.png)
    SHOT_WAIT      sélecteur CSS à attendre (défaut .o_action_manager, body)
    SHOT_WIDTH / SHOT_HEIGHT   viewport    (défaut 1920x1080)
    SHOT_FULL      "1" pour capturer toute la hauteur de page
    SHOT_TIMEOUT   secondes                (défaut 30)
"""

import base64
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

import requests
import websocket

BASE = "http://127.0.0.1:8069"
ARTIFACTS = pathlib.Path("/mnt/artifacts")

URL = os.environ.get("SHOT_URL", "/odoo")
DB = os.environ.get("SHOT_DB", "")
LOGIN = os.environ.get("SHOT_LOGIN", "admin")
PASSWORD = os.environ.get("SHOT_PASSWORD", "admin")
OUT = os.environ.get("SHOT_OUT", "shot.png")
WAIT = os.environ.get("SHOT_WAIT", "")
WIDTH = int(os.environ.get("SHOT_WIDTH", "1920"))
HEIGHT = int(os.environ.get("SHOT_HEIGHT", "1080"))
FULL = os.environ.get("SHOT_FULL", "") == "1"
TIMEOUT = float(os.environ.get("SHOT_TIMEOUT", "30"))


class Chrome:
    """Client CDP minimal : une connexion websocket, des commandes numérotées."""

    def __init__(self, width, height):
        self.profile = tempfile.mkdtemp(suffix="_shot_chrome")
        self.proc = subprocess.Popen(
            [
                "google-chrome",
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--hide-scrollbars",
                "--force-device-scale-factor=1",
                f"--window-size={width},{height}",
                f"--user-data-dir={self.profile}",
                "--remote-debugging-port=0",
                # Chrome refuse les connexions CDP dont l'Origin n'est pas listée.
                "--remote-allow-origins=*",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.port = self._wait_for_port()
        self.ws = websocket.create_connection(self._page_ws_url(), timeout=TIMEOUT)
        self._id = 0
        self.send("Page.enable")
        self.send("Runtime.enable")

    def _wait_for_port(self):
        port_file = pathlib.Path(self.profile) / "DevToolsActivePort"
        deadline = time.time() + 20
        while time.time() < deadline:
            if port_file.exists():
                content = port_file.read_text().splitlines()
                if content and content[0].strip().isdigit():
                    return int(content[0].strip())
            if self.proc.poll() is not None:
                raise RuntimeError("Chrome s'est arrêté au démarrage")
            time.sleep(0.1)
        raise RuntimeError("Chrome n'a pas ouvert de port de débogage")

    def _page_ws_url(self):
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                targets = requests.get(f"http://127.0.0.1:{self.port}/json", timeout=5).json()
            except requests.RequestException:
                time.sleep(0.2)
                continue
            for target in targets:
                if target.get("type") == "page":
                    return target["webSocketDebuggerUrl"]
            time.sleep(0.2)
        raise RuntimeError("aucune page Chrome disponible")

    def send(self, method, **params):
        self._id += 1
        message_id = self._id
        self.ws.send(json.dumps({"id": message_id, "method": method, "params": params}))
        deadline = time.time() + TIMEOUT
        while time.time() < deadline:
            message = json.loads(self.ws.recv())
            if message.get("id") == message_id:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result", {})
        raise TimeoutError(f"pas de réponse à {method}")

    def evaluate(self, expression):
        result = self.send(
            "Runtime.evaluate", expression=expression, awaitPromise=True, returnByValue=True
        )
        return result.get("result", {}).get("value")

    def navigate(self, url):
        self.send("Page.navigate", url=url)
        self.wait_for("document.readyState === 'complete'")

    def wait_for(self, expression, timeout=None):
        deadline = time.time() + (timeout or TIMEOUT)
        while time.time() < deadline:
            try:
                if self.evaluate(expression):
                    return True
            except RuntimeError:
                pass
            time.sleep(0.25)
        return False

    def close(self):
        try:
            self.ws.close()
        finally:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def main():
    target = URL if URL.startswith("http") else BASE + (URL if URL.startswith("/") else "/" + URL)
    login_url = f"{BASE}/web/login" + (f"?db={DB}" if DB else "")

    chrome = Chrome(WIDTH, HEIGHT)
    try:
        chrome.navigate(login_url)
        # Le formulaire porte déjà son csrf_token : on le soumet tel quel.
        chrome.evaluate(
            "(() => {"
            f"  const l = document.querySelector('input[name=login]');"
            f"  const p = document.querySelector('input[name=password]');"
            "   if (!l || !p) { return false; }"
            f"  l.value = {json.dumps(LOGIN)}; p.value = {json.dumps(PASSWORD)};"
            "   l.form.submit(); return true;"
            "})()"
        )
        if not chrome.wait_for("!document.querySelector('input[name=password]')"):
            print("ERREUR : authentification échouée (formulaire toujours affiché)", file=sys.stderr)
            return 1

        chrome.navigate(target)
        selector = WAIT or ".o_action_manager"
        if not chrome.wait_for(f"!!document.querySelector({json.dumps(selector)})", timeout=15):
            if WAIT:
                print(f"ERREUR : sélecteur absent après attente : {WAIT}", file=sys.stderr)
                return 1
            # Page non-backend (portail, rapport HTML) : on se rabat sur <body>.
            chrome.wait_for("!!document.body", timeout=5)
        # Laisser les rendus asynchrones (OWL, images) se poser.
        time.sleep(1.5)

        params = {"format": "png"}
        if FULL:
            params["captureBeyondViewport"] = True
        data = chrome.send("Page.captureScreenshot", **params)["data"]

        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        out_path = ARTIFACTS / OUT
        out_path.write_bytes(base64.b64decode(data))
        title = chrome.evaluate("document.title") or ""
        print(f"OK {out_path}  ({out_path.stat().st_size} octets)  titre={title!r}")
        return 0
    finally:
        chrome.close()


if __name__ == "__main__":
    sys.exit(main())
