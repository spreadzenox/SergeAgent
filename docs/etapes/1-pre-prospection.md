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

**Un demi-cycle de démonstration**, décrit dans `config/pipeline.yaml`,
pour vérifier que le pipeline en base s'enregistre, s'affiche dans Mission
Control et tourne. Sur la page Écoute, le bouton « Lancer un cycle
(démo) » (un déclencheur « bouton » en base) crée une tâche avec le texte
de guidage ; elle ne tourne que si Serge a été démarré :

1. « Ouvrir un cycle (démo) », sans LLM, enregistre le cycle
   (`listen_cycles`) avec le texte de guidage ;
2. « Formuler des idées (démo) » reçoit le cycle (lecture d'office), la
   version courte des business déjà connus (numéro et nom, les plus
   récents d'abord) et ses leçons ; elle peut chercher sur le web et dans
   la mémoire, lire la fiche complète d'un business et son historique, et
   écrit deux business `CANDIDATE`. La règle de doublons de la table `ventures`
   (72 % de mots en commun sur le nom et la description) écarte une fiche
   trop proche d'un business existant, avec une note au journal ;
3. « Choisir un business (démo) » passe au plus un candidat en
   `POC_SELECTED`. La règle des changements de statut refuse un business
   qui n'est plus candidat.

Le vrai cycle, en sept invocations, remplacera cette démonstration au
lot 7.

### Ce qui ne marche plus depuis le lot 6

L'ancien cycle écrit en dur (« Explorer les besoins A » et « B »,
« Choisir les business à tester ») et la collecte des flux RSS sont rangés
dans `pas_encore_branche/` (`serge/workers/listen.py`,
`serge/points/listen_pts.py`, `serge/listen/memory.py`). Leurs prompts
serviront au lot 7.

### Ce qui manque

- **Aucune page n'est collectée** : pas de liste de flux RSS, pas de
  collecte. Seul le script de démo `scripts/mc-demo.py` met des pages en
  base.
- **Les pages trouvées par la recherche web ne sont pas gardées.** Les
  preuves d'un besoin ne peuvent citer que des pages de `listen_docs`.
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
| 5 | Dédoublonner | règle d'écriture | les fiches de A et B | des business au statut `CANDIDATE` |
| 6 | Choisir les business à tester | LLM | les business éligibles | une sélection, autant que de places libres |
| 7 | Refuser les business déjà en test | règle d'écriture | la sélection | des business au statut `POC_SELECTED` |

Les étapes 5 et 7 ne sont plus des invocations à part : ce sont des
règles déclarées en base et appliquées au moment où la réponse est écrite
(voir [`LOT6_CONCEPTION.md`](../LOT6_CONCEPTION.md)). Le doublon est
repéré par la règle de doublons de la table des business ; le refus vient
de la règle des changements de statut permis, qui n'autorise le passage à
`POC_SELECTED` que depuis `CANDIDATE`. Aucune de ces sept étapes n'a de
code qui lui est propre.

Autres décisions :

- **Toute page lue** (flux ou web) est enregistrée dans `listen_docs`, avec
  sa source et le cycle qui l'a trouvée. Elle peut servir de preuve.
- **La liste des flux est en base** (nouvelle table `listen_feeds`) :
  adresse, qui l'a ajoutée (Julien ou une invocation), active ou non,
  nombre de pages ramenées et de pages utiles.
- **Recherche web** : SearXNG, un moteur de recherche open source hébergé
  sur le VPS. Gratuit, sans clé.
- **Garde-fous de volume** (réglages des invocations marqués « policy »,
  modifiables sur la page Policy ; la section « Écoute » de la policy
  générale a été retirée au lot 6) :
  - N pages triées au maximum par cycle ;
  - les pages « bruit » sont oubliées après X jours, les preuves sont
    gardées ;
  - un flux qui ne ramène que du bruit pendant K cycles est désactivé.
- **Légalité** : le prompt des invocations qui formulent et choisissent
  dit que le business doit être légal, et les encourage à ne pas s'arrêter
  sur des scrupules moraux qui ne sont pas contraires à la loi.
- Le réglage `listen.poc_business_target` a disparu (lot 6) : on choisit
  autant de business qu'il y a de places libres. Le quota « au plus 3
  business choisis » existe déjà ; « Choisir » doit voir le statut des
  business en test pour compter les places (voir le lot 7 du
  [`TODO.md`](../../TODO.md)).
- **À trancher au lot 7** : B écrit des business, donc elle reçoit
  d'office la version courte de ceux déjà en base, y compris ceux de A
  si A passe avant. Pour que B ne voie jamais A, on peut lui retirer les
  business de ses tables à comparer (les doublons sont écartés à
  l'écriture) ou ne lui montrer que ceux d'avant le cycle.
- Les familles de business possibles sont listées dans
  [`DECISIONS_REVUE.md`](../DECISIONS_REVUE.md) (question 32).

**Supprimé.** L'ancienne chaîne de regroupement par mots communs et
l'invocation `cluster_demand`.
