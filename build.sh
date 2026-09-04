#!/usr/bin/env bash
# Génère les profils d'agents Claude Code et Codex à partir des rôles partagés.
#
# Source de vérité : roles/*.md et routing.md (+ ODOO19_STYLE_GUIDE.md, qu'ils référencent).
# Cibles :
#   ~/.claude/agents/<nom>.md          — sous-agents Claude Code
#   ~/.codex/skills/<nom>/SKILL.md     — skills Codex
#   ~/.claude/CLAUDE.md                — aiguillage global Claude Code
#   ~/.codex/AGENTS.md                 — aiguillage global Codex
#   ~/.claude/commands/odoo-demande.md — commande d'enchaînement Claude Code
#   ~/.claude/commands/odoo-cloture.md — clôture de lot (recette complète) Claude Code
#   ~/.claude/commands/odoo-retex.md   — retour d'expérience Claude Code
#   ~/.codex/skills/odoo-{feature,lot-close,retex}/ — les mêmes, côté Codex
#   ~/.claude/skills/<nom>/SKILL.md    — skills Claude Code (camptocamp-docs)
#
# Relancer après toute modification d'un rôle ou de routing.md : ./build.sh

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_AGENTS="$HOME/.claude/agents"
CLAUDE_COMMANDS="$HOME/.claude/commands"
CODEX_SKILLS="$HOME/.codex/skills"
CLAUDE_SKILLS="$HOME/.claude/skills"

mkdir -p "$CLAUDE_AGENTS" "$CLAUDE_COMMANDS" "$CODEX_SKILLS" "$CLAUDE_SKILLS"

emit() {
    local slug="$1" role="$2" tools="$3" short="$4" desc="$5" color="${6:-}"

    # --- Claude Code -------------------------------------------------------
    {
        printf -- '---\n'
        printf 'name: %s\n' "$slug"
        printf 'description: %s\n' "$desc"
        [ -n "$tools" ] && printf 'tools: %s\n' "$tools"
        printf 'model: inherit\n'
        [ -n "$color" ] && printf 'color: %s\n' "$color"
        printf -- '---\n\n'
        printf '<!-- Généré par ~/.odoo19-agents/build.sh — ne pas éditer ici.\n'
        printf '     Source : ~/.odoo19-agents/roles/%s.md -->\n\n' "$role"
        cat "$HERE/roles/$role.md"
    } > "$CLAUDE_AGENTS/$slug.md"
    echo "  ✓ $CLAUDE_AGENTS/$slug.md"

    # --- Codex -------------------------------------------------------------
    mkdir -p "$CODEX_SKILLS/$slug"
    {
        printf -- '---\n'
        printf 'name: %s\n' "$slug"
        printf 'description: %s\n' "$desc"
        printf 'metadata:\n'
        printf '  short-description: %s\n' "$short"
        printf -- '---\n\n'
        printf '<!-- Généré par ~/.odoo19-agents/build.sh — ne pas éditer ici.\n'
        printf '     Source : ~/.odoo19-agents/roles/%s.md -->\n\n' "$role"
        cat "$HERE/roles/$role.md"
    } > "$CODEX_SKILLS/$slug/SKILL.md"
    echo "  ✓ $CODEX_SKILLS/$slug/SKILL.md"
}

# Anciens noms (avant le 2026-09-04) : on retire les fichiers générés pour qu'ils
# ne traînent pas dans les sélecteurs à côté des nouveaux.
for old in odoo-functional-reviewer odoo-qa-reviewer odoo-feature odoo-lot-close odoo-cadrage odoo-dev odoo-qa; do
    rm -f "$CLAUDE_AGENTS/$old.md" "$CLAUDE_COMMANDS/$old.md"
    rm -rf "$CODEX_SKILLS/$old"
done

echo "Génération des profils d'agents Odoo…"

# Les profils fonctionnel et QA n'écrivent jamais dans le module, mais ils
# écrivent la revue, la QA et la mémoire du projet (changelog/<lot>/, .odoo-agents/) :
# ils ont donc Write/Edit, et le rôle borne les chemins.
emit "odoo-business-analyst" "functional-review" \
    "Read, Grep, Glob, Bash, Write, Edit" \
    "Avant de coder : cadrer et challenger une demande, écrire la spec" \
    "Analyste fonctionnel contradicteur Odoo (17.0 → saas~19.x, dans la série du projet). À utiliser AVANT tout développement : remonte au problème réel, vérifie dans les sources de la série si le standard ou la base du client couvre déjà le besoin, compare configuration / Studio / code avec leur coût à la migration, remonte contradictions et non-dits (multi-société, droits, reprise de données, modules disparus), pose les questions bloquantes et écrit la spécification avec critères d'acceptation dans le lot. N'écrit pas de code." \
    "blue"

