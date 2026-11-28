#!/usr/bin/env python3
"""Modifier un objet déjà en base, une seule fois, sans écraser Julien.

``config/pipeline.yaml`` n'écrase jamais un objet déjà en base. Quand il
faut changer une valeur d'un objet qui existe déjà sur les instances (par
exemple les tours d'outils d'une invocation, de 25 à 10), on l'écrit dans
la section ``changes`` du fichier :

    changes:
      - id: moins_de_tours
        why: Avec plusieurs outils par tour, 10 tours suffisent.
        table: invocations
        where: {id: <l'invocation>}
        set: {max_tool_turns: {from: 25, to: 10}}

Chaque modification est appliquée une seule fois par instance, et
seulement si la valeur en base est encore celle d'origine (``from``) : une
valeur changée dans Mission Control est gardée. Le résultat est noté dans
``pipeline_changes`` (visible dans Mission Control, page SQLite). Le
libellé d'un champ d'un bouton change de la même façon (table
``trigger_params``, avec ``where: {trigger_id, param_name}``).

Un outil nouveau d'une invocation déjà en base s'ajoute de la même façon,
une seule fois, à la fin de ses outils (un outil retiré ensuite ne revient
pas). De même pour un champ nouveau de sa réponse (``add_outputs``), une
valeur nouvelle d'une de ses écritures (``add_write_values``, avec le rang
``write`` de l'écriture) et un paramètre nouveau d'un déclencheur
(``add_trigger_params``, avec ``trigger``). À l'inverse, un champ de la
réponse (``remove_outputs``), une valeur d'une écriture
(``remove_write_values``) ou une colonne lue par un outil de lecture
(``remove_tool_columns``, avec ``tool``) se retirent une seule fois :
exemple, le rythme des relances, sorti du plan d'un POC (Q37, corrigée
par Q92). Un outil d'une invocation aussi (``remove_tools``) : le
navigateur du constructeur (``serge/pipeline_changes_remove.py``). Dans un
``set``, ``replace`` (une liste de ``{old, new}``) remplace seulement des
passages d'un texte : un prompt changé ailleurs dans Mission Control garde
ses changements. Un paramètre figé d'un outil d'une invocation
(``set_tool_params``, avec ``tool``) change comme une valeur : seulement
s'il vaut encore celle d'origine. Un paramètre de plus d'un lien
(``add_link_params``), d'une invocation sans LLM (``add_params``) ou d'un
outil d'une invocation (``add_tool_params``, avec ``tool`` : un paramètre
que le modèle ne choisit plus) s'ajoute aussi une seule fois
(``serge/pipeline_changes_params.py``), comme une règle d'écriture de plus
d'une invocation (``add_writes``, ``serge/pipeline_changes_writes.py``).

    changes:
      - id: un_outil_de_plus
        why: L'invocation lit aussi l'e-mail du contact.
        invocation: <l'invocation>
        add_tools:
          - {tool: <l'outil>, mode: given, label: Son e-mail}
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.interpreter.rules import safe_name, table_columns
from serge.pipeline_changes_params import (
    add_link_params,
    add_params,
    add_tool_params,
)
from serge.pipeline_changes_remove import (
    invocation_absente,
    remove_outputs,
    remove_tool_columns,
    remove_tools,
    remove_trigger_conditions,
    remove_write_values,
)
from serge.pipeline_changes_writes import add_writes
from serge.seed_base import PipelineSeedError, seed_tool_link

# Les tables du pipeline qu'une modification peut viser.
TABLES = frozenset(
    {
        'invocations',
        'invocation_tools',
        'invocation_tool_params',
        'invocation_settings',
        'invocation_output_fields',
        'links',
        'triggers',
        'trigger_params',
        'table_quotas',
        'table_views',
        'table_view_columns',
        'llm_models',
        'policy_sections',
        'policy_settings',
        'serge_texts',
    }
)


def _result(
    conn: sqlite3.Connection,
    table: str,
    where: Mapping[str, Any],
    changes: Mapping[str, Any],
) -> str:
    """Applique une modification ; rend ce qui s'est passé, en clair."""
    columns = table_columns(conn, table)
    for name in [*where, *changes]:
        if safe_name(str(name)) not in columns:
            raise PipelineSeedError(
                f'changes : colonne absente {table}.{name}'
            )
    clause = ' AND '.join(f'"{name}"=?' for name in where)
    rows = conn.execute(
        f'SELECT rowid, * FROM "{table}" WHERE {clause}',
        [str(v) for v in where.values()],
    ).fetchall()
    if not rows:
        return 'objet absent'
    if len(rows) > 1:
        raise PipelineSeedError(f'changes : plusieurs lignes dans {table}')
    names = ['rowid', *columns]
    current = dict(zip(names, rows[0], strict=True))
    parts = []
    for name, spec in changes.items():
        now = str(current[name] if current[name] is not None else '').strip()
        if 'replace' in spec:
            parts.append(_replace(conn, table, current, name, now, spec))
            continue
        # Un texte (un prompt) se compare sans ses blancs de fin, comme il
        # est rangé en base.
        before, after = str(spec['from']).strip(), str(spec['to']).strip()
        if now == after:
            parts.append(f'{name} déjà à jour')
        elif now != before:
            parts.append(f'{name} gardé (changé dans Mission Control)')
        else:
            conn.execute(
                f'UPDATE "{table}" SET "{name}"=? WHERE rowid=?',
                (after, current['rowid']),
            )
            parts.append(
                f'{name} modifié'
                if '\n' in after
                else f'{name} : {before or "(vide)"} → {after}'
            )
    return ' ; '.join(parts)


