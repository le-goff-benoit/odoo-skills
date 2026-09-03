# Image de test Odoo pour la QA des modules custom.
#
# La série est un argument de build : `ODOO_SERIES=18.0 odoo-stack.sh build`
# construit `odoo-qa:18.0`. Le parc de modules est mélangé (17.0, 18.0, 19.x) et
# un module ne s'installe que sur la série pour laquelle il a été écrit.
#
# Ajouts par rapport à l'image officielle :
#  - google-chrome-stable : requis par HttpCase.start_tour. odoo/tests/common.py
#    ::_find_executable cherche, dans l'ordre, google-chrome / chromium /
#    chromium-browser / google-chrome-stable.
#    ⚠️ L'image odoo:19.0 est basée sur Ubuntu 24.04 (18.0 sur 22.04), où `apt install chromium`
#    n'installe qu'un stub de transition vers le snap (inutilisable en conteneur)
#    et où /usr/bin/chromium-browser existe déjà mais échoue au lancement.
#    On installe donc le vrai paquet Google. Odoo passe lui-même --no-sandbox,
#    --disable-dev-shm-usage et --disable-gpu.
#  - websocket-client : sans lui, HttpCase SKIPPE silencieusement tous les tours.
#  - ruff : lint avec la configuration officielle d'Odoo.
#  - poppler / python-docx / openpyxl / pypdf : dépendances courantes des customs.
ARG ODOO_SERIES=19.0
FROM odoo:${ODOO_SERIES}

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        fonts-liberation \
        poppler-utils \
        wget \
    && wget -qO /tmp/google-chrome.deb \
        https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y --no-install-recommends /tmp/google-chrome.deb \
    && rm -f /tmp/google-chrome.deb \
    && rm -rf /var/lib/apt/lists/* \
    && google-chrome --version

RUN pip3 install --no-cache-dir --break-system-packages \
        ruff \
        websocket-client \
        python-docx \
        openpyxl \
        pypdf

USER odoo
