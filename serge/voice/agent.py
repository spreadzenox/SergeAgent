#!/usr/bin/env python3
"""L'agent vocal, réglé en base comme une invocation.

Un appel est une tâche de l'invocation allumée de la file « Appels »
(``voice``), menée en direct par le pont téléphonique au lieu d'une file
de tâches. Tout ce qui la règle est en base, comme pour n'importe quelle
invocation (décision Q79) :

- son prompt, avec « Qui est Serge » ;
- ce qu'elle reçoit au décrochage (ses lectures d'office) : la fiche du
  contact, son fil, la fiche du business et la fiche produit, et, pour un
  appel sortant, l'envoi qui l'a lancé (le but de l'appel) ;
- ses outils appelables pendant l'appel : chercher un contact, noter une
  adresse ;
- ses réglages : fournisseurs, modèles et voix, durée maximale d'un appel ;
- ses écritures : à la fin, la transcription des deux voix entre dans le
  fil du contact (``inbound_events``), ce qui lance « Traiter une
  réponse » comme pour un e-mail.

Le transport de la voix (``serge/voice/s2s.py``) reste du code.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from serge.db.store import utcnow
from serge.funnels.contacts import normalise_value
from serge.interpreter.flow import fire_row_triggers, pass_links
from serge.interpreter.prompt import (
    Invocation,
    callable_tools,
    given_blocks,
    load_invocation,
    system_prompt,
)
from serge.interpreter.settings import load_settings
from serge.interpreter.tasks import (
    enqueue_task,
    finish_task,
    start_task,
    task_params,
)
from serge.interpreter.tools import run_tool, tool_capability
from serge.interpreter.writer import write_answer

# La file dont l'invocation allumée mène les appels.
VOICE_QUEUE = 'voice'
# Ce qu'un résultat d'outil rend au plus à l'agent vocal (caractères).
TOOL_OUTPUT_MAX = 4000


@dataclass
class Call:
    """Un appel en cours : sa tâche, ce qu'elle a reçu, ce qui s'est dit."""

    task_id: str
    inv: Invocation
    task: dict[str, str]
    links: dict[str, int | None] = field(default_factory=dict)
    lines: list[str] = field(default_factory=list)
    # Le contact trouvé pendant l'appel (un appelant inconnu, reconnu par
    # l'outil « Chercher un contact » quand il ne rend qu'une fiche).
    found: dict[str, str] = field(default_factory=dict)


def peer_from_uuid(raw: bytes) -> tuple[str, str]:
    """Le sens et le numéro d'un appel, lus dans l'UUID d'AudioSocket.

    Le plan d'appel d'Asterisk (``kit/asterisk.py``) écrit le sens (1 :
    entrant, 2 : sortant) puis les 15 derniers chiffres du numéro, complétés
    de zéros. Exemple : ``5e7e0000-0000-4000-2000-033612345678`` est un appel
    sortant vers ``+33612345678``. Un UUID d'une autre forme : ``('', '')``.
    """
    try:
        digits = uuid.UUID(bytes=raw).hex
    except ValueError:
        return '', ''
    if not digits.startswith('5e7e') or digits[16] not in '12':
        return '', ''
    number = digits[17:].lstrip('0')
    direction = 'inbound' if digits[16] == '1' else 'outbound'
    return direction, f'+{number}' if number else ''


def agent_invocation(conn: sqlite3.Connection) -> str:
    """L'invocation qui mène les appels, ou ``''`` s'il n'y en a pas.

    La file « Appels » coupée dans Mission Control : l'agent vocal se tait,
    seul le secours prend un message.
    """
    row = conn.execute(
        'SELECT i.id FROM invocations i JOIN queues q ON q.id=i.queue_id'
        " WHERE i.queue_id=? AND i.enabled=1 AND i.deleted_at=''"
        ' AND q.enabled=1 ORDER BY i.priority DESC, i.id LIMIT 1',
        (VOICE_QUEUE,),
    ).fetchone()
    return str(row[0]) if row else ''


def _contact(conn: sqlite3.Connection, phone: str) -> tuple[str, str]:
    """Le contact qui porte ce numéro (celui à qui Serge a écrit le plus
    récemment, s'il y en a plusieurs) et son business."""
    row = conn.execute(
        'SELECT c.id, c.venture_id FROM contact_addresses a'
        ' JOIN contacts c ON c.id=a.contact_id'
        " WHERE a.channel='phone' AND a.value_norm=?"
        ' ORDER BY (SELECT MAX(t.created_at) FROM touches t'
        ' WHERE t.contact_id=c.id) DESC, c.created_at DESC LIMIT 1',
        (normalise_value('phone', phone),),
    ).fetchone()
    return (str(row[0]), str(row[1])) if row else ('', '')


def start_call(
    conn: sqlite3.Connection,
    direction: str,
    phone: str,
    cdr_id: str,
    touch_id: str = '',
) -> Call | None:
    """La tâche d'un appel qui commence, ou ``None`` sans agent en base.

    Args:
        direction: ``inbound`` ou ``outbound``.
        phone: Le numéro de l'interlocuteur (E.164).
        cdr_id: Le numéro de l'appel dans le journal des appels.
        touch_id: L'envoi qui a lancé un appel sortant.
    """
    inv_id = agent_invocation(conn)
    if not inv_id:
        return None
    contact_id, venture_id = _contact(conn, phone)
    params = {
        'direction': direction,
        'phone': phone,
        'cdr_id': cdr_id,
        'touch_id': touch_id,
        'contact_id': contact_id,
        'venture_id': venture_id,
    }
    # Une tâche par branche de l'appel : le secours tour par tour, qui
    # reprend un appel dont la session vocale a lâché, a la sienne.
    task_id = enqueue_task(
        conn,
        inv_id,
        params,
        origin_ref=f'appel {cdr_id}',
        key=f'appel:{cdr_id}:{uuid.uuid4().hex[:8]}',
    )
    if task_id is None or not start_task(conn, task_id):
        return None
    conn.commit()
    return Call(
        task_id, load_invocation(conn, inv_id), task_params(conn, task_id)
    )


def instructions(conn: sqlite3.Connection, call: Call) -> str:
    """Le prompt de l'agent : le sien, puis ce qu'il reçoit au décrochage."""
    blocks = given_blocks(conn, call.inv, call.task_id, call.task)
    return '\n\n'.join(
        [system_prompt(conn, call.inv, []), *blocks[:1]]
    ).strip()


def tools(conn: sqlite3.Connection, call: Call) -> list[dict[str, Any]]:
    """Les outils appelables, sous la forme d'une session vocale."""
    schemas, call.links = callable_tools(conn, call.inv, call.task)
    out = []
    for schema in schemas:
        function = schema.get('function') or {}
        out.append(
            {
                'type': 'function',
                'name': str(function.get('name') or ''),
                'description': str(function.get('description') or ''),
                'parameters': function.get('parameters') or {},
            }
        )
    return out


def settings(conn: sqlite3.Connection, call: Call) -> dict[str, str]:
    """Les réglages de l'agent (fournisseurs, modèles, voix, durée)."""
    return load_settings(conn, call.inv.id)


def run_tool_call(
    conn: sqlite3.Connection, call: Call, name: str, arguments: str
) -> str:
    """Exécute un outil demandé pendant l'appel ; rend son résultat (JSON).

    Un appelant inconnu reconnu par « Chercher un contact » (une seule
    fiche trouvée) devient le contact de l'appel.
    """
    if not call.links:
        tools(conn, call)
    if name not in call.links:
        return json.dumps({'ok': False, 'code': 'outil_inconnu'})
    try:
        args = json.loads(arguments or '{}')
    except json.JSONDecodeError:
        return json.dumps({'ok': False, 'code': 'arguments_illisibles'})
    if not isinstance(args, dict):
        args = {}
    result = run_tool(
        conn, call.inv.id, call.links[name], name, args, call.task
    )
    rows = result.get('rows')
    if (
        not call.task.get('contact_id')
        and tool_capability(conn, name) == 'contact_search'
        and isinstance(rows, list)
        and len(rows) == 1
    ):
        call.found = {'contact_id': str(rows[0]['id'])}
    conn.commit()
    return json.dumps(result, ensure_ascii=False, default=str)[
        :TOOL_OUTPUT_MAX
    ]


def hear(call: Call, speaker: str, text: str) -> None:
    """Note une phrase de l'appel (``Serge`` ou ``Contact``)."""
    if text.strip():
        call.lines.append(f'{speaker} : {text.strip()}')


def finish_call(conn: sqlite3.Connection, call: Call) -> None:
    """Range l'appel : sa transcription entre dans le fil du contact.

    Les règles d'écriture de l'invocation rangent la réponse ; un appel
    sans un mot ne laisse rien dans le fil. Un appel d'un contact connu
    (par son numéro, ou reconnu pendant l'appel) lance la suite, comme un
    e-mail reçu.
    """
    contact = call.task.get('contact_id') or call.found.get('contact_id', '')
    venture = call.task.get('venture_id', '')
    if contact and not venture:
        row = conn.execute(
            'SELECT venture_id FROM contacts WHERE id=?', (contact,)
        ).fetchone()
        venture = str(row[0]) if row else ''
        # L'appelant reconnu pendant l'appel : la tâche garde son business,
        # et ses minutes comptent dans ce que ce business a dépensé.
        if venture:
            conn.execute(
                'INSERT OR REPLACE INTO task_params(task_id, name, value)'
                " VALUES(?, 'venture_id', ?)",
                (call.task_id, venture),
            )
    if call.lines:
        answer = {
            'transcript': '\n'.join(call.lines),
            'contact_id': contact,
            'venture_id': venture,
            'status': 'attached' if contact else 'unattached',
        }
        written = write_answer(
            conn, call.inv.id, call.task_id, call.task, answer
        )
        fire_row_triggers(conn, written)
        pass_links(conn, call.inv.id, call.task_id, written, answer)
    finish_task(conn, call.task_id)
    conn.commit()


def call_seconds(conn: sqlite3.Connection, venture_id: str) -> float:
    """La durée des appels d'un business, en secondes : ses tâches d'appel
    terminées, du décroché à la fin. Un appel coupé par un redémarrage du
    pont ne compte pas : sa fin n'est pas celle de l'appel."""
    total = 0.0
    for started, finished in conn.execute(
        'SELECT t.started_at, t.finished_at FROM tasks t JOIN task_params p'
        " ON p.task_id=t.id AND p.name='venture_id'"
        " WHERE t.queue_id=? AND p.value=? AND t.status='done'"
        " AND t.started_at<>'' AND t.finished_at<>''",
        (VOICE_QUEUE, venture_id),
    ).fetchall():
        try:
            debut = datetime.fromisoformat(str(started))
            fin = datetime.fromisoformat(str(finished))
        except ValueError:
            continue
        total += max(0.0, (fin - debut).total_seconds())
    return total


def close_interrupted_calls(conn: sqlite3.Connection) -> int:
    """Les appels restés « en cours » quand le pont s'est arrêté : en échec.

    Un appel ne se reprend pas : la ligne est coupée. Appelé au démarrage
    du pont téléphonique.
    """
    cursor = conn.execute(
        "UPDATE tasks SET status='failed', finished_at=?,"
        " last_error='appel interrompu : le pont téléphonique a redémarré'"
        " WHERE queue_id=? AND status='running'",
        (utcnow(), VOICE_QUEUE),
    )
    conn.commit()
    return cursor.rowcount