emit "odoo-developer" "implementation" \
    "" \
    "Coder un module custom avec ses tests, dans la série du projet" \
    "Développeur Odoo (17.0 → saas~19.x, dans la série du projet). Écrit ou modifie le code d'un module custom (modèles, vues, sécurité, assets, tests) dans la ligne éditoriale des sources de sa série : ordre des membres, models.Constraint ou _sql_constraints selon la série, Command, api.model_create_multi, <list>, chatter, sécurité livrée avec le code. Livre les tests avec le code, lint des fichiers touchés et tests ciblés avant de rendre." \
    "green"

emit "odoo-tester" "qa-review" \
    "Read, Grep, Glob, Bash, Write, Edit" \
    "Valider un module : lint, install, tests, tours, copie client" \
    "Relecteur et QA Odoo (17.0 → saas~19.x, dans la série du module). Deux modes : QA de tâche (lint des fichiers touchés, install/update, tests ciblés) pendant un lot ouvert, QA de lot (odoo-recette.sh : base neuve, suite complète, tours Chrome headless, désinstallation, mise à niveau sur la copie du client) à la clôture ou sur demande « valide ce module ». Rend un verdict avec anomalies localisées et écrit qa.md, le journal et la fiche projet." \
    "orange"


# --- Aiguillage global ------------------------------------------------------
# Un seul et même texte, injecté dans le fichier d'instructions globales de
# chaque outil. Le bloc est délimité pour pouvoir être remplacé sans écraser
# ce que l'utilisateur aurait ajouté autour.
MARK_START="<!-- odoo19-agents:début — généré par ~/.odoo19-agents/build.sh -->"
MARK_END="<!-- odoo19-agents:fin -->"

inject_routing() {
    local target="$1" heading="$2"
    local tmp; tmp="$(mktemp)"

    if [ -f "$target" ] && grep -qF "$MARK_START" "$target"; then
        # Remplace le bloc existant, préserve le reste du fichier.
        awk -v s="$MARK_START" -v e="$MARK_END" '
            index($0, s) { skip = 1; print "@@BLOC@@" }
            !skip { print }
            index($0, e) { skip = 0; next }
        ' "$target" > "$tmp"
    else
        [ -f "$target" ] && cat "$target" > "$tmp" || : > "$tmp"
        printf '\n@@BLOC@@\n' >> "$tmp"
    fi

    {
        printf '%s\n' "$MARK_START"
        printf '%s\n\n' "$heading"
        cat "$HERE/routing.md"
        printf '\nPour une demande de développement, la chaîne complète est outillée par\n'
        printf 'la commande `/odoo-demande`.\n'
        printf '%s\n' "$MARK_END"
    } > "$tmp.block"

    awk -v blockfile="$tmp.block" '
        /^@@BLOC@@$/ { while ((getline line < blockfile) > 0) print line; next }
        { print }
    ' "$tmp" > "$target"

    rm -f "$tmp" "$tmp.block"
    echo "  ✓ $target"
}

inject_routing "$HOME/.claude/CLAUDE.md" "# Développement Odoo"
inject_routing "$HOME/.codex/AGENTS.md" "# Développement Odoo"

# --- Commandes --------------------------------------------------------------
# emit_command <slug> <role> <argument-hint> <intro> <short> <description>
emit_command() {
    local slug="$1" role="$2" hint="$3" intro="$4" short="$5" desc="$6"

    {
        printf -- '---\n'
        printf 'description: %s\n' "$desc"
        [ -n "$hint" ] && printf 'argument-hint: %s\n' "$hint"
        printf -- '---\n\n'
        printf '<!-- Généré par ~/.odoo19-agents/build.sh — ne pas éditer ici.\n'
        printf '     Source : ~/.odoo19-agents/roles/%s.md -->\n\n' "$role"
        [ -n "$intro" ] && printf '%s\n\n' "$intro"
        cat "$HERE/roles/$role.md"
    } > "$CLAUDE_COMMANDS/$slug.md"
    echo "  ✓ $CLAUDE_COMMANDS/$slug.md"

    mkdir -p "$CODEX_SKILLS/$slug"
    {
        printf -- '---\n'
        printf 'name: %s\n' "$slug"
        printf 'description: %s\n' "$desc"
        printf 'metadata:\n'
        printf '  short-description: %s\n' "$short"
        printf -- '---\n\n'
        printf '<!-- Généré par ~/.odoo19-agents/build.sh — ne pas éditer ici.\n'
        printf '     Source : ~/.odoo19-agents/roles/%s.md -->\n\n' "$role"
        cat "$HERE/roles/$role.md"
    } > "$CODEX_SKILLS/$slug/SKILL.md"
    echo "  ✓ $CODEX_SKILLS/$slug/SKILL.md"
}

