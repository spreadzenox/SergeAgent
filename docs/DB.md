# Canon SQLite — schéma et migrations

Le fichier `$SERGE_SYSTEM_ROOT/state/serge.db` est **l’autorité** des
faits métier (charte P4). Le deploy crée un canon vide au premier
install et **ne le recrée pas** à l’update.

## Ouverture

`open_db` (WAL, `0600`) appelle `init_schema` :

1. **Migrations** (`serge/db/migrate.py`) : enchaîne les versions
   manquantes, tamponne `schema_version` **seulement** après une
   migration réellement appliquée.
2. **Catalogue** (semence idempotente, pas du DDL) : colonnes comptes
   manquantes, étapes, tools, invocations LLM.

Une base déjà à la tête du code ne réécrit pas le tampon. Une base
**plus récente** que le code refuse de booter (`MigrateError`) — un
rollback git ne démonte pas le schéma tout seul.

Le socle actuel est la **v7** (`SCHEMA_SQL` dans `serge/db/schema.py`).
Une base vide saute à v7 d’un coup. Ensuite chaque évolution = une
fonction `apply_v00N`, numéro = précédent + 1.

Ledgers bornés hors canon (même pattern `CREATE IF NOT EXISTS`, pas
encore dans cette chaîne) : `state/voice/voice.db`, inbox SMS.
L’index FTS `memory_fts` se crée au premier search.

## Objets (miroir)

Catalogue (types, semés) vs occurrences (faits) :

| Catalogue | Occurrences |
|---|---|
| `pipeline_steps` | `work_items` (prochain lot : `etape_id`) |
| `llm_points` + `llm_point_tools` | `llm_usage` |
| invocations techniques (à venir) | `events` / runs |
| `tools` | appelés seulement par une invocation LLM |

Autres faits déjà en canon : `ventures`, `campaigns`, `contacts`,
`tickets`, `artifacts`, `transactions`, `consents`, `lessons`,
`policy_snapshots`. Voix / SMS : ledgers à part.

## Prochain lot (décidé, pas encore dans le code)

Étapes = sacs de vie du projet (enum fermé), coupe-circuit MC par
`etape_id` du work item — plus par `kind` (le smoke et la prospection
lourde partagent `email.send`).

Ordre : pré-prospection → conception PoC → prospection light (smoke)
→ choix de venture → build/rebuild (y compris livraison / onboarding)
→ prospection lourde → collect feedback → **caisse**. Hors épine :
mémoire, policy owner.

Renommage UI/docs : « jugement » → **invocation LLM** (la charte
garde le mot tant que Julien ne l’amende pas).
