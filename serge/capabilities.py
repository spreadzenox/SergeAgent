#!/usr/bin/env python3
"""Les capacités : ce que le code sait faire, déclaré en base au démarrage.

Une capacité est un savoir-faire général, réglé par des paramètres lus en
base. Elle ne connaît jamais une invocation, une étape ou un business en
particulier. C'est la seule table que le code remplit lui-même : une
capacité retirée du code reste en base, marquée absente
(``available`` = 0), pour que Mission Control signale ce qui s'en servait.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Param:
    name: str
    type: str
    required: bool
    description: str


@dataclass(frozen=True)
class Capability:
    id: str
    title: str
    doc_md: str
    code_path: str
    params: tuple[Param, ...] = field(default_factory=tuple)


CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        'db_read',
        'Lire la base',
        'Lit des lignes de la base à travers un outil de lecture. Chaque'
        ' outil déclare en base les tables, colonnes, filtres et jointures'
        ' qu’il a le droit de lire ; le modèle n’écrit jamais de SQL.',
        'serge/db/query_builder.py',
        (Param('tool_id', 'text', True, 'L’outil de lecture à utiliser.'),),
    ),
    Capability(
        'web_search',
        'Chercher sur le web',
        'Cherche une question sur le web et rend quelques résultats : titre,'
        ' adresse et extrait.',
        'serge/listen/web.py',
        (
            Param('query', 'text', True, 'La recherche à faire.'),
            Param('limit', 'number', False, 'Le nombre de résultats.'),
        ),
    ),
    Capability(
        'memory_search',
        'Chercher dans la mémoire',
        'Cherche des mots dans les leçons, les événements et les tickets de'
        ' Serge, et rend quelques extraits. Lecture seule.',
        'serge/memory/search.py',
        (
            Param('query', 'text', True, 'Les mots à chercher.'),
            Param('types', 'list', False, 'Les sortes de souvenirs visées.'),
            Param('top_k', 'number', False, 'Le nombre d’extraits.'),
        ),
    ),
    Capability(
        'echo',
        'Rendre ses paramètres',
        'Rend tels quels les paramètres qu’on lui donne. Sert aux invocations'
        ' sans LLM qui ne font qu’écrire en base ce qu’on leur transmet, par'
        ' exemple ouvrir un cycle avec le texte de guidage.',
        'serge/interpreter/tools.py',
    ),
    Capability(
        'db_write',
        'Écrire dans la base',
        'Écrit la réponse d’une invocation en base, selon ses règles'
        ' d’écriture : la table, ajouter ou modifier, quelle colonne reçoit'
        ' quel champ. Applique les protections réglées en base (tables'
        ' autorisées, changements de statut permis, doublons) et note chaque'
        ' écriture et chaque refus au journal. Toutes les invocations s’en'
        ' servent ; on ne la donne pas comme outil.',
        'serge/interpreter/writer.py',
    ),
    Capability(
        'seen_table_read',
        'Lire les tables que je vois',
        'Lit toutes les colonnes lisibles d’une table que l’invocation voit'
        ' déjà en version courte : une ligne par son numéro, ou toutes les'
        ' lignes avec un filtre simple, page par page. Les tables permises'
        ' sont calculées à chaque appel à partir de l’invocation : celles où'
        ' elle écrit, plus ou moins les ajustements réglés dans Mission'
        ' Control. Les colonnes lisibles sont réglées une fois par table.',
        'serge/interpreter/seen.py',
        (
            Param('table', 'text', True, 'La table à lire.'),
            Param(
                'column',
                'text',
                False,
                'Une colonne lisible pour filtrer (id pour une seule ligne).',
            ),
            Param(
                'value', 'text', False, 'La valeur que doit avoir la colonne.'
            ),
            Param('page', 'number', False, 'La page (1 pour commencer).'),
        ),
    ),
    Capability(
        'row_history',
        'Lire l’historique d’une ligne',
        'Rend ce qui est arrivé à une ligne que l’invocation voit (ce qu’elle'
        ' traite, ou une table à comparer) : ses derniers événements dans le'
        ' journal, du plus récent au plus ancien, page par page.',
        'serge/interpreter/seen.py',
        (
            Param('table', 'text', True, 'La table de la ligne.'),
            Param('id', 'text', True, 'Le numéro de la ligne.'),
            Param('page', 'number', False, 'La page (1 pour commencer).'),
        ),
    ),
    Capability(
        'request_capability',
        'Demander une nouvelle capacité',
        'Ouvre une demande à Julien quand il manque à Serge un outil ou un'
        ' accès pour faire ce qu’on lui demande.',
        'serge/demande_capacite.py',
        (
            Param('need', 'text', True, 'Ce qui manque, en une phrase.'),
            Param('context', 'text', False, 'Pourquoi on en a besoin.'),
        ),
    ),
)


def ensure_capabilities(conn: sqlite3.Connection) -> None:
    """Déclare en base les capacités du code, sans jamais en effacer.

    Le titre, la description, le chemin et les paramètres suivent le code ;
    une capacité absente du code est marquée ``available`` = 0.

    Args:
        conn: Canon (commit par l'appelant).
    """
    from serge.horloge import iso_utc

    now = iso_utc()
    known = {cap.id for cap in CAPABILITIES}
    for cap in CAPABILITIES:
        conn.execute(
            'INSERT INTO capabilities(id, title, doc_md, available, code_path,'
            ' updated_at) VALUES(?,?,?,1,?,?)'
            ' ON CONFLICT(id) DO UPDATE SET title=excluded.title,'
            ' doc_md=excluded.doc_md, available=1,'
            ' code_path=excluded.code_path',
            (cap.id, cap.title, cap.doc_md, cap.code_path, now),
        )
        conn.execute(
            'DELETE FROM capability_params WHERE capability_id=?', (cap.id,)
        )
        for position, param in enumerate(cap.params):
            conn.execute(
                'INSERT INTO capability_params(capability_id, name, type,'
                ' required, description, position) VALUES(?,?,?,?,?,?)',
                (
                    cap.id,
                    param.name,
                    param.type,
                    int(param.required),
                    param.description,
                    position,
                ),
            )
    for (ident,) in conn.execute('SELECT id FROM capabilities').fetchall():
        if str(ident) not in known:
            conn.execute(
                'UPDATE capabilities SET available=0 WHERE id=?', (ident,)
            )
