# Charte du code

Ces règles s'appliquent à tout ce qui entre dans le dépôt : code, tests,
migrations, valeurs de départ, Mission Control, documentation. Elles valent
pour un humain comme pour un LLM qui code.

**Julien est le seul à modifier cette charte.** Un contributeur peut
proposer un changement, avec sa raison, mais ne l'applique pas lui-même.

Le but : le maximum de capacité économique avec le minimum de code,
lisible et testé.

---

## 1. Avant d'écrire du code : l'échelle

Inspirée du skill [Ponytail](https://github.com/DietrichGebert/ponytail).
On se pose ces questions dans l'ordre, et on s'arrête à la première qui
marche :

1. **Est-ce que ça doit vraiment exister ?** Si le besoin est hypothétique,
   on ne le fait pas.
2. **Est-ce que ça existe déjà dans le dépôt ?** Alors on le réutilise.
3. **Est-ce que la bibliothèque standard de Python le fait ?**
4. **Est-ce qu'un outil déjà présent le fait ?** Exemple : une contrainte
   SQLite plutôt que du code de vérification.
5. **Est-ce qu'une dépendance déjà installée le fait ?** On n'en ajoute
   jamais une pour quelques lignes.
6. **Est-ce que ça tient en une ligne ?**
7. **Seulement ensuite** : le minimum de code qui marche.

**Mais d'abord, comprendre.** On lit tout le code concerné avant de
choisir la solution. Un bug se corrige à sa cause, dans la fonction que
tous les appelants utilisent, pas seulement à l'endroit signalé.

## 2. Règles de code

- **Pas d'abstraction inutile** : pas d'interface pour une seule
  implémentation, pas de réglage pour une valeur qui ne change jamais.
- **Pas de code préparé « pour plus tard ».**
- **Supprimer plutôt qu'ajouter.** Le plus simple plutôt que le plus malin.
- **Peu de fichiers.** Un fichier fait une seule chose, qu'on peut dire en
  une phrase.
- **500 lignes au maximum par fichier Python** dans `kit/` et `serge/`.
  Vérifié par `tests/test_charter.py`.
- **Pas de fichier fourre-tout** (`utils.py`, `helpers.py`, `common.py`).
  Une fonction vit à côté de ce qu'elle protège.
- **Pas d'import circulaire** entre modules du dépôt.
- **Un raccourci assumé est signalé** par un commentaire qui dit sa limite.
  Exemple : `# raccourci : recherche en O(n²), passer à un index si plus
  de 10 000 contacts`.
- **Pas de code mort.** Pas de bouton sans action, de route sans appelant,
  de fonction que personne n'appelle. On termine la capacité ou on
  l'enlève, avec ses tests et sa doc.

**On ne simplifie jamais** : la vérification des données qui viennent de
l'extérieur, la gestion d'erreur qui évite de perdre des données, la
sécurité.

## 3. Nommer les choses

- **Les noms sont en anglais** : fonctions, variables, modules, tables,
  colonnes. Exemple : une « invocation LLM » s'appelle `llm_invocation`
  dans le code.
- **Les textes sont en français** : docstrings, commentaires, doc,
  messages, Mission Control.
- Le code actuel mélange les deux langues. On renomme au fil des
  changements, pas en une seule fois.
- On dit **« invocation LLM »**, jamais « jugement LLM ».

## 4. Les invocations LLM

- On utilise le LLM quand une règle ne suffit pas : texte libre en entrée,
  réponse ouverte, information à aller chercher. Une entrée fermée et une
  réponse dans une liste fixe restent du code.
- Chaque invocation est déclarée en base (`llm_points`). Son prompt, son
  niveau de modèle, ses tools et son interrupteur se règlent dans Mission
  Control. Le code et `config/llm-points.yaml` ne donnent que les valeurs
  de départ.
- Chaque appel est enregistré dans `llm_usage` : invocation, modèle,
  tokens, durée, résultat.
- Une réponse structurée (JSON) est vérifiée par le code avant usage. En
  cas de réponse malformée, on redemande un nombre borné de fois, avec
  l'erreur. Puis on applique le repli prévu.
- **Pas de limite de longueur** sur les réponses du LLM.
- Pour dire « il me manque quelque chose », une invocation utilise le tool
  « Demander une nouvelle capacité ». Pas de champ libre dans la réponse.
- Le code qui décide (ordonnanceur, garde-fous) ne lit jamais un texte
  libre : il lit des champs structurés et des listes fermées.

## 5. La base fait foi

- La base SQLite est la seule source de vérité. Pas de fichier d'état, pas
  de copie d'un fait en JSON ou en constante.
- Le code et les YAML sont des **valeurs de départ** : ils remplissent une
  base neuve, ajoutent les objets nouveaux à une base existante, et ne
  modifient jamais un réglage déjà en base. Détails : [`DB.md`](DB.md).
- Une exception à cette règle doit être justifiée par une contrainte
  technique dure.
- Les empreintes du code sont calculées au démarrage, jamais recopiées à
  la main.

## 6. Les tests

Julien préfère **les tests de bout en bout** à des centaines de petits
tests qui ne testent rien. Trois sortes, par ordre d'importance :

1. **Le test de scénario, par étape.** On part d'un vrai point d'entrée et
   on vérifie le résultat final dans la base et le journal. Le LLM et le
   monde extérieur (web, e-mail, téléphone, Stripe) sont remplacés par des
   faux qui renvoient des réponses écrites à l'avance. Tout le reste est
   réel.
   Exemple, étape 1 : 5 pages en base et 1 place libre → « lancer le
   cycle » → 1 business `POC_SELECTED` avec ses preuves, les doublons
   écartés, chaque décision au journal.
2. **Le test navigateur de Mission Control** (Playwright).
3. **Le test réel avec une vraie clé LLM**, avant chaque push, jamais en
   CI.

Un test de fonction isolée n'existe que si la logique est vraiment
piégeuse. Exemples : la grille de points, le regroupement des contacts.

Pour tout ce qui touche le monde extérieur (envoyer, appeler, payer), on
teste le cas qui passe **et** le cas refusé.

Aucun test de CI n'agit sur le monde réel.

## 7. La documentation

- Un changement qui modifie un comportement, une table, une invocation,
  une page de Mission Control ou une installation met à jour la doc dans
  le même changement. On corrige le paragraphe qui devient faux ; on
  n'ajoute pas une note « aussi, on a changé X ».
- **Écrire pour quelqu'un qui arrive à froid**, humain ou LLM :
  - phrases courtes ;
  - un exemple concret, chiffré, plutôt qu'une formule abstraite ;
  - pas de jargon ni de mots-valises (« hôte », « canon », « contrat »,
    « jonction », « de façon prévisible ») ;
  - décrire ce qui se passe, concrètement.

  À éviter : « Chaque accès injecté a une taille maximale (nombre de
  lignes) sur sa jonction. Si le contenu dépasse, l'hôte coupe de façon
  prévisible (les plus récents d'abord). »
  À écrire : « On donne au plus 50 business à l'invocation. S'il y en a
  plus, elle reçoit les 50 plus récents et un message qui dit combien ont
  été laissés de côté. »
- Où écrire : voir [`PIPELINE.md`](PIPELINE.md) (fonctionnement),
  [`etapes/`](etapes/) (une page par étape), [`MEMOIRE.md`](MEMOIRE.md),
  [`DB.md`](DB.md), [`MISSION_CONTROL.md`](MISSION_CONTROL.md),
  [`installation/`](installation/).

## 8. Les changements

- **Un changement fait une seule chose**, et sa description le dit en une
  phrase.
- **La description d'une PR** (ou d'un commit) répond, en français clair,
  à quatre questions :
  1. Qu'est-ce qui change, vu de l'extérieur ?
  2. Pourquoi ?
  3. Comment on vérifie que ça marche (quel test de scénario) ?
  4. Qu'est-ce qui a été supprimé ?
- Pas de commit direct sur `main` : une branche, une PR, la CI verte.

## 9. Outils

- `uv` et `uv.lock` pour les dépendances. Toute nouvelle dépendance est
  déclarée dans `pyproject.toml`, et son usage est relu avant activation.
- `ruff` pour le style, `ty` pour les types, un scan qui refuse les
  secrets versionnés.
- Ce qui tourne au commit, au push et en CI :
  [`DEV_TOOLING.md`](DEV_TOOLING.md).
