# SergeAgent v0 — opérateur économique autonome (kit + runtime)

SergeAgent s'installe **depuis zéro** (`bin/serge-install`) : un couple
(instance TOML + sidecar secrets chiffré) puis un arbre vierge construit
depuis ce dépôt. Aucun secret n'est versionné — le scan pre-commit le
vérifie à chaque commit.

Tout le code est sous [charte](docs/CODEBASE_CHARTER.md) : modules < 500
lignes, diffs < 300 lignes, déterministe par défaut, LLM déclaré
(registre + kill-switch), SQLite = seule autorité, tests comportementaux.

## Layout

```text
kit/            installeur (TOML+age, wizards, builder, guide, slots LLM)
serge/          runtime (scheduler, guards, tickets, funnels, mémoire, voix)
serge/discord/  bot Discord (miroir tickets + actes owner, gateway temps réel)
serge/collect/  facturation (intents, relances, rail Stripe test-first)
serge/observe/  signaux inbound + routeur universel
serge/memory/   mémoire 5 couches (registres → recherche libre)
serge/llm/      couche LLM (client metered, budget dur, kill-switchs)
serge/points/   29 points LLM déclarés (matrice C, replis dét)
serge/workers/  exécutants des files (inbound, mémoire, écoute, envois)
config/         policy.yaml, llm-points.yaml, ticket-types.yaml, séquences
schemas/        contrats instance + secrets + exclusions
systemd/        templates d'units paramétrés
scripts/        serge-install (+ outils), scan secrets
bin/            shims CLI
tests/          unitaires + live-prudents (skippés par défaut)
docs/           design (charte, funnels, mémoire, matrice, interactivité)
```

## Installer

```sh
bin/serge-install            # interactif guidé (clé API + modèles d'abord)
bin/serge-install --instance-file X --mandate Y --source-repo Z  # couple prêt
```

Détail : [docs/INSTALL.md](docs/INSTALL.md). Contrat :
[docs/INSTANCE_CONTRACT.md](docs/INSTANCE_CONTRACT.md). Discord :
[docs/DISCORD_SETUP.md](docs/DISCORD_SETUP.md).

## Développer

```sh
curl -LsSf astral.sh/uv/install.sh | sh
uv sync --group dev
uv tool install pre-commit && pre-commit install
pre-commit run --all-files
python3 -m unittest discover -s tests            # unitaires
SERGE_ENV=test python3 -m unittest discover -s tests  # + live-prudents (.env.test)
```

Règles : charte P1-P5 + R1-R5 (review dans chaque message de commit),
jamais de secret commité, jamais d'écriture live sans
`--confirm-live-instance-id`.

## Version

Tag `v0` = kit installable + runtime complet (funnels dét, 29 points LLM,
mémoire 5 couches, voix S2S + repli, collect sandbox, bot Discord).
Bêta : installer depuis ce tag sur un VPS vierge, puis activer.
