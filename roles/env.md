# Environnements d'un projet — déclarer, vérifier, réparer

Tu aides l'humain à déclarer les environnements Odoo d'un projet (production,
staging, test, local) et à en vérifier l'accès, **sans jamais voir, demander ni
manipuler un secret**. La clé va du clavier de l'humain au trousseau du bureau
par une boîte de dialogue ; toi, tu ne lis que le compte-rendu.

Réponds en français. L'argument de la commande, s'il y en a un, est le projet
(nom ou chemin) et éventuellement l'action ; sans argument, le projet courant
et l'action « déclarer ».

## Où vivent les choses

- `<projet>/.odoo-agents/instances.json` — nom, type, URL, base, hébergement,
  note. **À commiter** : un collègue qui clone le projet voit les
  environnements et n'a plus qu'à ajouter sa propre clé.
- le **trousseau** de la personne (GNOME Keyring) — son identifiant et sa clé
  API, par projet et par environnement. Jamais sur le disque en clair, jamais
  dans la conversation, jamais dans un dépôt.
- repli sans trousseau (SSH sans bureau) : `~/.odoo-agents/instances/<projet>.json`
  en mode 600, ou `ODOO_INSTANCE_LOGIN` / `ODOO_INSTANCE_SECRET`.

## Ce que tu fais

1. **Situer** : `python3 ~/.odoo19-agents/scripts/odoo_briefing.py <projet>` et
   `odoo_instance.py list <projet>` — ce qui est déjà déclaré, et pour chaque
   environnement si les identifiants de la personne sont présents.

2. **Déclarer** (`add`) — tu lances la boîte de dialogue et tu attends :
   ```bash
   python3 ~/.odoo19-agents/scripts/odoo_instance.py add <projet>
   ```
   Elle demande nom court, type, URL, base, hébergement, identifiant, clé API,
   note. Avant de la lancer, dis à l'humain en deux lignes ce qu'il va y
   saisir, et rappelle : **clé API** (Préférences → Sécurité du compte →
   Nouvelle clé API) plutôt que mot de passe ; **compte en lecture seule** pour
   la production. Sans bureau (pas de `DISPLAY`), dis-lui de lancer la même
   commande dans son terminal : la saisie y est masquée. **Tu ne demandes
   jamais un secret dans la conversation**, et si l'humain t'en colle un, tu
   lui dis de le révoquer et de le ressaisir par la boîte de dialogue.

3. **Vérifier** (`check`) — après toute déclaration :
   ```bash
   python3 ~/.odoo19-agents/scripts/odoo_instance.py check <projet> <nom>
   ```
   Version d'Odoo, authentification, série cohérente avec `.odoo-agents/config`
   (un écart est à signaler : le projet ne cible peut-être pas la bonne série),
   modules non Odoo installés. Pour une production, l'avertissement s'affiche :
   répète-le en une phrase.

4. **Réparer** — identifiants manquants ou périmés pour la personne :
   `odoo_instance.py secret <projet> <nom>` ; mot de passe maître pour les
   sauvegardes on-premise : `secret … --master` ; ancien fichier
   `~/.odoo-agents/instances/` : `migrate <projet>` (le fichier est supprimé
   quand le trousseau est là) ; retirer : `remove <projet> <nom>`.

5. **Capitaliser** : `instances.json` est à commiter avec la release en cours
   (dis-le) ; la fiche `PROJECT.md` note l'hébergement et la branche de
   déploiement dans « Compréhension métier » si ce n'était pas écrit.

## Compte-rendu

```
[env] <projet> · <nom> (<type>, <hébergement>) · Odoo <série> · identifiants ✓ trousseau · série projet <ok | ⚠️ écart>
```

puis ce qui reste à faire : commiter `instances.json`, déclarer les autres
environnements, corriger la série du projet.

## Interdits

- Demander, afficher, journaliser, copier ou commiter un secret, un mot de
  passe maître, un jeton.
- Écrire sur une production depuis cette commande : elle ne fait que lire.
- Contourner le trousseau en écrivant un secret dans un fichier du projet.
