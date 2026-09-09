# Discord : serveur privé + bot (H §2)

Le bot est un **miroir temps réel** des tickets (DB = vérité) : cartes de
décision FR, boutons = actes typés, mentions/slash pour le sens inverse.
Aucun LLM ne décide : il rédige, le déterministe tranche.

## 1. Serveur privé (5 min)

1. Crée un serveur privé (toi seul + le bot).
2. Crée 3 canaux :
   - **Forum** `🎫-tickets-serge` (1 post = 1 ticket),
   - **Texte** `🔴-urgent` (miroir GUICHET/veto/ALERT),
   - **Texte** `📣-digest` (FYI, lecture).
3. Active le **mode développeur** (Réglages → Avancés), puis clic droit →
   **copier l’identifiant** sur : le serveur, les 3 canaux, ton compte.

## 2. Application + bot (portail développeur)

1. [Applications](https://discord.com/developers/applications) → New
   Application → onglet **Bot** → Reset Token → **copie le token**
   (il ne s’affichera plus ; il part dans le sidecar, jamais dans git).
2. **Privileged Gateway Intents** : active **MESSAGE CONTENT INTENT**
   (sans ça, le bot ne lit pas les mentions).
3. Onglet **OAuth2 → URL Generator** : scopes `bot`, permissions
   minimales (View Channels, Send Messages, Create Public Threads,
   Send Messages in Threads, Embed Links, Read Message History,
   Add Reactions) → ouvre l’URL → ajoute au serveur privé.
4. Remets le bot dans les 3 canaux si besoin (permissions par canal).

## 3. Kit (wizard)

- `features.discord = true` → le wizard demande les **5 IDs** (`[discord]`
  du TOML, pas secrets) puis le **token bot** à l’étape secrets
  (sidecar chiffré → `secrets/discord-bot-token`, 0600).
- Vérifie : `serge/discord/cli.py verify` (token + username, rien d’autre).
- Le service `serge-discord-bot` démarre avec l’instance (boucle gateway
  + miroir, reconnect backoff).

## 4. Tests live-prudents

`.env.test` : `SERGE_TEST_DISCORD_CHANNEL*` + `SERGE_TEST_DISCORD_BOT_TOKEN`
(bot invité sur le serveur **test**). `tests/test_live_discord.py` :
verify → nom du canal → send/edit/delete (rien ne persiste, cap 6).

## 5. Règles d’usage

- Canaux **owner-only** (H §10). Jamais de secret/PII dans Discord :
  liens signés expirables pour les écrans sensibles.
- Boutons = actes (idempotents, double-clic = 1 acte). La prose ne
  tranche jamais : en fil, “oui” reçoit un rappel vers les boutons.
- `!` / `--force` / “sans confirmation” = bypass logué + FYI post-hoc.
  La constitution (§14.1a : faux avis, usurpation, spam illégal…)
  **n’est jamais bypassée** (refus avec explication).
- Fiche architecture : [`INTERACTION_ARCHITECTURE.md`](INTERACTION_ARCHITECTURE.md).