def _replace(
    conn: sqlite3.Connection,
    table: str,
    current: Mapping[str, Any],
    name: str,
    now: str,
    spec: Mapping[str, Any],
) -> str:
    """Remplace des passages d'un texte (un prompt) : ``replace`` est une
    liste de ``{old, new}``. Un passage absent (changé dans Mission
    Control) est gardé ; le reste du texte n'est jamais touché."""
    texte, faits, gardes = now, 0, 0
    for pair in spec['replace']:
        old, new = str(pair['old']).strip(), str(pair['new']).strip()
        # Le nouveau passage peut contenir l'ancien (un paragraphe ajouté
        # avant « Règles : ») : déjà là, il ne s'ajoute pas une seconde fois.
        if new in texte:
            continue
        if old in texte:
            texte, faits = texte.replace(old, new, 1), faits + 1
        else:
            gardes += 1
    if texte != now:
        conn.execute(
            f'UPDATE "{table}" SET "{name}"=? WHERE rowid=?',
            (texte, current['rowid']),
        )
    if gardes:
        return f'{name} : {faits} passage(s) remplacé(s), {gardes} gardé(s) (changés dans Mission Control)'
    return (
        f'{name} : {faits} passage(s) remplacé(s)'
        if faits
        else f'{name} déjà à jour'
    )


def _add_tools(conn: sqlite3.Connection, invocation: str, raw: Any) -> str:
    """Ajoute des outils à une invocation déjà en base ; rend ce qui s'est
    passé, en clair. Un outil déjà lié (même outil, même mode) est gardé."""
    if not isinstance(raw, list) or not all(
        isinstance(tool, Mapping) and tool.get('tool') for tool in raw
    ):
        raise PipelineSeedError('changes : add_tools, une liste d’outils')
    if not conn.execute(
        'SELECT 1 FROM invocations WHERE id=?', (invocation,)
    ).fetchone():
        return 'objet absent'
    parts = []
    for tool in raw:
        tool_id, mode = str(tool['tool']), str(tool.get('mode', 'callable'))
        if conn.execute(
            'SELECT 1 FROM invocation_tools WHERE invocation_id=?'
            ' AND tool_id=? AND mode=?',
            (invocation, tool_id, mode),
        ).fetchone():
            parts.append(f'{tool_id} déjà là')
            continue
        position = conn.execute(
            'SELECT COALESCE(MAX(position) + 1, 0) FROM invocation_tools'
            ' WHERE invocation_id=?',
            (invocation,),
        ).fetchone()[0]
        seed_tool_link(conn, invocation, tool, int(position))
        parts.append(f'{tool_id} ajouté')
    return ' ; '.join(parts)


