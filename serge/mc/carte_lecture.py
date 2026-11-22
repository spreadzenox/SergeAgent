#!/usr/bin/env python3
"""La carte du pipeline : ce que la base dit de chaque invocation.

Pour chaque invocation en service : ce qui la lance (un bouton, une
horloge, une ligne écrite dans une table), les tables qu'elle lit (par ses
outils de lecture, ou « pour comparer »), celles où elle écrit et quoi
(ses règles d'écriture), ses outils, et les missions qu'elle confie à une
autre invocation. Les liens entre invocations sont lus à part.

Tout vient des tables du pipeline : rien n'est propre à une invocation
ici. ``serge/mc/proj_carte.py`` en fait la carte.

Exemple : « Explorer le web » est lancée par le lien d'« Ouvrir un
cycle », lit ``listen_cycles``, écrit dans ``listen_docs``, et confie la
mission « Fouiller Reddit » à « Fouiller un réseau ».
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

# Les capacités qui confient un envoi ou une relève à l'invocation d'un
# canal du navigateur (``canaux.send_invocation``, ``poll_invocation``).
CANAL = {
    'send_message': 'send_invocation',
    'receive_messages': 'poll_invocation',
}


def minutes(minutes: int) -> str:
    """« toutes les 2 min », « toutes les 6 h », « chaque jour »."""
    if minutes % 1440 == 0:
        jours = minutes // 1440
        return 'chaque jour' if jours == 1 else f'tous les {jours} jours'
    if minutes % 60 == 0:
        return f'toutes les {minutes // 60} h'
    return f'toutes les {minutes} min'


def titres_des_tables(conn: sqlite3.Connection) -> dict[str, str]:
    return {
        str(table): str(titre)
        for table, titre in conn.execute(
            "SELECT table_name, title FROM table_views WHERE title<>''"
        )
    }


def invocations(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    return {
        str(r[0]): {
            'id': str(r[0]),
            'titre': str(r[1]),
            'role': str(r[2] or ''),
            'etape': str(r[3]),
            'sorte': 'llm' if r[4] == 'llm' else 'code',
            'capacite': str(r[5]),
            'capacite_titre': str(r[9]),
            'file': str(r[6] or ''),
            'niveau': str(r[7]),
            'allumee': bool(r[8]),
            'hors_de_serge': bool(r[10]),
            'lance': [],
            'lit': [],
            'ecrit': [],
            'outils': [],
        }
        for r in conn.execute(
            "SELECT i.id, COALESCE(NULLIF(i.title, ''), i.id), i.role,"
            " COALESCE(i.step_id, ''), i.type, COALESCE(i.capability_id, ''),"
            " i.queue_id, COALESCE(i.model_tier, ''), i.enabled,"
            " COALESCE(c.title, ''), COALESCE(c.acts_outside, 0)"
            ' FROM invocations i LEFT JOIN capabilities c'
            " ON c.id=i.capability_id WHERE i.deleted_at=''"
            ' ORDER BY i.rowid'
        )
    }


def declencheurs(
    conn: sqlite3.Connection, noeuds: Mapping[str, dict[str, Any]]
) -> None:
    """Ce qui lance chaque invocation : ``lance`` sur sa case."""
    for r in conn.execute(
        'SELECT id, title, invocation_id, event, table_name, filter_column,'
        ' filter_value, every_minutes, at_time, enabled, lane FROM triggers'
        " WHERE deleted_at='' ORDER BY rowid"
    ):
        case = noeuds.get(str(r[2]))
        if case is None:
            continue
        sorte, table = str(r[3]), str(r[4] or '')
        if sorte == 'button':
            texte, quoi = f'bouton « {r[1]} »', 'bouton'
        elif sorte == 'row_written':
            filtre = f' : {r[5]} = {r[6]}' if r[5] else ''
            texte, quoi = f'une ligne écrite dans {table}{filtre}', 'ligne'
        elif sorte == 'at':
            texte, quoi = f'chaque jour à {r[8]}', 'horloge'
        else:
            texte, quoi = minutes(int(r[7] or 0)), 'horloge'
        case['lance'].append(
            {
                'id': str(r[0]),
                'titre': str(r[1]),
                'sorte': quoi,
                'texte': texte,
                'table': table if sorte == 'row_written' else '',
                'allume': bool(r[9]),
                'couloir': str(r[10] or ''),
            }
        )


def outils(
    conn: sqlite3.Connection,
    noeuds: Mapping[str, dict[str, Any]],
    tables: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Les outils de chaque invocation, les tables qu'elle lit, et les
    missions qu'elle confie (rendues : des traits vers d'autres cases)."""
    lues: dict[str, list[str]] = {}
    for outil, table in conn.execute(
        'SELECT tool_id, table_name FROM tool_db_tables'
        ' ORDER BY tool_id, position'
    ):
        lues.setdefault(str(outil), []).append(str(table))
    services = {
        str(outil): str(service)
        for outil, service in conn.execute(
            "SELECT e.tool_id, COALESCE(NULLIF(s.title, ''), s.id)"
            ' FROM api_endpoints e JOIN api_services s ON s.id=e.service_id'
        )
    }
    cibles = {
        int(lien): str(cible)
        for lien, cible in conn.execute(
            'SELECT invocation_tool_id, value FROM invocation_tool_params'
            " WHERE param_name='invocation' AND source='fixed'"
            ' AND invocation_tool_id<>0'
        )
    }
    lectures: dict[str, dict[str, list[str]]] = {}

    def lit(invocation: str, table: str, par: str) -> None:
        deja = lectures.setdefault(invocation, {}).setdefault(table, [])
        if par not in deja:
            deja.append(par)

    # Les missions confiées par des outils : un seul trait par paire
    # d'invocations, qui les nomme toutes.
    confiees: dict[tuple[str, str], list[str]] = {}
    for r in conn.execute(
        "SELECT it.id, it.invocation_id, t.id, COALESCE(NULLIF(it.label, ''),"
        ' t.titre), t.capability_id, COALESCE(c.title, t.capability_id),'
        ' it.mode, COALESCE(c.acts_outside, 0) FROM invocation_tools it'
        ' JOIN tools t ON t.id=it.tool_id LEFT JOIN capabilities c'
        ' ON c.id=t.capability_id ORDER BY it.invocation_id, it.position'
    ):
        invocation, outil = str(r[1]), str(r[2])
        case = noeuds.get(invocation)
        if case is None:
            continue
        cible = cibles.get(int(r[0]), '')
        case['outils'].append(
            {
                'id': outil,
                'titre': str(r[3]),
                'capacite': str(r[5]),
                'mode': 'reçu d’office' if r[6] == 'given' else 'peut appeler',
                'tables': lues.get(outil, []),
                'service': services.get(outil, ''),
                'mission': cible if cible in noeuds else '',
                'hors_de_serge': bool(r[7]),
            }
        )
        for table in lues.get(outil, []):
            lit(invocation, table, str(r[3]))
        if cible in noeuds:
            confiees.setdefault((invocation, cible), []).append(str(r[3]))
    missions = [
        {
            'id': f'mission:{de}:{vers}',
            'de': de,
            'vers': vers,
            'sorte': 'mission',
            'titre': 'confie en mission : ' + ', '.join(titres),
        }
        for (de, vers), titres in confiees.items()
    ]
    # Une invocation sans LLM qui lit la base par un outil de lecture, et
    # les tables qu'une invocation voit « pour comparer ».
    for invocation, outil in conn.execute(
        'SELECT invocation_id, value FROM invocation_tool_params'
        " WHERE invocation_tool_id=0 AND param_name='tool_id'"
        " AND source='fixed'"
    ):
        for table in lues.get(str(outil), []):
            lit(str(invocation), table, 'sa lecture')
    for invocation, table in conn.execute(
        'SELECT invocation_id, table_name FROM invocation_compare_tables'
        ' WHERE included=1 ORDER BY table_name'
    ):
        lit(str(invocation), str(table), 'pour comparer')
    for invocation, par_table in lectures.items():
        if invocation in noeuds:
            noeuds[invocation]['lit'] = [
                {'table': t, 'titre': tables.get(t, ''), 'par': par}
                for t, par in par_table.items()
            ]
    # Les canaux du navigateur : l'invocation qui envoie ou qui relève
    # leur confie une mission.
    for capacite, colonne in CANAL.items():
        par_cible: dict[str, list[str]] = {}
        for canal, cible in conn.execute(
            f"SELECT titre, {colonne} FROM canaux WHERE {colonne}<>''"
        ):
            par_cible.setdefault(str(cible), []).append(str(canal))
        for cible, canaux in par_cible.items():
            for case in noeuds.values():
                if case['capacite'] == capacite and cible in noeuds:
                    missions.append(
                        {
                            'id': f'canal:{case["id"]}:{cible}',
                            'de': case['id'],
                            'vers': cible,
                            'sorte': 'mission',
                            'titre': 'confie en mission, pour les canaux : '
                            + ', '.join(canaux),
                        }
                    )
    return missions


