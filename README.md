# SergeAgent

Serge est un programme qui gagne de l'argent tout seul, sous le contrôle
de son propriétaire. Il cherche des besoins sur le web, teste des idées de
business auprès de vrais prospects, garde la meilleure, la construit, la
vend et encaisse.

Il a une adresse e-mail, un numéro de téléphone, une carte bancaire, un
compte Stripe et un accès permanent à Internet. Le propriétaire (Julien)
valide les décisions importantes, depuis une console web (Mission Control)
ou Discord.

La seule vraie limite de Serge est la légalité. Il ne trompe personne et
assume d'être un agent IA.

---

## La chaîne en 8 étapes

```text
1. Pré-prospection     trouver des besoins, choisir des business à tester
        ↓
2. Conception du POC   écrire le plan du test, construire un livrable d'essai
        ↓
3. Prospection légère  tester auprès d'une quarantaine de prospects
        ↓
4. Choix               garder le meilleur des 3 tests
        ↓
5. Construction        construire le vrai produit, brancher le paiement
        ↓
6. Prospection lourde  vendre à plus grande échelle, livrer, améliorer
        ↓
7. Mémoire             tirer des leçons de ce qui s'est passé
        ↓
8. Caisse              encaisser, relancer les impayés
```

Tout le reste du projet s'organise autour de cette chaîne.

## Où lire la suite

| Pour… | Lire |
|---|---|
| Comprendre comment Serge fonctionne | [`docs/PIPELINE.md`](docs/PIPELINE.md) |
| Comprendre une étape en détail | [`docs/etapes/`](docs/etapes/) |
| Comprendre la mémoire | [`docs/MEMOIRE.md`](docs/MEMOIRE.md) |
| Comprendre la base de données | [`docs/DB.md`](docs/DB.md) |
| Utiliser la console | [`docs/MISSION_CONTROL.md`](docs/MISSION_CONTROL.md) |
| Installer une instance | [`docs/installation/INSTALL.md`](docs/installation/INSTALL.md) |
| Écrire du code | [`docs/CHARTE.md`](docs/CHARTE.md) et [`docs/DEV_TOOLING.md`](docs/DEV_TOOLING.md) |
| Savoir ce qui reste à faire | [`TODO.md`](TODO.md) |
| Connaître les décisions de la revue de septembre 2026 | [`docs/DECISIONS_REVUE.md`](docs/DECISIONS_REVUE.md) |

## État

Serge est en pleine refonte. Beaucoup de morceaux sont écrits mais pas
encore branchés entre eux. Chaque page de [`docs/etapes/`](docs/etapes/)
dit clairement ce qui marche aujourd'hui et ce qui est décidé mais reste à
construire.

Ce qui est branché aujourd'hui dans le code :

- Mission Control et le bot Discord ;
- l'étape 1, lancée à la main depuis Mission Control ;
- l'envoi d'e-mails et d'appels, la relève de la boîte mail toutes les
  5 minutes, le traitement des réponses ;
- la consolidation de la mémoire tous les 3 jours ;
- la réception des paiements Stripe.

Tout le reste (trouver des prospects, concevoir un POC, construire, choisir
le business principal…) est décidé mais pas encore construit.

## Démarrer

Installer une instance :

```sh
bin/serge-install
```

Détails : [`docs/installation/INSTALL.md`](docs/installation/INSTALL.md).

Développer :

```sh
curl -LsSf astral.sh/uv/install.sh | sh
uv sync --group dev
uv run pre-commit install
scripts/ci.sh
```

Chaque push sur `main` est déployé automatiquement sur le VPS de Julien.
On ne pousse donc jamais directement sur `main` : une branche, une PR, la
CI verte.

## Le code

```text
kit/             l'installeur (fichier d'instance, secrets chiffrés, assistants)
serge/           Serge lui-même
  db/            la base : ouverture, migrations
  llm/           appels au LLM, budget, tools
  points/        les invocations LLM (un prompt et sa vérification chacune)
  workers/       ce que le runner exécute
  listen/        l'écoute (étape 1)
  funnels/       campagnes, contacts, statuts des ventures
  observe/       traduction des réponses en signaux
  collect/       la caisse (Stripe, relances)
  memory/        leçons, résumés, recherche
  voice/, sms/   téléphone
  discord/       le bot Discord
  mc/            Mission Control
config/          valeurs de départ : policy, invocations LLM, types de tickets
systemd/         services du serveur
tests/           les tests
docs/            la documentation
```

## Licence

MIT, voir [LICENSE](LICENSE).
