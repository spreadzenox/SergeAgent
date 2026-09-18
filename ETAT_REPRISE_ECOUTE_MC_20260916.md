# État de reprise — Écoute / Mission Control

Date : 2026-09-16

Ce document capture l'état du chantier au moment de l'arrêt demandé. Il sert de point de reprise pour un prochain agent ou une prochaine session. **Aucun commit n'a été créé.** Le dépôt est volontairement laissé dans son état de travail courant.

## Demande utilisateur en cours

Le besoin était de corriger l'intégration de l'objectif 1 avec le code existant :

- En direct doit suivre le catalogue DB/code réellement actif.
- L'ancien jugement d'écoute ne doit plus apparaître comme un jugement à l'étape suivante.
- Les jugements doivent être triés selon l'ordre métier, pas selon l'ordre alphabétique des IDs.
- L'ordre demandé pour `pre_prospection` est :
  1. `cluster_demand` / « Regrouper la demande ».
  2. Dans les autres jugements, ordre explicite :
     - `listen_choose_poc` / « Choisir les business à tester ».
     - `listen_discover_needs_a` / « Explorer les besoins A ».
     - `listen_discover_needs_b` / « Explorer les besoins B ».
- Les paramètres ne doivent plus être nommés seulement `n` et `p`.
- Les paramètres doivent appartenir à la Policy, être stockés dans les snapshots Policy de la BDD, être visibles et modifiables depuis la page Policy, et ne plus être édités depuis la page Écoute.
- `TODO.md` ne doit pas être modifié par l'agent.

## Architecture déjà implémentée avant le dernier correctif

### Migration v15

Fichier : `serge/db/v015.py`

Tables ajoutées :

- `db_readers`
- `llm_point_readers`
- `listen_settings` (ancienne table locale, désormais legacy et destinée à disparaître)
- `listen_cycles`
- `listen_cycle_docs`
- `business_candidates`
- `business_candidate_sources`
- `poc_selections`

La mémoire d'écoute est persistante :

```text
listen_docs
  -> listen_cycle_docs
  -> business_candidates
  -> poc_selections
```

`listen_docs` évite de réexplorer les documents déjà présents. `listen_cycle_docs` fige le corpus d'un cycle. `business_candidates` conserve les business déjà trouvés. `poc_selections` conserve les sélections et possède un index unique partiel pour empêcher deux engagements POC actifs du même candidat.

### Permissions DB et tools

Fichier principal : `serge/db_readers.py`

Lecteurs nommés :

- `current_listen_cycle`
- `listen_cycle_documents`
- `known_business_candidates`
- `eligible_poc_candidates`

Permissions par agent :

```text
listen_discover_needs_a:
  current_listen_cycle
  listen_cycle_documents
  known_business_candidates

listen_discover_needs_b:
  current_listen_cycle
  listen_cycle_documents
  known_business_candidates

listen_choose_poc:
  current_listen_cycle
  eligible_poc_candidates
```

Le tool `db_read` n'accepte pas de SQL libre. Il vérifie le lecteur demandé contre `llm_point_readers` en BDD, puis appelle une vue nommée dans `serge/listen/memory.py`.

Le runtime injecte au modèle les permissions DB et filtre les tools par les jonctions `llm_point_tools` actives. Les deux agents de découverte reçoivent le même contrat et ne reçoivent jamais la sortie de l'autre.

Le tool `web_search` existe dans `serge/listen/web.py`. Il interroge le web public en lecture seule et est déclaré pour les deux agents de découverte via `config/llm-points.yaml`.

### Trois points LLM

Déclarés dans `config/llm-points.yaml`, enregistrés dans `serge/llm_registre.py` et rattachés à `pre_prospection` dans `serge/mc/libelles.py` :

- `listen_discover_needs_a`
- `listen_discover_needs_b`
- `listen_choose_poc`

Les deux premiers sont indépendants et ont le même contexte. Le troisième lit uniquement les candidats canoniques après écriture/déduplication déterministes.

### Worker du cycle

Fichier : `serge/workers/listen.py`

Kind : `listen.business_cycle`

