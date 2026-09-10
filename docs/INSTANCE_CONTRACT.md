# Contrat du fichier d’instance Serge

Objectif : **sans le fichier d’instance, Serge ne boot pas.**

Pas de fallback `/home/serge`, pas de « on verra les secrets plus tard »,
pas de processus à moitié monté. Le checkout git n’est pas une instance.

Deux outils, un artefact :

```text
kit (générateur interactif)
    → serge.instance.toml  +  serge.secrets.age
         ↓
serge builder
    → arbre Unix, units, canon vide, secrets injectés
         ↓
kernel
    → boot seulement si SERGE_INSTANCE_FILE + sidecar sont complets
```

Le loader, la barrière de boot, les templates systemd et le générateur
de couple existent dans le kit :

- [`kit/instance_file.py`](../kit/instance_file.py) — parse + gate CLI
- [`systemd/templates/`](../systemd/templates/) + [`kit/units.py`](../kit/units.py)
  — units paramétrés, **pas installés**
- [`scripts/serge-instance-wizard.py`](../scripts/serge-instance-wizard.py)
  — TOML + sidecar ; `--also-mandate` enchaîne le wizard mandat

Le builder existe : [`kit/builder/`](../kit/builder/) (package : guards, seed, secrets, install, telephony, build),
[`bin/serge-builder`](../bin/serge-builder). Il archive un SHA, pose un
canon vide, injecte les secrets en 0600, écrit les units paramétrés.
Le builder **active** les units des features on (`systemctl --user
enable --now`) dès que le dossier units est la session de cet utilisateur.
`--no-enable-units` pour un dry-run. Les chemins live Julien sont refusés
sauf `--confirm-live-instance-id julien-vps`.

`systemd/*.service` à la racine du dossier restent la forme observée
`julien-vps` ; le seed portable est `systemd/templates/`.

Le VPS `julien-vps` tourne encore sur les hardcodes (sinon on l’éteint
avant d’avoir le fichier). Cette branche ne doit pas être merge/installée
sur le live tant que Julien n’a pas son couple TOML+age. Le jour où le
builder pose `SERGE_INSTANCE_FILE` dans les units, le fallback disparaît.

Exemples versionnés : [`schemas/serge.instance.example.toml`](../schemas/serge.instance.example.toml),
[`schemas/serge.instance.schema.json`](../schemas/serge.instance.schema.json),
[`schemas/serge.secrets.manifest.yaml`](../schemas/serge.secrets.manifest.yaml).

## Barrière de boot (fail-closed)

Le kernel refuse de démarrer (`sergectl run-once`, pipeline, dashboards)
si l’un de ces points manque :

1. `SERGE_INSTANCE_FILE` absente, illisible, ou TOML invalide.
2. Sidecar `serge.secrets.age` absent, indéchiffrable, ou incomplet.
3. Une feature à `true` dont **toutes** les clés du manifeste marquées
   `required_when_feature` sont absentes après déchiffrement.
4. Chemins `home` / `system_root` / `policy` absents ou non utilisables.

Conséquence : un clone nu, un laptop sans fichier, un zip de secrets
en clair — **aucun** ne produit un process Serge.

« Complet » veut dire : **100 % de ce que le TOML déclare**. Le produit
kit est **tout ou rien** : toutes les features à token sont `true` par
défaut. Une feature `false` reste un TOML valide pour le loader, mais ce
n’est plus le défaut. `true` sans les clés du manifeste = pas de couple,
pas de builder, pas de boot. Meta-Grok reste `false` (pas de token,
jamais empaqueté).

## Variable unique d’entrée

```text
SERGE_INSTANCE_FILE=/absolute/path/to/serge.instance.toml
```

Tout le reste se dérive. Plus de `ROOT = Path('/home/serge/serge-system')`
comme source de vérité une fois le builder en service.

| dérivé | depuis le TOML |
| --- | --- |
| `SERGE_HOME` | `paths.home` |
| `SERGE_SYSTEM_ROOT` | `paths.system_root` |
| `SERGE_MANDATE_PATH` | `paths.policy` |
| config / secrets dir | `paths.config_root` (défaut `$home/.config/serge`) |
| sidecar | `paths.secrets_age` relatif au TOML, sinon `serge.secrets.age` à côté |
| canon | `$system_root/state/serge.db` |

`SERGE_HOME` seul n’est **pas** suffisant pour booter.

## Kit de génération

