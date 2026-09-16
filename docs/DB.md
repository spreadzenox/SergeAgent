# Canon SQLite — schéma et migrations

Le fichier `$SERGE_SYSTEM_ROOT/state/serge.db` est **l’autorité** des
faits métier (charte P4). Le deploy crée un canon vide au premier
install et **ne le recrée pas** à l’update.

## Ouverture

`open_db` (WAL, `0600`) appelle `init_schema` (`serge/db/boot.py`) :

1. **Migrations** (`serge/db/migrate.py`) : enchaîne les versions
   manquantes, tamponne `schema_version` **seulement** après une
   migration réellement appliquée.
2. **Catalogue** (semence idempotente, pas du DDL) : colonnes comptes
   manquantes, étapes, tools, invocations LLM / tech, canaux, liens
   d’épine, SHA fichiers.

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

`init_schema` sème le catalogue puis `verifier_catalogue` refuse un
graphe incomplet (toute instance, même vierge).

Catalogue (types, semés) vs occurrences (faits) :

| Catalogue | Occurrences |
|---|---|
| `pipeline_steps` | `work_items.etape_id` (coupe-circuit MC) |
| `llm_points` + `llm_point_tools` | `llm_usage` |
| `tech_invocations` | `events` / runs (pas encore de ledger dédié) |
| `tools` | `llm_point_tools` (seule une invocation LLM invoque) |
| `canaux` + `brique_canaux` | touches / envois (`email.send`, `voice.send`, Discord) |
| `etape_liens` | débits Live (`listen_docs` … `transactions`) |

Liens : `llm_points.etape_id` et `tech_invocations.etape_id` ∈ épine
ou `policy` ; jonction `llm_point_tools` sans orphelin. Lecture :
`objets_de_etape`. Hors épine : `policy` (3 invocations LLM).

Autres faits déjà en canon : `ventures`, `campaigns`, `contacts`,
`tickets`, `artifacts`, `transactions`, `consents`, `lessons`,
`policy_snapshots`. Voix / SMS : ledgers à part.

## Étapes (v8)

Enum fermé, coupe-circuit d’étape par `work_items.etape_id` — plus par
`kind` seul (le smoke et la lourde partagent `email.send`). Un kind
peut aussi être coupé à part via `runtime_flags.kind.{kind}` ; tout
Serge via `runtime_flags.scheduler.heartbeat`.

Factures = table `transactions`. Abonnements = table `subscriptions`
(`external_id` Stripe `sub_…`, `last_transaction_id` → dernière
facture encaissée). Writer : webhooks `customer.subscription.*` et
`invoice.paid` (`serge/collect/abonnements.py`).

Journal voix = ledger `state/voice/voice.db` (`calls`) : `outcome`,
`duration_s`, `recording_path`, `transcript`. 0 s + échec = jamais
connecté, pas une conversation de zéro minute.

Ordre : pré-prospection → conception PoC → prospection light (smoke)
→ choix de venture → build/rebuild (y compris livraison / onboarding)
→ prospection lourde → collect feedback → **caisse**. Hors épine :
policy owner.

Renommage UI/docs encore partiel : « jugement » → **invocation LLM**
(la charte garde le mot tant que Julien ne l’amende pas).

Invocations techniques : table `tech_invocations` (kinds fermés
`cluster` / `select` / `score` / `transform` / `index`). Une étape
en a n ; seule une **invocation LLM** peut appeler des tools. Runtime :
`serge/llm/boucle.py` (plafond 12 tours) + handlers dans
`serge/llm/outils_exec.py`. Un tool `kind=agent` ne peut pas en
appeler un autre (garde `outil_peut_invoquer`, pas encore d’enchaînement
tool → tool).

## Docs MC + SHA fichiers (v10)

Chaque objet catalogue porte `doc_md` (ou les champs fiche d’étape :
`titre`, `pourquoi`, `argent`, `dependance`, `comment`), `files_sha`
et `updated_at`. Mission Control lit **uniquement la base** pour
l’épine, les fiches et le graphe Live.

`files_sha` = SHA-256 des SHA *contenu* de tous les fichiers qui
encodent l’objet **et** ses sous-objets (étape → invocations LLM /
tech → tools). Pas les chemins, pas les dates. Valeur figée dans
`serge/catalogue_lock.py`, recopiée au seed. Les tests
(`tests/test_catalogue_sha.py`) rougissent si un objet est rajouté,
supprimé, ou si le SHA disque ≠ SHA en base.

`etape_liens` : arêtes de l’onglet En direct (`de` → `vers`, `libelle`,
`debit` enum fermé : `listen_docs`, `campaigns`, `contacts`,
`artifacts`, `touches`, `inbound_events`, `transactions`). Pas de SQL
libre.

## Canaux (v11)

Un canal = un moyen pour Serge d’**écrire vers un tiers** (client,
prospect, partenaire — pas Julien). Discord owner n’en est pas un.
Table `canaux` (id fermé, `doc_md`, `code_path` du writer, `etat`
`branche` / `prevu`). Jonction n-n `brique_canaux` : `brique_kind` ∈
{`llm`, `tech`}. Semence `serge/canaux.py`. Aujourd’hui branchés :
`email`, `voice`. Pas LinkedIn / WhatsApp / Ads tant qu’il n’y a pas
de writer.

## Contacts par lieu (v12)

Une fiche `contacts` = une trace sur **un** lieu (`venue` + `handle`,
URL optionnelle). Deux lieux, deux lignes, même si c’est le même
humain. `upsert_trace` (`serge/funnels/contact_canal.py`) enrichit
**sa** ligne (mail trouvé sur LinkedIn → fiche LinkedIn). Index unique
partiel `(venture_id, venue, handle)` si les deux sont non vides.
Les contacts e-mail historiques (venue vide) restent valides.

## Comptes standing (v13)

`accounts_standing.login` et `accounts_standing.password` : identifiants
de connexion **en clair**. Ce sont des comptes que Serge a créés ; ils
n’ont pas de valeur hors de lui. Writer : `enregistrer_compte`
(`serge/comptes.py`) — un lieu + un handle = une ligne ; le second
appel met à jour login / mot de passe, pas le capital. `secret_ref`
n’est plus le coffre.

## Santé des comptes (v14)

`accounts_standing.last_used_at` : dernier acte qui a débité le capital.
Garde `serge/comptes_sante.py`. Barème : `policy.standing` (`cout_usage`,
`gain_par_heure`, `idle_apres_heures`, `capital_min`, `capital_max`).
Après un usage le capital ne peut que baisser ; à l’inutilisation il
remonte, sans dépasser le plafond. Un snapshot policy plus vieux que
cette section est complété par la semence YAML à la lecture.

## Identité (pas de table)

`identite_serge()` (`serge/identite.py`) lit `[identity]` + `[mailbox]`.
Pas de seconde table. Volet advanced = IBAN + adresse de facturation.
Outils catalogue `identity_basique` (branché) et `identity_advanced`
(`prevu`). Page MC `#/identite`.

## Demande de capacité

Tool `demande_capacite` (branché, partout) : `poser_demande()` crée un
ticket `REQUESTED` (champs `demande`, `contexte`, `point_llm`). Pas de
kind worker. Le même besoin déjà ouvert pour le même jugement n’est
pas recréé.

## Boîte mail / SMS

Tool `boite_serge` : mails dans `inbound_events` (corps dans
`payload_json`), SMS dans le ledger inbox **en brut** (plus seulement
le hash). Le séquenceur n’enfile plus `sms.send` (pas de writer).
