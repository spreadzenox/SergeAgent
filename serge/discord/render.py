#!/usr/bin/env python3
"""Rendu tickets → carte Discord FR + boutons, envoyée en message privé.

Déterministe : embed + boutons depuis le type du ticket en base (boutons,
couleur, emoji). IDs backend strippés du visible (custom_id uniquement).
Un ticket tranché garde sa carte, boutons morts, avec qui l'a tranché.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from serge.text_ids import strip_ids
from serge.tickets.shared import champs_carte

BUTTONS: dict[str, dict[str, Any]] = {
    'approuver': {'label': 'Approuver', 'style': 3, 'emoji': '✅'},
    'approuver_version': {'label': 'Approuver', 'style': 3, 'emoji': '✅'},
    'rejeter': {'label': 'Rejeter', 'style': 4, 'emoji': '❌'},
    'discuter': {'label': 'Discuter', 'style': 2, 'emoji': '💬'},
    'discuter_fil': {'label': 'Discuter', 'style': 2, 'emoji': '🧵'},
    'editer': {'label': 'Éditer', 'style': 2, 'emoji': '✏️'},
    'cest_fait': {'label': "C'est fait", 'style': 3, 'emoji': '✅'},
    'abandonner': {'label': 'Abandonner', 'style': 4, 'emoji': '❌'},
    'tout_approuver': {'label': 'Tout approuver', 'style': 3, 'emoji': '✅'},
    'confirmer': {'label': 'Confirmer', 'style': 3, 'emoji': '✅'},
    'annuler': {'label': 'Annuler', 'style': 2, 'emoji': '❌'},
    'ouvrir': {'label': 'Ouvrir', 'style': 3, 'emoji': '🔓'},
    'refuser': {'label': 'Refuser', 'style': 4, 'emoji': '❌'},
    'accuse_reception': {'label': 'Bien reçu', 'style': 2, 'emoji': '👀'},
    'reponse_libre': {'label': 'Réponse libre', 'style': 2, 'emoji': '✍️'},
    'envoyer_brouillon': {
        'label': 'Envoyer le brouillon',
        'style': 3,
        'emoji': '✅',
    },
    'ma_reponse': {'label': 'Ma réponse', 'style': 1, 'emoji': '✍️'},
    'reecrire': {'label': 'Réécrire', 'style': 2, 'emoji': '🔁'},
    'ne_rien_envoyer': {
        'label': 'Ne rien envoyer',
        'style': 4,
        'emoji': '🚫',
    },
    'passer': {'label': 'Passer à la suite', 'style': 3, 'emoji': '▶️'},
    'ne_pas_passer': {'label': 'Ne pas passer', 'style': 4, 'emoji': '⏹️'},
    'garder': {'label': 'Garder', 'style': 3, 'emoji': '✅'},
    'modifier': {'label': 'Modifier', 'style': 2, 'emoji': '✏️'},
    'jeter': {'label': 'Jeter', 'style': 4, 'emoji': '🗑️'},
}
TERMINAL = frozenset(
    {
        'APPROVED',
        'REJECTED',
        'EDITED',
        'EXECUTED',
        'CLOSED',
        'EXPIRED',
        'CANCELLED',
    }
)
MAX_ITEM_ROWS = 4


def remaining_fr(expiry_at: str, now_iso: str) -> str:
    """Compte à rebours FR (défaut : 'sans expiry').

    Args:
        expiry_at: ISO d'expiry ('' = jamais).
        now_iso: Maintenant ISO.

    Returns:
        'dans 12 min' | 'dans 26 h' | 'dans 3 j' | 'dépassée' | 'sans expiry'.
    """
    if not expiry_at:
        return 'sans expiry'
    try:
        delta = datetime.fromisoformat(expiry_at) - datetime.fromisoformat(
            now_iso
        )
    except ValueError:
        return 'sans expiry'
    seconds = int(delta.total_seconds())
    if seconds <= 0:
        return 'dépassée'
    if seconds < 3600:
        return f'dans {max(1, seconds // 60)} min'
    if seconds < 86400:
        return f'dans {seconds // 3600} h'
    return f'dans {seconds // 86400} j'


def _button(
    ticket_id: str, action: str, disabled: bool, item_id: str = ''
) -> dict[str, Any]:
    spec = BUTTONS.get(action, {'label': action, 'style': 2, 'emoji': ''})
    custom_id = f't:{ticket_id}:{action}'
    if item_id:
        custom_id += f':{item_id}'
    button: dict[str, Any] = {
        'type': 2,
        'label': spec['label'][:80],
        'style': spec['style'],
        'custom_id': custom_id[:100],
        'disabled': disabled,
    }
    if spec.get('emoji'):
        button['emoji'] = {'name': spec['emoji']}
    return button


def _qcm_row(ticket_id: str, options: list[str], disabled: bool) -> dict:
    choices = [
        {'label': str(item)[:100], 'value': str(item)[:100]}
        for item in options[:24]
    ]
    choices.append(
        {'label': 'Autre (écrire ma réponse)', 'value': '__autre__'}
    )
    return {
        'type': 1,
        'components': [
            {
                'type': 3,
                'custom_id': f't:{ticket_id}:choix_qcm',
                'placeholder': 'Choisir…',
                'min_values': 1,
                'max_values': 1,
                'disabled': disabled,
                'options': choices,
            }
        ],
    }


# Ce qu'une carte Discord montre au plus : 1 024 caractères par champ, et
# une marge sous les 6 000 de tout le message.
CHAMP_MAX = 1024
CARTE_MAX = 5000


def _coupe(texte: str, place: int) -> str:
    """Un texte trop long garde sa fin (les derniers messages d'un fil)."""
    return texte if len(texte) <= place else '…' + texte[-(place - 1) :]


def _fields(
    ticket: Mapping[str, Any], spec: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Un champ par valeur du ticket, dans l'ordre de son type ; puis, s'il
    est tranché, qui l'a tranché et comment (la même carte chez tous les
    administrateurs, décision Q85)."""
    reste = CARTE_MAX
    fields = []
    for key, value in champs_carte(ticket, spec):
        place = min(CHAMP_MAX, reste)
        if place < 20:
            break
        texte = _coupe(str(value) or '—', place)
        reste -= len(texte)
        fields.append({'name': str(key)[:256], 'value': texte})
    if ticket.get('tranche'):
        fields.append(
            {'name': 'Tranché', 'value': str(ticket['tranche'])[:CHAMP_MAX]}
        )
    return fields


def render_card(
    ticket: Mapping[str, Any],
    spec: Mapping[str, Any],
    *,
    now_iso: str = '',
) -> dict[str, Any]:
    """Carte de décision (embed + boutons/select).

    Args:
        ticket: Ticket (id, type, title, state, payload, expiry_at,
            default_action, items?, tranche? : qui l'a tranché et comment).
        spec: Type du ticket en base (buttons, render...).
        now_iso: Maintenant ISO (compte à rebours).

    Returns:
        Payload message Discord {embeds, components} (IDs strippés).
    """
    ticket_id = str(ticket.get('id') or '')
    render = spec.get('render') or {}
    emoji = str(render.get('emoji') or '🎫')
    color = render.get('color')
    color = color if isinstance(color, int) else 5793266
    title = strip_ids(f'{emoji} {ticket.get("type")} — {ticket.get("title")}')[
        :256
    ]
    remaining = remaining_fr(str(ticket.get('expiry_at') or ''), now_iso)
    default = str(ticket.get('default_action') or '')
    footer = (
        f'Expire {remaining} → défaut : {default}'
        if default
        else (
            f'Expire {remaining}'
            if remaining != 'sans expiry'
            else 'Sans expiry'
        )
    )
    embed: dict[str, Any] = {
        'title': title,
        'description': f'{ticket.get("type")} • {ticket.get("state")}',
        'color': color,
        'fields': [
            {
                'name': field['name'],
                'value': strip_ids(str(field['value'])),
                'inline': False,
            }
            for field in _fields(ticket, spec)
        ],
        'footer': {'text': strip_ids(footer)[:2048]},
    }
    if ticket.get('expiry_at'):
        embed['timestamp'] = str(ticket.get('expiry_at'))
    dead = str(ticket.get('state') or '') in TERMINAL
    components: list[dict[str, Any]] = []
    buttons = [
        name
        for name in (spec.get('buttons') or [])
        if name in BUTTONS or name == 'choix_qcm'
    ]
    if ticket.get('type') == 'MEMORY':
        items = ticket.get('items') or []
        rows: list[dict[str, Any]] = []
        for rank, item in enumerate(items[:MAX_ITEM_ROWS], start=1):
            item_id = str(item.get('id') or '')
            embed['fields'].append(
                {
                    'name': f'Leçon {rank} [{item.get("state") or "open"}]',
                    'value': strip_ids(str(item.get('label') or ''))[:1024],
                    'inline': False,
                }
            )
            rows.append(
                {
                    'type': 1,
                    'components': [
                        _button(ticket_id, 'garder', dead, item_id),
                        _button(ticket_id, 'modifier', dead, item_id),
                        _button(ticket_id, 'jeter', dead, item_id),
                    ],
                }
            )
        leftover = len(items) - len(rows)
        rows.append(
            {
                'type': 1,
                'components': [
                    _button(ticket_id, name, dead) for name in buttons
                ],
            }
        )
        components = rows[:5]
        if leftover > 0:
            embed['fields'].append(
                {
                    'name': 'Suite',
                    'value': f'+{leftover} leçon(s) sur Mission Control',
                    'inline': False,
                }
            )
    else:
        row: list[dict[str, Any]] = []
        for name in buttons:
            if name == 'choix_qcm':
                options = []
                payload = ticket.get('payload')
                if isinstance(payload, dict):
                    options = payload.get('options_qcm') or []
                components.append(
                    _qcm_row(ticket_id, [str(item) for item in options], dead)
                )
                continue
            row.append(_button(ticket_id, name, dead))
        if row:
            components.append({'type': 1, 'components': row[:5]})
    return {'embeds': [embed], 'components': components[:5]}
