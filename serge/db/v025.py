#!/usr/bin/env python3
"""Migration v25 : retirer les tables de l'ancien fonctionnement (lot 6).

Le pipeline est maintenant décrit dans les tables de la v24 et exécuté par
l'interpréteur (``serge/interpreter/``). Les anciennes tables sont
supprimées :

- ``llm_points``, ``tech_invocations`` → ``invocations`` ;
- ``llm_point_tools`` et les quatre tables des « capsules »
  (``db_readers``, ``llm_point_readers``, ``db_reader_fixed_params``,
  ``db_reader_fixed_joins``) → ``invocation_tools`` et
  ``invocation_tool_params`` ;
- ``etape_liens`` → ``links`` ;
- ``work_items`` → ``tasks`` et ``task_params`` ;
- ``brique_canaux``, qui reliait un canal aux anciennes invocations.

La table ``tools`` est recréée sans ``kind`` : un outil dit maintenant
quelle capacité il utilise (``capability_id``). Le catalogue de lecture
(``tool_db_*``) est vidé, puis rempli de nouveau par
``config/pipeline.yaml`` au démarrage. La colonne ``kinds_json`` des étapes
et les interrupteurs ``kind.*`` et ``llm.*`` disparaissent : on coupe
maintenant une étape, une file ou une invocation.

Ce qui existait avant n'est pas recopié (décision Q58) : les tâches en
attente de l'ancien runner sont perdues, et les réglages des anciennes
invocations restent lisibles dans ``pas_encore_branche/``.
"""

from __future__ import annotations

import sqlite3

SCRIPT = """
DROP TABLE IF EXISTS llm_points;
DROP TABLE IF EXISTS llm_point_tools;
DROP TABLE IF EXISTS tech_invocations;
DROP TABLE IF EXISTS db_readers;
DROP TABLE IF EXISTS llm_point_readers;
DROP TABLE IF EXISTS db_reader_fixed_params;
DROP TABLE IF EXISTS db_reader_fixed_joins;
DROP TABLE IF EXISTS etape_liens;
DROP TABLE IF EXISTS work_items;
DROP TABLE IF EXISTS brique_canaux;
DROP TABLE IF EXISTS tools;
CREATE TABLE tools (
    id TEXT PRIMARY KEY,
    titre TEXT NOT NULL DEFAULT '',
    doc_md TEXT NOT NULL DEFAULT '',
    capability_id TEXT NOT NULL DEFAULT '',
    montre_partout INTEGER NOT NULL DEFAULT 0
        CHECK (montre_partout IN (0, 1))
);
DELETE FROM tool_db_tables;
DELETE FROM tool_db_columns;
DELETE FROM tool_db_filters;
DELETE FROM tool_db_filter_values;
DELETE FROM tool_db_joins;
DELETE FROM tool_db_params;
DELETE FROM tool_db_param_enums;
DELETE FROM runtime_flags WHERE name LIKE 'kind.%' OR name LIKE 'llm.%';
"""


def apply_v025(connection: sqlite3.Connection) -> None:
    """Supprime les anciennes tables et recrée ``tools``."""
    connection.executescript(SCRIPT)
    columns = {
        str(row[1])
        for row in connection.execute('PRAGMA table_info(pipeline_steps)')
    }
    if 'kinds_json' in columns:
        connection.execute('ALTER TABLE pipeline_steps DROP COLUMN kinds_json')