Le worker :

1. lit le cycle ;
2. exécute A ;
3. exécute B ;
4. n'écrit les candidats qu'après les deux retours ;
5. déduplique les candidats ;
6. exécute le choix POC ;
7. applique `select_poc()` avec veto déterministe ;
8. journalise un événement de cycle.

Le kind est déclaré dans `serge/etapes.py` sous `pre_prospection` et routé dans `serge/workers/dispatch.py`.

### Onglet Mission Control Écoute

Fichiers :

- `serge/mc/ecoute_actions.py`
- `serge/mc/proj_ecoute.py`
- `serge/mc/static/mc/pages/ecoute.js`
- `serge/mc/templates/shell.html`
- `serge/mc/static/mc/app.js`
- `serge/mc/projectors.py`
- `serge/mc/server.py`

L'onglet affiche :

- les valeurs Policy de découverte/sélection ;
- le dernier cycle ;
- les agents et leurs lecteurs DB ;
- les business candidats ;
- un champ guide de recherche ;
- un bouton pour lancer le cycle.

L'ancien endpoint de réglage local `/owner/api/listen/settings` est conservé comme route explicite `410` afin d'éviter qu'un ancien client puisse modifier une seconde source de vérité. Les paramètres doivent être modifiés dans Policy.

## Derniers changements du correctif d'intégration

### Ordre métier

Fichier : `serge/mc/proj_etape.py`

Ajout de :

```python
RESTE = {
    'pre_prospection': [
        'listen_choose_poc',
        'listen_discover_needs_a',
        'listen_discover_needs_b',
    ],
}
```

`lister_jugements()` ne fait plus dépendre l'ordre de `ORDER BY id`. Il prend l'ordre déclaré dans `ORDRE`, puis l'ordre déclaré dans `RESTE`, puis les éventuels autres points par défaut.

Pour `pre_prospection`, le résultat attendu est donc :

```text
cluster_demand                ordre=True, rang=1
listen_choose_poc             ordre=False
listen_discover_needs_a       ordre=False
listen_discover_needs_b       ordre=False
```

### Graphe En direct

Fichier : `serge/mc/proj_graphe.py`

Le graphe ne fait plus :

```sql
SELECT id, etape_id, titre, tier FROM llm_points ORDER BY id
```

Il charge les étapes par `pipeline_steps.rang`, puis calcule une position à partir de `ORDRE` et `RESTE`. Les nœuds LLM du graphe sont triés selon cette position métier. Les points inconnus de l'ordre viennent ensuite.

### Paramètres Policy

Fichiers :

- `config/policy.yaml`
- `serge/policy.py`
- `serge/mc/static/mc/policy_champs.js`
- `serge/mc/ecoute_actions.py`
- `serge/mc/proj_ecoute.py`
- `serge/listen/memory.py`
- `serge/workers/listen.py`

Nouveaux noms :

```yaml
listen:
  discovery_needs_target: 5
  poc_business_target: 1
```

Le validateur de Policy exige maintenant ces deux nombres. La page Policy les expose dans la section « Écoute du web » avec les libellés :

- « Besoins à explorer par découverte »
- « Business à retenir pour le prochain POC »

Le cycle recopie les valeurs au moment du lancement dans :

```text
listen_cycles.needs_target
listen_cycles.business_target
```

Ainsi, un cycle garde les valeurs réellement utilisées même si Policy change ensuite.

### Migration v16

Fichier : `serge/db/v016.py`

Objectif : renommer :

```text
listen_cycles.n_target       -> listen_cycles.needs_target
listen_cycles.p_target       -> listen_cycles.business_target
```

Le fichier contient aussi une suppression de `listen_settings`.

### Migration v17

Fichier : `serge/db/v017.py`

Contenu actuel vérifié :

```python
connection.execute('DROP TABLE IF EXISTS listen_settings')
```

Cette migration rend la suppression de la table legacy définitive même sur une base qui a déjà traversé v16.

Tête de schéma attendue : **v17**.

## État du catalogue SHA

`serge/catalogue_lock.py` a été modifié plusieurs fois car :

