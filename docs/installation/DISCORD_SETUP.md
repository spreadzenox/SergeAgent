# Discord : serveur privé + bot

Le bot envoie chaque ticket en **message privé à chaque administrateur**
de Serge (décisions Q85 et Q86). La base est la vérité : la carte du
ticket, avec ses boutons, est la même chez tous. Dès qu'un administrateur
répond (sur Discord ou dans Mission Control), le ticket est tranché pour
tous : sa carte est mise à jour chez chacun, boutons morts, avec qui l'a
tranché. Aucun LLM ne décide.

## 1. Serveur privé (5 min)

1. Crée un serveur privé : les administrateurs de Serge et le bot. Le bot
   ne peut écrire en message privé qu'à une personne qui partage un
   serveur avec lui.
2. Active le **mode développeur** (Réglages → Avancés), puis clic droit →
   **copier l’identifiant** sur : le serveur et ton compte.

Il n'y a plus de salon à créer : les tickets ne passent plus par un
forum, un salon des urgences ou un salon du résumé.

## 2. Application + bot (portail développeur)

1. [Applications](https://discord.com/developers/applications) → New
   Application → onglet **Bot** → Reset Token → **copie le token**
   (il ne s’affichera plus ; il part dans le sidecar, jamais dans git).
2. Aucune **Privileged Gateway Intent** n'est nécessaire : le bot ne lit
   ni les messages ni les réactions, seulement les clics sur ses boutons
   et les fenêtres de saisie.
3. Onglet **OAuth2 → URL Generator** : scope `bot`, permission minimale
   Send Messages → ouvre l’URL → ajoute au serveur privé.

## 3. Kit (wizard)

- `features.discord = true` → le wizard demande **2 identifiants**
  (`[discord]` du TOML, pas secrets) : le serveur, et ton compte, qui
  devient le premier administrateur au premier démarrage du bot. Puis le
  **token bot** à l’étape secrets (sidecar chiffré →
  `secrets/discord-bot-token`, 0600).
- Les autres administrateurs s'ajoutent dans Mission Control, page
  Décisions, par leur identifiant Discord.
- Vérifie : `serge/discord/cli.py verify` (token + username, rien d’autre).
- Le service `serge-discord-bot` démarre avec l’instance (boucle gateway
  + messages privés, reconnect backoff).

## 4. Tests live-prudents

`.env.test` : `SERGE_TEST_DISCORD_CHANNEL*` + `SERGE_TEST_DISCORD_BOT_TOKEN`
(bot invité sur le serveur **test**). `tests/test_live_discord.py` :
verify → nom du canal → send/edit/delete (rien ne persiste, cap 6).

## 5. Règles d’usage

- Seuls les administrateurs en base peuvent agir ; un autre compte reçoit
  un refus. Jamais de secret ni de donnée sensible dans Discord.
- Boutons = actes (idempotents, double-clic = 1 acte). Un bouton qui
  demande un texte (« Éditer », « Réponse libre », « Discuter », « Autre »
  d'un choix) ouvre une fenêtre de saisie, rattachée au ticket. Un message
  libre n'est pas lu.
- Les tickets partent tout de suite, à toute heure, avec notification.
- Fiche architecture : [`MISSION_CONTROL.md`](../MISSION_CONTROL.md#discord).
