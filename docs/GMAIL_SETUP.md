# Gmail : binaire gog + keyring fichier

Le transport email passe par le CLI `gog` (OpenClaw `gogcli`, API Gmail) :
recherche, lecture, envoi. Sur machine headless (pas de trousseau OS), l'auth
est un **keyring fichier** déverrouillé par `gog.env` (3 variables : backend,
mot de passe, compte) — les tokens OAuth vivent dans le store
`~/.local/share/gogcli/`, jamais dans `gog.env`.

> Alternative sans OAuth (boîte partagée clé en main) :
> [`MAILBOX_SETUP.md`](MAILBOX_SETUP.md) (SMTP/IMAP, presets fournisseurs).

## 1. Binaire (5 min)

1. Télécharge la release [`openclaw/gogcli`](https://github.com/openclaw/gogcli)
   (asset `linux_amd64`, checksum vérifié) → `~/.local/bin/gog`.
2. `gog --version` pour valider.
3. Résolution par le runtime : `SERGE_GOG_BIN` > `PATH` > `/usr/local/bin/gog`
   (override explicite d'abord, défaut codé en dur en dernier).

## 2. Authentification : migrer OU ré-authentifier

### (a) Migrer un store existant (5 min)

Depuis la machine source (fichiers `0600`, ne jamais les exposer) :

```sh
scp -r <source>:~/.local/share/gogcli ~/.local/share/gogcli
scp <source>:~/.config/gogcli/config.json ~/.config/gogcli/config.json
chmod -R go-rwx ~/.local/share/gogcli ~/.config/gogcli
gog auth list && gog auth doctor
```

Si `doctor` échoue (drift de format entre versions), passe en (b).

### (b) Ré-authentifier (propre, ~15 min)

1. Console Google Cloud : client OAuth **Desktop** → télécharge
   `client_secret.json`.
2. `gog auth credentials ~/client_secret.json`
3. `gog auth add <adresse> --services gmail --manual` (colle l'URL dans un
   navigateur, le flow headless ne peut pas ouvrir d'onglet).
4. `gog auth doctor` doit être vert.

## 3. Kit (wizard)

- `features.gmail = true` → le wizard demande `gog_env` (3 lignes, fin =
  ligne vide) → sidecar v2 → `~/.config/openclaw/gog.env` (`0600`).
- L'unit `serge-pipeline.service` charge le fichier (`EnvironmentFile`
  optionnel : sans lui, le service démarre et les workers Gmail échouent
  proprement en `MailError` — jamais silencieux).
- Note : `~/.openclaw/.env` peut en être une copie (convention du gateway
  OpenClaw externe, hors périmètre Serge).

## 4. Tester

```sh
gog gmail search 'newer_than:1d' --max 3 --json
```

Puis le worker `email.poll` via le pipeline (`run-once`) : ingest + dédup
`gmail_id`, erreurs par message ignorées + comptées.

## 5. Dépannage

- `BIN: gog introuvable` → binaire absent (`PATH` ? `SERGE_GOG_BIN` ?).
- `AUTH: gog refusé` → keyring verrouillé : `gog.env` présent ? store migré ?
  `gog auth doctor` pour trancher.
- `API: gog a échoué` → sortie brute tronquée dans le message, relire.

## 6. Sécurité

- `gog.env` contient un **mot de passe** : `0600`, sidecar chiffré, jamais
  dans git, le TOML, Discord ou un chat.
- Tokens : `~/.local/share/gogcli/` en `0600`, migrés par `scp` direct.
