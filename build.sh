#!/usr/bin/env bash
# Génère les profils d'agents Claude Code et Codex à partir des rôles partagés.
#
# Source de vérité : roles/*.md et routing.md (+ ODOO19_STYLE_GUIDE.md, qu'ils référencent).
# Cibles :
#   ~/.claude/agents/<nom>.md          — sous-agents Claude Code
#   ~/.codex/skills/<nom>/SKILL.md     — skills Codex
#   ~/.claude/CLAUDE.md                — aiguillage global Claude Code
#   ~/.codex/AGENTS.md                 — aiguillage global Codex
#   ~/.claude/commands/odoo-feature.md — commande d'enchaînement Claude Code
#   ~/.codex/skills/odoo-feature/      — commande d'enchaînement Codex
#
# Relancer après toute modification d'un rôle ou de routing.md : ./build.sh

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_AGENTS="$HOME/.claude/agents"
CLAUDE_COMMANDS="$HOME/.claude/commands"
CODEX_SKILLS="$HOME/.codex/skills"

mkdir -p "$CLAUDE_AGENTS" "$CLAUDE_COMMANDS" "$CODEX_SKILLS"

emit() {
    local slug="$1" role="$2" tools="$3" desc="$4"

    # --- Claude Code -------------------------------------------------------
    {
        printf -- '---\n'
        printf 'name: %s\n' "$slug"
        printf 'description: %s\n' "$desc"
        [ -n "$tools" ] && printf 'tools: %s\n' "$tools"
        printf 'model: inherit\n'
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
        printf '  short-description: %s\n' "$(echo "$desc" | cut -c1-100)"
        printf -- '---\n\n'
        printf '<!-- Généré par ~/.odoo19-agents/build.sh — ne pas éditer ici.\n'
        printf '     Source : ~/.odoo19-agents/roles/%s.md -->\n\n' "$role"
        cat "$HERE/roles/$role.md"
    } > "$CODEX_SKILLS/$slug/SKILL.md"
    echo "  ✓ $CODEX_SKILLS/$slug/SKILL.md"
}

echo "Génération des profils d'agents Odoo 19…"

emit "odoo-functional-reviewer" "functional-review" \
    "Read, Grep, Glob, Bash" \
    "Analyste fonctionnel contradicteur Odoo 19. À utiliser AVANT tout développement : reformule la demande, vérifie dans les sources 19.0 si le standard couvre déjà le besoin, remonte les contradictions et les non-dits (multi-société, droits, reprise de données, modules disparus en 19), pose les questions bloquantes et produit une spécification avec critères d'acceptation. N'écrit pas de code."

emit "odoo-developer" "implementation" \
    "" \
    "Développeur Odoo 19. Écrit ou modifie le code d'un module custom (modèles, vues, sécurité, assets, tests) en respectant la ligne éditoriale des sources 19.0 : ordre des membres, models.Constraint, Domain, Command, api.model_create_multi, <list>, chatter, ir.model.access.csv. Livre les tests avec le code et passe le lint avant de rendre."

emit "odoo-qa-reviewer" "qa-review" \
    "Read, Grep, Glob, Bash" \
    "Relecteur et QA Odoo 19. À utiliser pour valider un module : conformité statique (ruff avec la config Odoo, manifest, XML, sécurité, motifs bannis en 19), puis exécution réelle sur un Odoo 19 local monté via Docker Compose (installation base neuve, mise à jour, désinstallation, tests Python), puis parcours e2e (tours Chrome headless). Rend un verdict avec anomalies localisées."


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
        printf 'la commande `/odoo-feature`.\n'
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

emit_command "odoo-feature" "orchestration" \
    "<la demande de développement>" \
    'Demande à traiter : $ARGUMENTS' \
    "Chaîne Odoo : fonctionnel → dev → QA → capitalisation" \
    "Traite une demande de développement Odoo de bout en bout, dans la série du projet : revue fonctionnelle contradictoire, implémentation, revue de code et QA sur Odoo local (Docker), puis capitalisation dans le journal du projet. Avec boucle de reprise."

emit_command "odoo-retex" "retex" \
    "[période ou projet]" \
    'Périmètre demandé : $ARGUMENTS' \
    "Retour d’expérience : promeut les leçons et corrige le référentiel" \
    "Retour d’expérience sur le dispositif Odoo : relit les journaux de projet, vérifie que le guide et la matrice des séries disent encore vrai au regard des sources, promeut les leçons récurrentes dans LESSONS.md et les traduit en motifs de lint ou en règles de rôle, puis reconstruit les profils."

echo
echo "Terminé. Sources partagées :"
echo "  $HERE/ODOO19_STYLE_GUIDE.md"
echo "  $HERE/routing.md"
echo "  $HERE/roles/"