- `config/llm-points.yaml` est inclus dans les SHA des points LLM ;
- `serge/etapes.py` est inclus dans les SHA des étapes ;
- `serge/listen/memory.py` est inclus dans le SHA du tool `db_read` ;
- les nouvelles jonctions changent les SHA calculés des arbres catalogue.

Une tentative de remplacement global des valeurs SHA a temporairement corrompu la syntaxe de `catalogue_lock.py`. Cette corruption a été réparée partiellement :

- `python -m py_compile serge/catalogue_lock.py` repassait après réparation syntaxique ;
- le test catalogue a encore signalé des valeurs SHA incohérentes avant l'arrêt ;
- le dernier état doit impérativement être revalidé par `tests.test_catalogue_sha`.

Commande de validation :

```bash
cd /home/cleme/Serge/SergeAgent
.venv/bin/python -m unittest tests.test_catalogue_sha -q
```

Si le test liste des SHA, recalculer avec :

```bash
.venv/bin/python - <<'PY'
import sqlite3
from pathlib import Path
from serge.db.boot import init_schema
from serge.objet_sha import sha_arbre
from serge.catalogue_lock import SHA_ATTENDUS

conn = sqlite3.connect(':memory:')
init_schema(conn)
for kind, ident in sorted(SHA_ATTENDUS):
    actual = sha_arbre(Path('.'), kind, ident, conn)[0]
    if actual != SHA_ATTENDUS[(kind, ident)]:
        print(kind, ident, actual)
PY
```

Ne pas faire de remplacement global par simple valeur SHA : plusieurs objets partageaient historiquement le même SHA et un remplacement textuel aveugle a déplacé des valeurs sur le mauvais objet. Corriger chaque entrée avec son contexte `(kind, id)`.

## Tests déjà passés avant l'arrêt

Les validations suivantes avaient été vertes à différents milestones :

- migration v15 sur SQLite mémoire ;
- boot/catalogue ;
- tests runtime LLM et boucle d'outils ;
- tests mémoire d'écoute ;
- tests serveur MC et frontend ;
- suite complète antérieure : 824 tests OK, 3 ignorés ;
- tests ciblés ordre/MC/Policy : la dernière commande a produit des logs MC et n'a pas affiché d'échec dans la portion consultée, mais doit être relancée après v17 ;
- Ruff avait été vert sur les modules principaux avant les derniers fichiers v16/v17.

La suite complète doit être relancée seulement après que `test_catalogue_sha`, `test_db` et `test_migrate` soient verts.

## Vérifications actives au dernier état connu

Avant l'ajout de v17, l'instance active avait été observée avec :

```text
schema 15
listen_cycles : n_target, p_target
```

Après migration v16 déclenchée explicitement, elle avait été observée avec :

```text
schema 16
listen_cycles : needs_target, business_target
```

La migration v17 devait encore être appliquée et vérifiée au moment de l'arrêt.

Commandes de reprise :

```bash
cd /home/cleme/Serge/SergeAgent
SERGE_SYSTEM_ROOT=/home/cleme/serge-system .venv/bin/python - <<'PY'
from serge.db.store import open_db
from serge.paths import system_root

path = system_root() / 'state/serge.db'
with open_db(path) as conn:
    print('version=', conn.execute('SELECT max(version) FROM schema_version').fetchone()[0])
    print('legacy=', conn.execute(
        "SELECT count(*) FROM sqlite_master "
        "WHERE type='table' AND name='listen_settings'"
    ).fetchone()[0])
    print('columns=', [row[1] for row in conn.execute(
        'PRAGMA table_info(listen_cycles)'
    )])
PY
```

Résultat attendu :

```text
version= 17
legacy= 0
columns= ['id', 'guide', 'needs_target', 'business_target', 'status', 'created_at', 'started_at', 'finished_at']
```

## Vérification MC après redémarrage

Le service est :

```text
serge-public-dashboard.service
```

Il écoute habituellement sur :

```text
http://127.0.0.1:8790/owner
```

Après chargement du nouveau code, vérifier :

