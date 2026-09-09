# Inventaire d’instance Serge

Carte de ce qui relie encore Serge au VPS Julien (`julien-vps`).
Cible : **pas de fichier d’instance → pas de boot.** Le couple
`serge.instance.toml` + `serge.secrets.age` est produit par le kit, puis
le **builder** instancie. Détail : [`INSTANCE_CONTRACT.md`](INSTANCE_CONTRACT.md).

Table machine : [`instance-inventory.yaml`](instance-inventory.yaml).

Aujourd’hui le kernel hardcode encore `/home/serge`. Cet inventaire sert
au kit/builder pour ne pas recoder par-dessus ces chemins. Le fallback
disparaît quand le builder pose `SERGE_INSTANCE_FILE`.

**Aucune valeur secrète n’est reproduite ici.**

## Méthode de scan (2026-09-08)

Lecture seule :

- `rg` de `/home/serge`, `/opt/serge`, du domaine public, `~/.config/serge`, `~/.openclaw`
- `scripts/install-*.sh`, `systemd/`, `deploy/systemd/`
- basenames sous `~/.config/serge/secrets/` (pas le contenu)
- références code (`SECRET_PATH`, `XAI_`, Stripe, Discord, OpenRouter)

Limite : [`scripts/scan-repo-secrets.py`](../scripts/scan-repo-secrets.py)
ne voit que le git tracké.

## Barrière de boot (cible)

Sans `SERGE_INSTANCE_FILE` + sidecar déchiffrable + secrets de **chaque**
feature `true` + `openrouter_api_key` + mandat + dirs writables : **refus**.

Un clone git seul ne boot pas. Un TOML sans age ne boot pas. Une feature
allumée sans sa clé ne boot pas.

`[llm]` est toujours requis. Les autres surfaces sont des features : off =
hors instance (valide), on = secrets obligatoires.

## Ce que le kit doit demander (features)

Le YAML reste le catalogue d’hôte Julien. Mapping feature → ids :

| feature TOML | ids d’inventaire à provisionner si `true` |
| --- | --- |
| *(toujours)* | `path.system_root`, `path.policy_mandate`, `path.writable_runtime`, `path.canon_db`, `secret.openrouter`, `host_dep.python3`, `host_dep.pyyaml` |
| `ingress` | Caddy, Cloudflare, `optional.public_hostname` |
| `stripe` / `payments_live` | clés Stripe, vault, carte si live |
| `owner_ui` | token dashboard ; Discord si `discord` |
| `gmail` | gog env, provider, binaire |
| `openclaw` | optionnel ; défaut off. Runtime = OpenRouter `direct_llm` |
| `voice` | xAI / OpenAI env |
| `metagrok` | workspace + release **déjà présents** sur l’hôte (Julien-only) |
| `discord` | `secret.discord_bot_token` |
| `phone_sms` | `secret.sms_gateway`, `unit.sms_receiver`, route `sms.<domaine>` |
| `phone_voice` | `secret.sip_trunk`, `unit.asterisk`, `unit.voice_bridge`, `host_dep.asterisk` |

Aujourd’hui, sans fichier d’instance, le VPS boot encore grâce aux
hardcodes. C’est la dette que le builder ferme.

## Julien-only (ne pas copier dans un kit tiers)

- Mandat root `/opt/serge-policy/mandate.yaml` et Constitutions Meta-Grok.
- Checkout et release Meta-Grok.
- Identité publique DNS du propriétaire.
- Unix `serge` / uid `1002`.
- Snowflake Discord owner câblé.
- Canon et `state/` de production.

Un tiers allume `metagrok` seulement s’il a **son** pont, pas le checkout
Julien. Sinon la feature reste `false` et l’instance boot.

## Règles de collab

1. **Git** = code, schémas, inventaire, exemple TOML. Jamais
   `serge.secrets.age` de prod.
2. **VPS** = `julien-vps`. Laptop = autre `instance_id`.
3. **Même HEAD git ≠ même canon.** Copie locale vide, ou dump autorisé.
4. On se passe le couple kit (TOML + age), pas un zip de secrets.
5. Le builder, pas l’humain, pose les units et `SERGE_INSTANCE_FILE`.
6. Le kit est un Serge **vierge**. Pas tes secrets, pas ton canon, pas
   Discord/domaines/leftover. Exclusions :
   [`schemas/serge.kit-exclusions.yaml`](../schemas/serge.kit-exclusions.yaml).