def _add_outputs(conn: sqlite3.Connection, invocation: str, raw: Any) -> str:
    """Ajoute des champs à la réponse d'une invocation déjà en base ; un
    champ déjà là (même chemin) est gardé."""
    if not isinstance(raw, list) or not all(
        isinstance(out, Mapping) and out.get('path') and out.get('type')
        for out in raw
    ):
        raise PipelineSeedError('changes : add_outputs, une liste de champs')
    if invocation_absente(conn, invocation):
        return 'objet absent'
    parts = []
    for out in raw:
        path = str(out['path'])
        if conn.execute(
            'SELECT 1 FROM invocation_output_fields WHERE invocation_id=?'
            ' AND path=?',
            (invocation, path),
        ).fetchone():
            parts.append(f'{path} déjà là')
            continue
        position = conn.execute(
            'SELECT COALESCE(MAX(position) + 1, 0) FROM'
            ' invocation_output_fields WHERE invocation_id=?',
            (invocation,),
        ).fetchone()[0]
        conn.execute(
            'INSERT INTO invocation_output_fields(invocation_id, path, type,'
            ' choices, required, description, position)'
            ' VALUES(?,?,?,?,?,?,?)',
            (
                invocation,
                path,
                str(out['type']),
                ', '.join(str(c) for c in out.get('choices') or []),
                int(bool(out.get('required', True))),
                str(out.get('description', '')),
                int(position),
            ),
        )
        parts.append(f'{path} ajouté')
    return ' ; '.join(parts)


def _add_write_values(
    conn: sqlite3.Connection, invocation: str, write: Any, raw: Any
) -> str:
    """Ajoute des valeurs à une écriture d'une invocation déjà en base
    (son rang ``write`` dans ``writes``) ; une colonne déjà écrite est
    gardée."""
    if not isinstance(raw, Mapping) or not isinstance(write, int):
        raise PipelineSeedError(
            'changes : add_write_values, un rang write et des valeurs'
        )
    if invocation_absente(conn, invocation):
        return 'objet absent'
    row = conn.execute(
        'SELECT id FROM invocation_writes WHERE invocation_id=? AND position=?',
        (invocation, write),
    ).fetchone()
    if row is None:
        return 'écriture absente'
    parts = []
    for column, spec in raw.items():
        if not isinstance(spec, Mapping):
            raise PipelineSeedError(f'changes : valeur de {column} mal écrite')
        if conn.execute(
            'SELECT 1 FROM invocation_write_values WHERE write_id=?'
            ' AND column_name=?',
            (row[0], str(column)),
        ).fetchone():
            parts.append(f'{column} déjà là')
            continue
        conn.execute(
            'INSERT INTO invocation_write_values(write_id, column_name,'
            ' source, value) VALUES(?,?,?,?)',
            (
                row[0],
                str(column),
                str(spec['source']),
                str(spec.get('value', '')),
            ),
        )
        parts.append(f'{column} ajouté')
    return ' ; '.join(parts)


def _add_trigger_params(
    conn: sqlite3.Connection, trigger: str, raw: Any
) -> str:
    """Ajoute des paramètres à un déclencheur déjà en base (un champ ou une
    case de plus dans le formulaire d'un bouton) ; un paramètre déjà là est
    gardé."""
    if not isinstance(raw, Mapping):
        raise PipelineSeedError('changes : add_trigger_params, des paramètres')
    if not conn.execute(
        'SELECT 1 FROM triggers WHERE id=?', (trigger,)
    ).fetchone():
        return 'objet absent'
    parts = []
    for name, spec in raw.items():
        if not isinstance(spec, Mapping) or 'source' not in spec:
            raise PipelineSeedError(f'changes : paramètre {name} mal écrit')
        if conn.execute(
            'SELECT 1 FROM trigger_params WHERE trigger_id=? AND param_name=?',
            (trigger, str(name)),
        ).fetchone():
            parts.append(f'{name} déjà là')
            continue
        conn.execute(
            'INSERT INTO trigger_params(trigger_id, param_name, source, value)'
            ' VALUES(?,?,?,?)',
            (
                trigger,
                str(name),
                str(spec['source']),
                str(spec.get('value', '')),
            ),
        )
        parts.append(f'{name} ajouté')
    return ' ; '.join(parts)