emit_command "odoo-demande" "orchestration" \
    "<la demande de développement>" \
    'Demande à traiter : $ARGUMENTS' \
    "Une demande de dev de A à Z : cadrage → code → QA de tâche → journal" \
    "Traite une demande de développement Odoo de bout en bout, dans la série du projet et dans le lot de changelog ouvert (ou en ouvre un) : revue fonctionnelle contradictoire écrite dans le lot, implémentation, QA de tâche sur Odoo local (lint des fichiers touchés, install/update, tests ciblés), puis entrée de journal. La recette complète se joue à la clôture du lot (/odoo-cloture). Avec boucle de reprise."

emit_command "odoo-cloture" "lot-close" \
    "[dossier du lot]" \
    'Lot à clôturer : $ARGUMENTS' \
    "Clôturer le lot : recette complète, captures, guide, README, commit" \
    "Clôture un lot de changelog Odoo : recette complète outillée (base neuve, suite de tests entière, tours, désinstallation, mise à niveau sur la copie du client), recette navigateur et captures, livrables client (guide, communication), README final avec versions lues dans les manifests, message de commit proposé, capitalisation dans le journal. Ne clôture pas si un contrôle est rouge."

emit_command "odoo-retex" "retex" \
    "[période ou projet]" \
    'Périmètre demandé : $ARGUMENTS' \
    "Améliorer le dispositif : leçons des journaux → guide, lint, rôles" \
    "Retour d’expérience sur le dispositif Odoo : relit les journaux de projet, vérifie que le guide et la matrice des séries disent encore vrai au regard des sources, promeut les leçons récurrentes dans LESSONS.md et les traduit en motifs de lint ou en règles de rôle, puis reconstruit les profils."

# --- Skills (même contenu pour Claude Code et Codex) -------------------------
# emit_skill <slug> <role> <description>
emit_skill() {
    local slug="$1" role="$2" short="$3" desc="$4" target
    for target in "$CLAUDE_SKILLS/$slug/SKILL.md" "$CODEX_SKILLS/$slug/SKILL.md"; do
        mkdir -p "$(dirname "$target")"
        {
            printf -- '---\n'
            printf 'name: %s\n' "$slug"
            printf 'description: %s\n' "$desc"
            printf 'metadata:\n'
            printf '  short-description: %s\n' "$short"
            printf -- '---\n\n'
            printf '<!-- Généré par ~/.odoo19-agents/build.sh — ne pas éditer ici.\n'
            printf '     Source : ~/.odoo19-agents/roles/%s.md -->\n\n' "$role"
            cat "$HERE/roles/$role.md"
        } > "$target"
        echo "  ✓ $target"
    done
}

emit_skill "camptocamp-docs" "docs" \
    "Guide utilisateur, changelog, communication client à la charte Camptocamp" \
    "Livrables documentaires Camptocamp pour un client Odoo : guide utilisateur ou de décision (DOCX + PDF à la charte, captures depuis une copie locale restaurée), dossier de changelog d'un lot (README, demande, recette navigateur, communication client). À utiliser dès qu'une intervention doit être documentée, illustrée ou annoncée au client."

# --- Contrôle : Claude et Codex doivent porter le même texte ------------------
echo
for role in functional-review:odoo-business-analyst implementation:odoo-developer qa-review:odoo-tester; do
    slug="${role##*:}"
    if diff -q <(sed '1,/^---$/d' "$CLAUDE_AGENTS/$slug.md" | sed '1,/^---$/d') \
               <(sed '1,/^---$/d' "$CODEX_SKILLS/$slug/SKILL.md" | sed '1,/^---$/d') >/dev/null; then
        echo "  = $slug : Claude et Codex identiques"
    else
        echo "  ≠ $slug : DIVERGENCE Claude / Codex" >&2
    fi
done
echo
echo "Terminé. Sources partagées : $HERE/roles/, $HERE/routing.md, $HERE/ODOO19_STYLE_GUIDE.md"
