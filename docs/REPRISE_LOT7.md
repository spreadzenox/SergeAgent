# Reprendre le lot 7 (l'étape 1 en base)

Ce dossier dit où en est le lot 7 et ce qu'il reste à faire. Pour les
commandes de vérification et les règles de travail, voir
[`REPRISE_LOT6.md`](REPRISE_LOT6.md) (parties « Lancer les vérifications
en local » et « Règles de travail à garder ») : elles valent toujours.

## À lire d'abord

1. [`TODO.md`](../TODO.md), partie « Étape 1 — Pré-prospection » : la
   liste des tâches, cochées.
2. [`DECISIONS_REVUE.md`](DECISIONS_REVUE.md), question Q65 : toutes les
   réponses de Clem sur l'étape 1.
3. [`LOT7_CONCEPTION.md`](LOT7_CONCEPTION.md) : ce qui a été construit
   (le pipeline de l'étape 1 en base, et les ajouts à l'interpréteur).
4. [`etapes/1-pre-prospection.md`](etapes/1-pre-prospection.md) : l'étape
   vue de l'extérieur.

## Où on en est

Tout est construit sur la branche `Clem`, pas encore dans `main` :
l'étape 1 est décrite dans `config/pipeline.yaml` (la veille, le cycle,
l'oubli des pages, deux boutons), l'interpréteur a gagné ce qu'il fallait
(lire une page ou un flux, lectures par paquets, limite d'appels par
outil, conditions de quota sur un bouton, suppression, déclencheur
horaire par ligne), la migration v29 range les nouvelles tables, et la
page Écoute de Mission Control montre tout. Les tests :
`tests/test_etape1_cycle.py` (le cycle complet avec un faux modèle),
`tests/test_etape1_veille.py`, `tests/test_etape1_mc.py`.

## Ce qu'il reste à faire

1. **Montrer tous les prompts à Clem** avant la fusion (Q65).
2. **Fusionner dans `main`**, une seule fois pour tout le lot, après
   l'accord de Clem. Le déploiement met à jour le serveur de Julien.
3. **Sur le serveur de Julien**, après la fusion : si la démo du lot 6 a
   laissé un cycle ouvert, cliquer une fois sur « Abandonner le cycle en
   cours » ; « Effacer les idées (test) » détruit les business de la démo.
4. **Julien lance le premier vrai cycle**, avec 1 idée par invocation
   (réglage « nombre d'idées » de A et de B, page Policy) pour un essai
   peu cher, puis 3.

Puis le lot 8 : les conversations avec les prospects et les clients.
