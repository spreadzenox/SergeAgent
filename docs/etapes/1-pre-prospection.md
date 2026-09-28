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

Décisions : Q9, Q14, Q32, Q33 et Q65 de
[`DECISIONS_REVUE.md`](../DECISIONS_REVUE.md). C'est le lot 7 du
[`TODO.md`](../../TODO.md).

L'étape devient **deux processus**, entièrement décrits en base.

**La veille** tourne toute seule, toutes les 6 heures (réglage), sans
LLM : elle lit les flux RSS actifs et enregistre leurs pages nouvelles.
Serge choisit ses flux lui-même (« Explorer le web » les ajoute), sans
accord de Julien.

**Le cycle** se lance à la main depuis la page Écoute (plus tard,
automatiquement), s'il reste une place libre en prospection légère. Les
invocations tournent l'une après l'autre :

| # | Invocation | Type | Entrée | Sortie |
|---|---|---|---|---|
| 1 | Ouvrir un cycle | sans LLM | le texte de guidage de Julien | le cycle |
| 2 | Explorer le web | LLM moyen | le texte de guidage + les business connus | au plus 30 pages retenues (aperçu seulement) + au plus 2 flux RSS |
| 3 | Rattacher les pages au cycle | sans LLM | les pages pas encore triées (flux et web) | au plus 60 pages pour ce cycle, les plus récentes d'abord |
| 4 | Trier les pages | LLM rapide, par paquets de 20 | l'aperçu des pages | une étiquette par page : enrichit un business existant (rattachée comme preuve) / besoin nouveau / bruit |
| 5 | Formuler des business A | LLM intelligent | l'aperçu des pages « besoin nouveau » pas encore utilisées ; les pages qu'elle veut, lues en entier | 3 fiches (réglage), chacune avec ses preuves et sa famille |
| 6 | Formuler des business B | LLM intelligent | la même chose (sans les pages utilisées par A), et les business écrits par A | 3 fiches |
| 7 | Choisir les business à tester | LLM moyen | les candidats et les business en test | autant de `POC_SELECTED` que de places libres |

Puis le cycle est fermé : rien n'est encore prévu après.

**Ce qui n'est pas une invocation.** Dédoublonner et refuser un business
déjà en test sont des règles déclarées en base et appliquées au moment où
la réponse est écrite (voir [`LOT6_CONCEPTION.md`](../LOT6_CONCEPTION.md)).
Le doublon est repéré par la règle de doublons de la table des business ;
le refus vient de la règle des changements de statut permis, qui
n'autorise le passage à `POC_SELECTED` que depuis `CANDIDATE`.

Autres décisions :

- **Serge ne fait pas deux fois la même chose.** B voit les business
  écrits par A, comme toute invocation qui écrit des business reçoit la
  version courte de ceux déjà en base. Le prompt de A et de B dit de ne
  jamais reproposer un business qui existe déjà. On ne passe jamais la
  réponse de A dans le prompt de B : B voit seulement ce que A a écrit en
  base.
- **Ne pas saturer les invocations.** « Explorer » et « Trier » ne lisent
  qu'un aperçu de chaque page (5 lignes, réglage ; une ligne = un titre,
  un paragraphe ou un élément de liste) ; seules A et B lisent une page
  en entier. Une seule capacité « lire une page », réglée par ce nombre
  de lignes, sans navigateur. En base, on garde l'adresse et l'aperçu,
  jamais le texte entier ; pour une page de flux, l'aperçu est le résumé
  du flux.
- **Les pages gardées.** Seules les pages qu'« Explorer » retient et celles
  des flux sont enregistrées (`listen_docs`), avec leur source, le cycle
  qui les a trouvées, leur aperçu et leur étiquette. Une page déjà triée
  n'est jamais représentée comme nouvelle. Une fois leur idée écrite, A
  et B reclassent les pages utilisées : une page « besoin nouveau »
  devient une preuve rattachée à leur business. B ne reçoit donc que les
  pages que A n'a pas utilisées ; celles qui restent après B repassent au
  cycle suivant, sans être retriées.
- **Une fiche de business** cite au moins une page de preuve et sa
  famille (les 11 familles de Q32).
- **Les places.** Une place est occupée par un business `POC_SELECTED`,
  `SMOKE_READY`, `SMOKE_RUNNING` ou `SMOKE_DONE`, jusqu'au choix de
  l'étape 4. « Choisir » en choisit au plus autant que de places libres ;
  le quota refuse le surplus. Quand tout est pris, le bouton du cycle est
  bloqué et affiche « 3 places sur 3 occupées ».
- **La liste des flux est en base** (nouvelle table `listen_feeds`) :
  adresse, ajouté par quelle invocation (« Explorer », au plus 2 par
  cycle), actif ou non. Au plus 20 pages lues par flux à chaque passage ;
  le surplus attend le cycle suivant. Mission Control
  montre, pour chaque flux, les pages ramenées et les pages utiles ; on
  peut le couper à la main.
- **Recherche web** : DuckDuckGo au lot 7, SearXNG (un moteur open source
  hébergé sur le serveur) au lot 12.
- **Garde-fous de volume** (réglages des invocations marqués « policy »,
  modifiables sur la page Policy) : 60 pages triées au plus par cycle ;
  une page « bruit » ou jamais triée est supprimée après 30 jours (jamais
  une preuve),
  avec une note au journal ; un flux qui ne ramène que du bruit est coupé
  à la main au lot 7, automatiquement après 5 cycles plus tard.
- **Légalité** : le prompt des invocations qui formulent et choisissent
  dit que le business doit être légal, et les encourage à ne pas s'arrêter
  sur des scrupules moraux qui ne sont pas contraires à la loi (Q33).
- **Marché** : la France d'abord, recherches en français, pages en anglais
  acceptées.
- Le réglage `listen.poc_business_target` a disparu (lot 6) : on choisit
  autant de business qu'il y a de places libres.
- La démo du lot 6 est retirée, avec les business et les cycles qu'elle a
  laissés sur le serveur de Julien.

**Supprimé.** L'ancienne chaîne de regroupement par mots communs et
l'invocation `cluster_demand`.