def _set_tool_params(
    conn: sqlite3.Connection, invocation: str, tool: str, raw: Any
) -> str:
    """Change des paramètres figés d'un outil d'une invocation déjà en base,
    ``{param: {from, to}}`` ; une valeur changée dans Mission Control est
    gardée."""
    if not isinstance(raw, Mapping) or not all(
        isinstance(spec, Mapping) and 'from' in spec and 'to' in spec
        for spec in raw.values()
    ):
        raise PipelineSeedError(
            'changes : set_tool_params, des paramètres {from, to}'
        )
    if invocation_absente(conn, invocation):
        return 'objet absent'
    parts = []
    for name, spec in raw.items():
        lignes = conn.execute(
            'SELECT p.rowid, p.value FROM invocation_tool_params p'
            ' JOIN invocation_tools t ON t.id=p.invocation_tool_id'
            ' WHERE t.invocation_id=? AND t.tool_id=? AND p.param_name=?',
            (invocation, tool, str(name)),
        ).fetchall()
        if not lignes:
            parts.append(f'{name} absent')
            continue
        avant, apres = str(spec['from']), str(spec['to'])
        for rowid, valeur in lignes:
            if str(valeur) == apres:
                parts.append(f'{name} déjà à jour')
            elif str(valeur) != avant:
                parts.append(f'{name} gardé (changé dans Mission Control)')
            else:
                conn.execute(
                    'UPDATE invocation_tool_params SET value=? WHERE rowid=?',
                    (apres, rowid),
                )
                parts.append(f'{name} modifié')
    return ' ; '.join(parts)


# Les sortes de modification qui visent une invocation (``invocation``), et
# les autres, chacune avec ce qu'elle vise (voir ``apply_changes``).
_PAR_INVOCATION = {
    'add_tools': _add_tools,
    'add_outputs': _add_outputs,
    'remove_outputs': remove_outputs,
    'remove_tools': remove_tools,
    'add_params': add_params,
    'add_writes': add_writes,
}
_AUTRES = (
    'add_trigger_params',
    'remove_trigger_conditions',
    'add_write_values',
    'remove_write_values',
    'add_link_params',
    'set_tool_params',
    'add_tool_params',
    'remove_tool_columns',
)


def apply_changes(conn: sqlite3.Connection, raw: Any, only: str = '') -> None:
    """Applique les modifications de ``pipeline.yaml`` pas encore passées
    (``only`` : seulement celles de cette sorte).

    Raises:
        PipelineSeedError: Modification mal écrite (table ou colonne
            inconnue, objet visé par plusieurs lignes).
    """
    from serge.horloge import iso_utc

    for change in raw or []:
        if only and only not in change:
            continue
        ident = str(change['id'])
        if conn.execute(
            'SELECT 1 FROM pipeline_changes WHERE id=?', (ident,)
        ).fetchone():
            continue
        invocation = str(change.get('invocation') or '')
        kind = next(
            (k for k in (*_PAR_INVOCATION, *_AUTRES) if k in change), ''
        )
        if kind in _PAR_INVOCATION:
            result = _PAR_INVOCATION[kind](conn, invocation, change[kind])
        elif kind == 'add_trigger_params':
            result = _add_trigger_params(
                conn, str(change.get('trigger') or ''), change[kind]
            )
        elif kind == 'remove_trigger_conditions':
            result = remove_trigger_conditions(
                conn, str(change.get('trigger') or ''), change[kind]
            )
        elif kind in ('add_write_values', 'remove_write_values'):
            fonction = (
                _add_write_values
                if kind == 'add_write_values'
                else remove_write_values
            )
            result = fonction(
                conn, invocation, change.get('write'), change[kind]
            )
        elif kind == 'add_link_params':
            result = add_link_params(
                conn, str(change.get('link') or ''), change[kind]
            )
        elif kind in ('set_tool_params', 'add_tool_params'):
            fonction = (
                _set_tool_params
                if kind == 'set_tool_params'
                else add_tool_params
            )
            result = fonction(
                conn, invocation, str(change.get('tool') or ''), change[kind]
            )
        elif kind == 'remove_tool_columns':
            result = remove_tool_columns(
                conn, str(change.get('tool') or ''), change[kind]
            )
        else:
            table = str(change['table'])
            if table not in TABLES:
                raise PipelineSeedError(
                    f'changes.{ident} : table {table} interdite'
                )
            where, sets = change.get('where'), change.get('set')
            if not isinstance(where, Mapping) or not where:
                raise PipelineSeedError(f'changes.{ident} : where manquant')
            if not isinstance(sets, Mapping) or not sets:
                raise PipelineSeedError(f'changes.{ident} : set manquant')
            result = _result(conn, table, where, sets)
        conn.execute(
            'INSERT INTO pipeline_changes(id, applied_at, result)'
            ' VALUES(?,?,?)',
            (ident, iso_utc(), result),
        )
