# Installation Serge (installeur unique)

`bin/serge-install` est le seul point d’entrée : il réutilise un couple
existant **ou** le génère (avec guide), puis construit l’instance.
Les outils historiques (`serge-instance-wizard`, `serge-builder`) restent
utilisables séparément ; l’installeur les orchestre.

## Les 3 chemins

```text
1. Couple existant :  serge-install --instance-file X --mandate Y --source-repo Z
2. Réponses JSON   :  serge-install --answers a.json --source-repo Z [--also-mandate]
3. Interactif guidé:  serge-install   (terminal, choix 1 ou 2 à l’écran)
```

`--non-interactive` refuse les prompts (CI). `--no-enable-units` écrit
sans `systemctl`. `--confirm-live-instance-id julien-vps` seul autorise
les chemins live (l’installeur le propose explicitement).

## Étape 1 : clé API + modèles (toujours en premier, chemin 3)

1. **Clé OpenRouter** (obligatoire, saisie masquée). Elle sert au guide
   pendant l’installation, puis part dans le sidecar chiffré. Jamais
   affichée, jamais dans le TOML.
2. **Catalogue live** : l’installeur liste les modèles OpenRouter
   (`GET /models`, ~400). Hors-ligne → saisie manuelle.
3. **Choix T1/T2/T3** : Entrée = recommandations live Julien
   (T1 `xiaomi/mimo-v2.5`, T2 `deepseek/deepseek-v4-flash-0731`,
   T3 `z-ai/glm-5.3-flash`), ou recherche par sous-chaîne + prix affichés.
   Le modèle guide = T2 par défaut.
4. **Référent** (optionnel) : URL affichée côté OpenRouter.

Les IDs partent dans `[llm]` du TOML (pas secrets) ; le builder écrit
`config_root/llm/slots.json` (CHEAP=T1, DEFAULT=T2, SMART=T3).

## Guide interactif (chemin 3)

Une fois la clé + le modèle guide choisis, **tape `?` (ou `aide`) à
n’importe quel prompt** : une question libre s’ouvre, le guide répond en
français, simplement, avec le contexte de l’étape (features, téléphone,
secrets...). Exemples : “c’est quoi un trunk SIP ?”, “quel mode choisir ?”,
“où trouver cette clé ?”.

- Le guide **ne voit aucun secret** et n’en demande jamais.
- Hors-ligne / clé invalide : réponses locales de secours, l’installation
  continue — rien n’est bloquant.
- Désactivable (`Activer le guide interactif ?`), réactivable en relançant.

## Ensuite : instance (2/3), secrets (3/3), build

Le wizard enchaîne instance → features → téléphone → **discord (IDs
serveur/forum/urgent/digest/owner)** → secrets (la clé OpenRouter n’est
pas redemandée) → sidecar age → mandat optionnel, puis l’installeur
construit : arbre vierge (`git archive`, jamais rsync), canon vide,
secrets 0600, units, Asterisk, route SMS, slots LLM.
Résumé humain + receipt JSON à la fin (`state/instance-build.json`).

**Secrets : règle d’or.** Tout secret vit dans le sidecar chiffré
(`serge.secrets.age`, jamais commité) puis en fichiers 0600 sous
`config_root/secrets/`. Chaque brique lit le sien à cet endroit
(token Discord, clés OpenRouter/Stripe/SIP, webhooks...). Rien dans le
TOML, rien dans git — le scan pre-commit le vérifie.

Détail contrat : [`INSTANCE_CONTRACT.md`](INSTANCE_CONTRACT.md).
Téléphonie : [`PHONE_OPTIONS.md`](PHONE_OPTIONS.md).
Discord : [`DISCORD_SETUP.md`](DISCORD_SETUP.md).