Entrée : questions (instance_id, mode, home, features, destinataires age).
CLI : `bin/serge-instance-wizard` (`--answers` JSON, `--allow-plaintext-secrets`
seulement pour tests/sandbox local).

Sortie **uniquement** :

- `serge.instance.toml` — zéro secret
- `serge.secrets.age` — toutes les clés exigées par les features choisies
  (ou `serge.secrets` dotenv si `--allow-plaintext-secrets`)

Le **mandat** est un troisième artefact, produit par
`scripts/serge-mandate-wizard.py` (même forme que `/opt/serge-policy/mandate.yaml`,
identité neutre). Ce n’est pas le mandat Julien. `mode=sandbox` coupe
paiements live et deploy prod.

Le kit refuse d’écrire un couple incomplet. Il ne crée pas le canon, n’installe
pas systemd, ne copie pas les Constitutions, ne touche pas Meta-Grok.

Partage équipe = ces deux fichiers (TOML clair + age chiffré pour des
destinataires nommés). Pas un dossier `~/.config/serge/secrets/` en zip.

## Serge builder

Entrée : le couple produit par le kit (+ checkout git à un SHA).
Sortie : une instance qui boot.

Le builder :

1. Vérifie TOML + age (même règles que le kernel).
2. Crée `system_root` writable (`state/`, `queue/`, `evidence/`, `logs/`,
   `orchestrator/runtime`). Canon **vide** sauf dump explicitement autorisé.
3. Pose le mandat à `paths.policy` (fourni par l’owner, pas celui de prod
   Julien si `instance_id` ≠ `julien-vps`).
4. Injecte les secrets du sidecar aux chemins dérivés (mode 0600).
5. Installe les units **avec** `Environment=SERGE_INSTANCE_FILE=…`.
6. Active les units des features `true` (pipeline, report, ingress,
   Mission Control). Jamais Meta-Grok. `--no-enable-units` pour ne pas
   appeler systemctl.

S’il manque un secret pour une feature on, le builder s’arrête. Il ne
livre pas un Serge « on verra ce soir ».

## `serge.instance.toml`

`schema_version = 1`. Aucune valeur secrète.

Champs obligatoires :

- `instance_id` — unique par déploiement (`julien-vps`, `alice-laptop`, …)
- `mode` — `live` \| `staging` \| `sandbox`
- `paths.home`, `paths.system_root`, `paths.policy`

```toml
[identity]
hostname = "serge-vps"
public_hostname = ""            # obligatoire si phone_sms on
phone_sms_number = ""           # E.164, obligatoire si phone_sms on
phone_voice_number = ""         # E.164 NPV, obligatoire si phone_voice on

[features]                      # défaut kit = tout on sauf metagrok
ingress = true
stripe = true
voice = true
metagrok = false                # pas de token ; pont hôte seulement
gmail = true
mailbox = true                  # SMTP/IMAP confiance (cohabite avec gmail)
discord = true
openclaw = true
owner_ui = true
payments_live = true
phone_sms = true                # SIM + Android, OTP/2FA
phone_voice = true              # trunk SIP NPV, voix commerciale

[llm]
provider = "openrouter"         # la clé est dans le sidecar
referer = ""
t1_model = "xiaomi/mimo-v2.5"                 # rapide/économique
t2_model = "deepseek/deepseek-v4-flash-0731"  # défaut (+ guide)
t3_model = "z-ai/glm-5.3-flash"               # stratège
guide_model = "deepseek/deepseek-v4-flash-0731"

[ingress]
listen = "loopback"             # loopback | privileged
aliases = []

[phone_voice]                   # requis si phone_voice on
sip_server = ""
sip_username = ""
sip_transport = "tls"           # udp | tcp | tls
max_calls_per_day = 50

[mailbox]                       # requis si mailbox on (login + preset)
preset = "infomaniak"           # infomaniak | gmail | fastmail | custom
login = ""                      # adresse complète (mot de passe = sidecar)
smtp_host = ""                  # vide = preset (custom : obligatoire)
smtp_port = 587                 # 587 STARTTLS | 465 SSL
imap_host = ""                  # vide = preset (custom : obligatoire)
imap_port = 993                 # 993 SSL | 143 STARTTLS

[testing]                       # topologie à froid (B4) : N + seuils kill/scale
n_smoke_min = 30                # modifiable via Mission Control uniquement
n_smoke_max = 50                # à froid (0 campagne RUNNING), jamais à chaud
n_full_min = 150
n_full_target = 200
kill_max_positives = 1
scale_min_positives = 5
scale_min_meetings = 2
extend_max = 1
```