def ecritures(
    conn: sqlite3.Connection,
    noeuds: Mapping[str, dict[str, Any]],
    tables: Mapping[str, str],
) -> None:
    """Où chaque invocation écrit, et quoi : ``ecrit`` sur sa case."""
    valeurs: dict[int, list[dict[str, str]]] = {}
    for ecriture, colonne, source, valeur in conn.execute(
        'SELECT write_id, column_name, source, value'
        ' FROM invocation_write_values ORDER BY write_id, column_name'
    ):
        valeurs.setdefault(int(ecriture), []).append(
            {
                'colonne': str(colonne),
                'source': str(source),
                'valeur': str(valeur),
            }
        )
    for r in conn.execute(
        'SELECT id, invocation_id, table_name, operation, for_each,'
        ' condition_field, condition_op, condition_value'
        ' FROM invocation_writes ORDER BY invocation_id, position'
    ):
        case = noeuds.get(str(r[1]))
        if case is None:
            continue
        table = str(r[2])
        regles = next(
            (e['regles'] for e in case['ecrit'] if e['table'] == table), None
        )
        if regles is None:
            regles = []
            case['ecrit'].append(
                {
                    'table': table,
                    'titre': tables.get(table, ''),
                    'regles': regles,
                }
            )
        regles.append(
            {
                'operation': str(r[3]),
                'pour_chaque': str(r[4] or ''),
                'condition': f'{r[5]} {r[6]} {r[7]}'.strip() if r[5] else '',
                'colonnes': valeurs.get(int(r[0]), []),
            }
        )


def lire_liens(
    conn: sqlite3.Connection, noeuds: Mapping[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    liens = []
    for r in conn.execute(
        'SELECT id, title, from_invocation_id, to_invocation_id, mode, auto,'
        ' enabled, condition_field, condition_op, condition_value,'
        ' delay_min_setting, lane FROM links'
        " WHERE deleted_at='' ORDER BY rowid"
    ):
        if str(r[2]) not in noeuds or str(r[3]) not in noeuds:
            continue
        liens.append(
            {
                'id': str(r[0]),
                'titre': str(r[1] or r[0]),
                'de': str(r[2]),
                'vers': str(r[3]),
                'sorte': 'lien',
                'par_ligne': r[4] == 'per_row',
                'auto': bool(r[5]),
                'allume': bool(r[6]),
                'condition': f'{r[7]} {r[8]} {r[9]}'.strip() if r[7] else '',
                'delai': str(r[10] or ''),
                'couloir': str(r[11] or ''),
            }
        )
    return liens