```bash
SERGE_SYSTEM_ROOT=/home/cleme/serge-system .venv/bin/python - <<'PY'
import json
import urllib.request
from serge.paths import system_root
from serge.secrets import owner_dashboard_token

root = system_root()
headers = {'X-Serge-Owner-Token': owner_dashboard_token(root)}
for page in ('p0', 'p5', 'p10'):
    request = urllib.request.Request(
        f'http://127.0.0.1:8790/owner/api/state?page={page}',
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        data = json.load(response)
        print(page, response.status, list(data['sections']))
        if page == 'p10':
            print(data['sections']['ecoute']['payload']['settings'])
PY
```

Vérifier dans le payload `p0` :

```text
cluster_demand est le premier jugement de pre_prospection.
listen_choose_poc, listen_discover_needs_a, listen_discover_needs_b suivent dans « Autres jugements ».
Aucun ancien jugement inattendu n'est présent.
```

Vérifier dans `p5` :

```text
listen.discovery_needs_target
listen.poc_business_target
```

Vérifier dans `p10` :

```json
{
  "discovery_needs_target": 5,
  "poc_business_target": 1
}
```

## Point important sur `TODO.md`

`TODO.md` est déjà modifié dans le worktree par l'utilisateur ou un état antérieur. Il ne faut pas le restaurer, le réécrire ni changer son statut. La reprise doit travailler avec son contenu présent.

## Commandes de validation recommandées à la reprise

Ordre conseillé :

```bash
cd /home/cleme/Serge/SergeAgent
.venv/bin/python -m py_compile \
  serge/db/v016.py serge/db/v017.py \
  serge/mc/proj_etape.py serge/mc/proj_graphe.py \
  serge/mc/proj_ecoute.py serge/mc/ecoute_actions.py

.venv/bin/ruff check \
  serge/db/v016.py serge/db/v017.py \
  serge/mc/proj_etape.py serge/mc/proj_graphe.py \
  serge/mc/proj_ecoute.py serge/mc/ecoute_actions.py

.venv/bin/python -m unittest \
  tests.test_catalogue_sha \
  tests.test_migrate \
  tests.test_db \
  tests.test_mc_proj_graphe \
  tests.test_mc_etape \
  tests.test_mc_policy \
  tests.test_mc_front \
  tests.test_listen_memory -q
```

Ensuite seulement :

```bash
.venv/bin/python -m unittest discover -s tests -q
```

## Risques et points à ne pas oublier

1. **Ne pas refaire un remplacement global des SHA.** Les entrées doivent être corrigées par clé.
2. **Ne pas remettre `listen_settings` dans `TABLES`.** Elle est legacy et doit rester supprimée.
3. **Ne pas réintroduire l'édition n/p dans l'onglet Écoute.** Les paramètres viennent de Policy.
4. **Ne pas modifier `TODO.md`.**
5. **Ne pas confondre `cluster_demand` et les trois nouveaux agents.** `cluster_demand` reste le jugement d'ordre 1 demandé par l'utilisateur.
6. **La migration active peut avoir besoin d'un redémarrage du service MC.** Le service charge le code au démarrage.
7. **Les `BrokenPipeError` dans les tests MC sont généralement causés par le client de test qui ferme la connexion ; ils existaient déjà et ne signifient pas automatiquement une panne du MC.**
8. **Les `ResourceWarning` de connexions SQLite/YAML apparaissent dans la suite existante ; les distinguer d'un échec fonctionnel.**

## État final honnête au moment de l'arrêt

Le chantier est avancé mais pas déclaré terminé :

- l'ordre métier est codé dans la projection fiche étape et le graphe ;
- les hyperparamètres ont été déplacés conceptuellement et runtime vers Policy ;
- les colonnes de cycle ont des noms explicites ;
- les migrations v16/v17 existent ;
- `v017.py` a été relu après une modification externe et contient bien le `DROP TABLE` attendu ;
- le catalogue SHA a été réparé syntaxiquement mais doit encore être confirmé par son test après les dernières corrections ;
- la migration v17 et la suite finale restent à valider dans une nouvelle session.
