# Matrice LLM / déterministe (C)

Version : 1.1 (2026-09-20)

Cette matrice décrit `config/llm-points.yaml`, le registre runtime et les
projections Mission Control. Chaque point déclare :

- `verdict` et `tier` pour le choix du modèle ;
- `output_mode`, limité à `structured` ou `text` ;
- `external_info`, booléen ;
- `context.tools`, les outils explicitement disponibles ;
- `context.tool_quotas` et `context.db_readers` quand ils sont nécessaires ;
- `garde_fou`, `repli`, `enabled` et, si utile, `note` ou `propagation`.

Les prompts vivent encore dans le code. Aucun prompt DB n'est exigé dans cette
tranche. Les tokens et le coût sont mesurés dans `llm_usage`; le runtime ne
interprète pas de dimensionnement déclaré par point.

## Règles transverses

- `output_mode: structured` est utilisé lorsqu'une validation déterministe
  attend un objet, un enum, une liste ou un score.
- `output_mode: text` est utilisé pour un message, un script, un résumé ou une
  explication libre.
- `external_info` indique seulement si le jugement peut exploiter une source
  externe ; il n'ouvre aucun outil à lui seul.
- Un outil est offert uniquement s'il apparaît dans `context.tools` ou vient
  du `tool_id` d'une capsule de `context.db_readers`, possède un handler et
  reste autorisé par la projection canonique.
- `db_readers` décrit les capsules mémoire affectées au point. Leur
  `tool_id` sous-jacent est projeté dans `llm_point_tools`; chaque tool DB
  individualisé expose un schéma construit depuis son catalogue relationnel.
- Les appels sont journalisés dans `llm_usage` et les tours d'outils sont
  bornés par `quotas.llm_outil_tours_max`.
- Les guards, l'idempotence, les transitions d'état, les compteurs U1-U5 et
  les writers restent déterministes.

## Points Déclarés

| Groupe | Points |
|---|---|
| Méta-funnel | `draft_hypothesis_smoke`, `draft_hypothesis_full`, `plan_scale`, `options_pivot`, `resume_test` |
| Prospection | `qualify_prospect`, `fill_slots`, `write_followup`, `voice_script`, `voice_dialog`, `summarize_thread`, `score_lead_departage` |
| Builder | `build_artifact`, `review_build`, `summarize_build_debt` |
| Observation | `classify_reply`, `extract_meeting`, `reply_intent`, `review_other`, `score_call` |
| Collect | `draft_price` |
| Allocation | `judge_allocator` |
| Mémoire | `consolidate`, `edit_serge_md` |
| Interactivité | `render_context_fr`, `classify_owner_intent`, `judge_consequence` |
| Écoute | `cluster_demand`, `listen_discover_needs_a`, `listen_discover_needs_b`, `listen_choose_poc` |
| Installation | `install_guide` |

## Sécurité

La sécurité des sorties reste portée par les checkers et les builders
déterministes. Les mots interdits, la minimisation PII et les contrôles de
publication ne sont pas des champs du registre LLM : ils restent dans les
points d'écriture concernés.
