# Discord : serveur de Serge + bot

Le bot ouvre un **fil par ticket dans le forum « tickets »** du serveur
de Serge (décision Q88). La base est la vérité : le premier message du fil
est la carte du ticket, avec ses boutons, et il mentionne les
administrateurs de Serge. Dès qu'un administrateur répond (sur Discord ou
dans Mission Control), le ticket est tranché : sa carte est mise à jour,
boutons morts, avec qui l'a tranché, et le fil est archivé. Aucun LLM ne
décide.

## 1. Serveur et forum (5 min)

1. Un serveur privé : les administrateurs de Serge et le bot.
2. Un salon de type **forum** nommé « tickets ». Le bot doit pouvoir y
   **créer des publications**, **envoyer des messages dans les fils** et
   **gérer les fils** (pour archiver un ticket tranché).
3. Active le **mode développeur** (Réglages → Avancés), puis clic droit →
   **Copier l’identifiant** sur : le serveur, le forum « tickets » et ton
   compte.

## 2. Application + bot (portail développeur)

1. [Applications](https://discord.com/developers/applications) → New
   Application → onglet **Bot** → Reset Token → **copie le token**
   (il ne s’affichera plus ; il part dans le sidecar, jamais dans git).
2. Aucune **Privileged Gateway Intent** n'est nécessaire : le bot ne lit
   ni les messages ni les réactions, seulement les clics sur ses boutons
   et les fenêtres de saisie.
3. Onglet **OAuth2 → URL Generator** : scope `bot`, permissions Send
   Messages, Send Messages in Threads, Create Public Threads et Manage
   Threads → ouvre l’URL → ajoute au serveur.

## 3. Kit (wizard) et Mission Control

- `features.discord = true` → le wizard demande **2 identifiants**
  (`[discord]` du TOML, pas secrets) : le serveur, et ton compte, qui
  devient le premier administrateur au premier démarrage du bot. Puis le
  **token bot** à l’étape secrets (sidecar chiffré →
  `secrets/discord-bot-token`, 0600).
- Dans Mission Control, page **Décisions**, section Discord : colle
  l'identifiant du forum « tickets ». Seuls les tickets ouverts après ce
  réglage y ont un fil ; sans forum, les tickets restent dans Mission
  Control.
- Les autres administrateurs s'ajoutent sur la même page, par leur
  identifiant Discord. Ils doivent être sur le serveur.
- Vérifie : `serge/discord/cli.py verify` (token + username, rien d’autre).
- Le service `serge-discord-bot` démarre avec l’instance (la gateway,
  qui répond aux clics, et les fils des tickets, ouverts et mis à jour à
  part ; reconnexion avec attente croissante). Son état est dans l'îlot
  Discord de la page Système.

## 4. Tests live-prudents

`.env.test` : `SERGE_TEST_DISCORD_CHANNEL*` + `SERGE_TEST_DISCORD_BOT_TOKEN`
(bot invité sur le serveur **test**). `tests/test_live_discord.py` :
verify → nom du canal → send/edit/delete (rien ne persiste, cap 6).

## 5. Règles d’usage

- Seuls les administrateurs en base peuvent agir ; un autre membre du
  serveur reçoit un refus. Jamais de secret ni de donnée sensible dans
  Discord.
- Boutons = actes (idempotents, double-clic = 1 acte). Un bouton qui
  demande un texte (« Éditer », « Réponse libre », « Discuter », « Autre »
  d'un choix, « Ma réponse », « Réécrire ») ouvre une fenêtre de saisie,
  rattachée au ticket. Un message libre dans un fil n'est pas lu.
- Les tickets partent tout de suite, à toute heure ; la mention prévient
  les administrateurs.
- Fiche architecture : [`MISSION_CONTROL.md`](../MISSION_CONTROL.md#discord).
