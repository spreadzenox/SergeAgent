# Étape 1 — Pré-prospection

Identifiant : `pre_prospection`.

**Rôle.** Trouver des besoins réels sur le web, en tirer des idées de
business, et choisir celles à tester.

**Entrée.** Un texte de Julien pour guider la recherche (facultatif). Des
flux RSS à suivre. Les business déjà connus.

**Sortie.** Des business choisis pour un test (statut `POC_SELECTED`), avec
les pages web qui prouvent le besoin.

---

## Aujourd'hui

### Ce qui marche

**Lancer un cycle depuis Mission Control** (page Écoute). Julien écrit un
texte de guidage et clique. Serge crée un cycle (`listen_cycles`) et une
tâche `listen.business_cycle`. Le cycle se déroule ainsi
(`serge/workers/listen.py`) :

1. Le cycle fige les pages de `listen_docs` jamais utilisées par un cycle
   précédent.
2. **« Explorer les besoins A »** (invocation LLM), puis **« Explorer les
   besoins B »** : même consigne, même contexte. B ne voit jamais la sortie
   de A. Chacune peut chercher sur le web (`web_search`), dans la mémoire
   (`memory_search`) et lire la base (cycle courant, pages du cycle,
   business déjà connus).
3. Serge enregistre les fiches dans `business_candidates` en écartant les
   doublons : même contenu, ou au moins 72 % de mots en commun avec une
   fiche existante.
4. **« Choisir les business à tester »** (invocation LLM) lit les business
   encore candidats et en choisit.
5. Le code refuse un business déjà choisi pour un test
   (`serge/listen/memory.py`, `select_poc`).

Réglages (policy, page Policy) : `listen.discovery_needs_target` (5 besoins
par découverte) et `listen.poc_business_target` (1 business choisi).

**Collecter des flux RSS** : le worker `listen.collect` télécharge les
articles d'une liste de flux et les range dans `listen_docs`, sans doublon.

### Ce qui ne marche pas

- **Rien ne lance la collecte RSS**, et aucune liste de flux n'est
  configurée. Seul le script de démo `scripts/mc-demo.py` met des pages en
  base.
- **Les pages trouvées par la recherche web ne sont pas gardées.** Les
  preuves d'un besoin ne peuvent citer que des pages de `listen_docs`.
  Comme la table est vide en production, les business sont enregistrés
  sans preuve.
- **La lecture des pages du cycle renvoie seulement leurs identifiants**,
  pas leur titre ni leur extrait, sauf si le modèle demande lui-même la
  jointure entre les deux tables.
- **La recherche web lit la page de résultats de DuckDuckGo** (5 résultats,
  un extrait). Elle ne lit jamais les pages et peut être bloquée.

---

## Décidé

L'étape devient **deux processus** et **7 invocations**, chacune avec un
seul rôle.

**La veille** tourne toute seule, régulièrement, sans LLM.

**Le cycle** se lance à la main, puis automatiquement plus tard. Il ne
tourne que s'il reste une place libre en prospection légère.

| # | Invocation | Type | Entrée | Sortie |
|---|---|---|---|---|
| 1 | Lire les flux | technique | les flux actifs | des pages en base |
| 2 | Explorer le web | LLM | le texte de Julien + les business connus | des pages en base + des flux proposés |
| 3 | Trier les pages | LLM (modèle rapide) | les pages nouvelles | une étiquette par page : enrichit un business existant / signal d'un besoin nouveau / bruit |
| 4 | Formuler des business A et B | LLM | les pages « signal » | des fiches business avec leurs pages de preuve |
| 5 | Dédoublonner | technique | les fiches de A et B | des business au statut `CANDIDATE` |
| 6 | Choisir les business à tester | LLM | les business éligibles | une sélection, autant que de places libres |
| 7 | Refuser les business déjà en test | technique | la sélection | des business au statut `POC_SELECTED` |

Autres décisions :

- **Toute page lue** (flux ou web) est enregistrée dans `listen_docs`, avec
  sa source et le cycle qui l'a trouvée. Elle peut servir de preuve.
- **La liste des flux est en base** (nouvelle table `listen_feeds`) :
  adresse, qui l'a ajoutée (Julien ou une invocation), active ou non,
  nombre de pages ramenées et de pages utiles.
- **Recherche web** : SearXNG, un moteur de recherche open source hébergé
  sur le VPS. Gratuit, sans clé.
- **Garde-fous de volume** (réglages de la policy) :
  - N pages triées au maximum par cycle ;
  - les pages « bruit » sont oubliées après X jours, les preuves sont
    gardées ;
  - un flux qui ne ramène que du bruit pendant K cycles est désactivé.
- **Légalité** : le prompt des invocations qui formulent et choisissent
  dit que le business doit être légal, et les encourage à ne pas s'arrêter
  sur des scrupules moraux qui ne sont pas contraires à la loi.
- Le réglage `listen.poc_business_target` disparaît : on choisit autant de
  business qu'il y a de places libres.
- Les familles de business possibles sont listées dans
  [`DECISIONS_REVUE.md`](../DECISIONS_REVUE.md) (question 32).

**Supprimé.** L'ancienne chaîne de regroupement par mots communs et
l'invocation `cluster_demand`.