Contraintes téléphonie (refusées au load, au wizard et au builder) :

- `phone_voice` ⇒ `phone_sms` (Option B = SIM SMS + trunk, jamais
  VoIP-only), `voice` (clés voix temps réel) avec `sip_server` +
  `sip_username`.
- `phone_sms` ⇒ `ingress` + `public_hostname` non vide (webhook
  `sms.<domaine>` → receiver loopback).
- Numéros E.164 quand la feature est on.

`[llm]` est toujours on : une instance sans provider LLM n’est pas un Serge
qui boot. `openrouter_api_key` est donc **toujours** exigée dans le sidecar.
Les tiers `t1/t2/t3_model` (IDs OpenRouter, recommandations = live Julien)
et `guide_model` (défaut = T2) sont écrits par le wizard ; le builder en
dérive `config_root/llm/slots.json` (CHEAP/DEFAULT/SMART). Détail install :
[`INSTALL.md`](INSTALL.md).

OpenClaw est **on** dans le défaut tout-ou-rien (`browserbase_key` exigé).
Sans la feature, le runtime reste `direct_llm`.

Téléphonie : `phone_sms` exige `sms_gateway_token`,
`phone_voice` exige `sip_trunk_password` (+ `voice` pour la voix temps réel).
Le builder écrit les units (`serge-sms-receiver`, `serge-asterisk`,
`serge-voice-bridge`), les configs Asterisk user-space et la route
ingress `sms.<domaine>`. Le mandat `sandbox` coupe la voix sortante.
Détail : [`PHONE_OPTIONS.md`](PHONE_OPTIONS.md),
[`PHONE_SMS_ONLY.md`](PHONE_SMS_ONLY.md),
[`PHONE_VOICE_SMS.md`](PHONE_VOICE_SMS.md).

## `serge.secrets.age`

Chiffrement : [age](https://age-encryption.org/) ou SOPS-age.

Après déchiffrement : dotenv plat, noms du
[`schemas/serge.secrets.manifest.yaml`](../schemas/serge.secrets.manifest.yaml).

Tests / sandbox : `SERGE_SECRETS_DOTENV` pointe un dotenv clair (jamais
commité). `SERGE_AGE_IDENTITY` déchiffre `serge.secrets.age` en prod.

Jamais ce plaintext sur Discord, git, tickets, ou un zip « pour l’équipe ».

Le repo ignore `*.secrets.age` et `/serge.instance.toml` à la racine.

## Ce qui n’est pas dans le fichier

- Constitutions owner (`/etc/serge/meta-grok/…`) — pas un kit public.
- Checkout Meta-Grok, clones d’ingénierie, `v2-runs/`.
- Canon / `state/` d’une autre instance.
- Mandat de production Julien si l’instance n’est pas `julien-vps`.
- Secrets en clair.

`features.metagrok = true` = « ce host a le pont » ; ça ne transporte
pas le dépôt Meta-Grok. Sans checkout Meta-Grok local, le kit doit laisser
la feature à `false` (sinon builder/kernel refusent).

## Collab

Git = code + schémas + inventaire. VPS = `julien-vps`. Laptop = autre
`instance_id`. Même commit ≠ même SQLite. Dump canon uniquement si Julien
l’autorise nommément.

Le fichier d’instance **est** ce qu’on se passe. Le builder fait le reste.

## Instance vierge (kit / builder)

Le kit n’empacte **pas** le Serge de Julien. Il produit une instance vide
à partir du SHA git + du couple TOML/age **du destinataire**.

Interdit dans le seed (liste machine :
[`schemas/serge.kit-exclusions.yaml`](../schemas/serge.kit-exclusions.yaml)) :

- secrets (`*.age`, `~/.config/serge/secrets/`, clés, cartes)
- mémoire : `state/` (canon, cycles, leftover, portfolio-guidance,
  provisioning live, Caddy/certs), queues, evidence, logs, projects
- identité Julien : snowflakes Discord, domaines live, fiche juridique
- Meta-Grok (checkout, runs, Constitutions)

Le builder clone via `git archive` (ou checkout propre), **jamais** un
rsync du working tree VPS. Canon = SQLite créé vide. Un dump de prod
n’entre que sur ordre explicite, hors kit par défaut.

L’exemple tracké est `example-sandbox` (vierge), pas `julien-vps`.
