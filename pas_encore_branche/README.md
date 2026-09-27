# Code pas encore branché

Ce dossier garde le code qui a été retiré de la production au lot 6, quand
Serge est passé à un pipeline entièrement décrit en base. Il n'est pas
détruit, parce qu'il contient beaucoup de choses utiles pour les lots
suivants : des prompts travaillés, des enchaînements, des règles.

Les fichiers gardent le chemin qu'ils avaient dans le dépôt. Exemple :
`pas_encore_branche/serge/points/write.py` était `serge/points/write.py`.

Ce dossier n'est ni importé, ni testé, ni vérifié par les outils de qualité
du code. Pour réutiliser une idée, on la réécrit dans le pipeline en base
(`config/pipeline.yaml`) ou comme capacité générale : jamais comme du code
propre à une invocation. Voir la règle en tête de [`TODO.md`](../TODO.md).

Ce qui s'y trouve :

- `serge/workers/`, `serge/scheduler.py`, `serge/runner.py`,
  `scripts/serge-runner.py` : l'ancien runner et les enchaînements en dur
  (cycle d'écoute, relève du mail, réponses, envois, appels,
  consolidation).
- `serge/points/`, `config/llm-points.yaml`, `serge/llm_registre.py` : le
  code et les prompts de chaque invocation LLM.
- `serge/llm/boucle.py`, `serge/llm/outils_exec.py` : l'ancienne boucle
  d'outils.
- `serge/db_readers.py`, `serge/db_reader_exec.py` : les anciennes
  « capsules » et le catalogue de lecture de départ.
- `serge/observe/router.py` : le routage des réponses reçues (dont le
  blocage de toutes les adresses d'une personne qui se désinscrit).
- `serge/memory/consolidate.py` : la consolidation de la mémoire.
- `serge/discord/owner_flow.py`, `serge/discord/owner_in.py` : les messages
  libres de Julien sur Discord.
- `serge/mc/llm_roles.py` : pour chaque invocation, un texte écrit à la
  main (son rôle, ce qu'elle reçoit, ce qu'elle rend) qu'affichait
  Mission Control. Le rôle vit maintenant dans `invocations.role`.
- `serge/allocator/`, `serge/tech_registre.py`, `serge/catalogue.py`,
  `serge/outils.py`, `serge/listen/memory.py`.
- Une copie de `serge/registry.py`, `serge/llm/runtime.py` et
  `serge/coupe_circuit.py` telles qu'avant le lot 6.
- `tests/` : les tests de tout ce code.
