#!/usr/bin/env python3
"""Verse un ou plusieurs mails `.eml` (demande du client, ticket) dans une release.

Un mail est une demande d'origine : on le garde tel quel — expéditeur, date, objet,
texte, fil de réponses — et on range ses pièces jointes à côté. Rien n'est
reformulé : une reformulation perd toujours un point.

    odoo_mail.py <fichier.eml> [...] [--release <dossier>] [--section "<titre>"]

Sans --release : affiche le Markdown sur la sortie standard (pour lire un mail
avant de décider). Avec --release : ajoute chaque mail à `<release>/demande.md`
(section `## Mail — <objet> (<date>)`) et dépose les pièces jointes dans
`<release>/pieces/<n>_<nom>`, en les listant sous le mail.

Les pièces jointes qui sont des documents du client (tableurs, contrats, exports)
restent dans `pieces/` mais ne doivent pas être commitées si elles contiennent
des données personnelles ou confidentielles : le script le rappelle en tête de
liste, l'humain décide. Les captures d'écran sont des preuves : elles se
commitent.
"""

from __future__ import annotations

import html
import re
import sys
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

IMAGE_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp")
SENSITIVE_EXT = (".xlsx", ".xls", ".csv", ".docx", ".doc", ".pdf", ".zip", ".sql", ".json")


class _Text(HTMLParser):
    """HTML → texte lisible : paragraphes, listes, sauts de ligne, sans balises."""

    def __init__(self) -> None:
        super().__init__()
        self.out: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script", "head"):
            self._skip += 1
        elif tag in ("br",):
            self.out.append("\n")
        elif tag in ("p", "div", "tr", "h1", "h2", "h3", "h4", "table", "blockquote"):
            self.out.append("\n")
        elif tag == "li":
            self.out.append("\n- ")

    def handle_endtag(self, tag):
        if tag in ("style", "script", "head"):
            self._skip = max(0, self._skip - 1)
        elif tag in ("p", "div", "tr", "h1", "h2", "h3", "h4", "table", "blockquote"):
            self.out.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.out.append(data)


def html_to_text(raw: str) -> str:
    parser = _Text()
    parser.feed(raw)
    text = html.unescape("".join(parser.out))
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def slug(name: str) -> str:
    name = re.sub(r"[^\w.\-]+", "_", name, flags=re.UNICODE).strip("._")
    return name[:80] or "piece"


def render(path: Path, release: Path | None, index: int) -> str:
    with path.open("rb") as fh:
        msg = BytesParser(policy=policy.default).parse(fh)

    subject = msg.get("Subject", "(sans objet)")
    sender = msg.get("From", "?")
    to = msg.get("To", "")
    cc = msg.get("Cc", "")
    try:
        date = parsedate_to_datetime(msg.get("Date")).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        date = msg.get("Date", "?")

    body = msg.get_body(preferencelist=("plain", "html"))
    if body is None:
        text = "(corps vide)"
    else:
        content = body.get_content()
        text = html_to_text(content) if body.get_content_type() == "text/html" else content.strip()

    lines = [f"## Mail — {subject} ({date})", "",
             f"**De** : {sender}  ", f"**À** : {to}  "]
    if cc:
        lines.append(f"**Cc** : {cc}  ")
    lines += [f"**Fichier** : `{path.name}`", "", "```text", text, "```", ""]

    attachments = []
    for part in msg.iter_attachments():
        name = part.get_filename() or f"piece_{part.get_content_type().replace('/', '_')}"
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        attachments.append((name, part.get_content_type(), payload))
    # Images intégrées au HTML (cid:) : ce sont souvent les captures du client.
    for part in msg.walk():
        if part.get_content_type() in IMAGE_TYPES and not part.is_attachment() \
                and part.get("Content-ID"):
            name = part.get_filename() or f"image_{len(attachments) + 1}.{part.get_content_subtype()}"
            payload = part.get_payload(decode=True)
            if payload:
                attachments.append((name, part.get_content_type(), payload))

    if attachments:
        lines.append(f"**Pièces jointes** ({len(attachments)}) — les documents du client "
                     "(tableurs, contrats, exports) ne se commitent pas sans décision de l'humain ; "
                     "les captures d'écran, oui :")
        lines.append("")
        for n, (name, ctype, payload) in enumerate(attachments, start=1):
            target_name = f"{index:02d}_{n:02d}_{slug(name)}"
            flag = " ⚠️ document client" if name.lower().endswith(SENSITIVE_EXT) else ""
            if release is not None:
                pieces = release / "pieces"
                pieces.mkdir(parents=True, exist_ok=True)
                (pieces / target_name).write_bytes(payload)
                lines.append(f"- `pieces/{target_name}` ({ctype}, {len(payload) // 1024} Ko){flag}")
            else:
                lines.append(f"- {name} ({ctype}, {len(payload) // 1024} Ko){flag}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    args = argv[1:]
    release: Path | None = None
    section = ""
    if "--release" in args:
        i = args.index("--release"); release = Path(args[i + 1]).resolve(); del args[i:i + 2]
    if "--section" in args:
        i = args.index("--section"); section = args[i + 1]; del args[i:i + 2]
    files = [Path(a) for a in args]
    if not files or any(not f.is_file() for f in files):
        print(__doc__)
        return 2
    if release is not None and not release.is_dir():
        print(f"release introuvable : {release}", file=sys.stderr)
        return 2

    # Ordre chronologique : le fil se lit du plus ancien au plus récent.
    def when(p: Path):
        try:
            with p.open("rb") as fh:
                return parsedate_to_datetime(BytesParser(policy=policy.default).parse(fh).get("Date"))
        except (TypeError, ValueError, OSError):
            return None
    files.sort(key=lambda p: (when(p) is None, when(p) or 0))

    existing = 0
    if release is not None and (release / "pieces").is_dir():
        existing = len({p.name[:2] for p in (release / "pieces").iterdir()})
    chunks = [render(f, release, existing + i + 1) for i, f in enumerate(files)]
    out = ("\n".join([f"# {section}", ""]) if section else "") + "\n".join(chunks)

    if release is None:
        print(out)
        return 0
    demande = release / "demande.md"
    prefix = demande.read_text(encoding="utf-8") if demande.is_file() else "# Demande\n\n"
    if not prefix.endswith("\n"):
        prefix += "\n"
    demande.write_text(prefix + "\n" + out, encoding="utf-8")
    print(f"{len(files)} mail(s) ajouté(s) à {demande}")
    if (release / "pieces").is_dir():
        print(f"pièces jointes dans {release / 'pieces'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
