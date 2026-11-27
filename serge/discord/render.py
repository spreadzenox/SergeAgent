#!/usr/bin/env python3
"""Rendu tickets → carte Discord FR + boutons, dans le fil du ticket.

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
    'rejeter': {'label': 'Rejeter', 'style': 4, 'emoji': '❌'},
    'discuter': {'label': 'Discuter', 'style': 2, 'emoji': '💬'},
    'discuter_fil': {'label': 'Discuter', 'style': 2, 'emoji': '🧵'},
    'editer': {'label': 'Éditer', 'style': 2, 'emoji': '✏️'},
    'cest_fait': {'label': "C'est fait", 'style': 3, 'emoji': '✅'},
    'abandonner': {'label': 'Abandonner', 'style': 4, 'emoji': '❌'},
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
    'valider': {'label': 'Valider', 'style': 3, 'emoji': '✅'},
    'a_corriger': {'label': 'À corriger', 'style': 1, 'emoji': '✏️'},
    # Depuis un ticket de test : revenir à la conception, pas seulement à
    # la construction (décision Q116).
    'revoir_plan': {'label': 'Revoir le plan', 'style': 1, 'emoji': '🧭'},
    'choisir_autre': {
        'label': 'Choisir un autre',
        'style': 1,
        'emoji': '🔀',
    },
    'aucun': {'label': 'Aucun', 'style': 4, 'emoji': '🚫'},
    'arreter_business': {
        'label': 'Arrêter le business',
        'style': 4,
        'emoji': '🛑',
    },
    'ne_pas_passer': {'label': 'Ne pas passer', 'style': 4, 'emoji': '⏹️'},
    'faire_sans': {'label': 'Faire sans', 'style': 2, 'emoji': '⏭️'},
    'pret': {'label': 'Je suis prêt', 'style': 3, 'emoji': '🙋'},
    # Ajouté de lui-même quand un champ de la carte est coupé : poste tout
    # le ticket dans son fil (``serge/discord/interactions.py``).
    'voir_en_entier': {'label': 'Voir en entier', 'style': 2, 'emoji': '📄'},
}
TOUT = 'voir_en_entier'
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


def _button(ticket_id: str, action: str, disabled: bool) -> dict[str, Any]:
    spec = BUTTONS.get(action, {'label': action, 'style': 2, 'emoji': ''})
    button: dict[str, Any] = {
        'type': 2,
        'label': spec['label'][:80],
        'style': spec['style'],
        'custom_id': f't:{ticket_id}:{action}'[:100],
        'disabled': disabled,
    }
    if spec.get('emoji'):
        button['emoji'] = {'name': spec['emoji']}
    return button


# Ce qu'une carte Discord montre au plus : 1 024 caractères par champ, et
# une marge sous les 6 000 de tout le message. Au-delà, la carte montre le
# début, et « Voir en entier » poste tout le texte dans le fil.
CHAMP_MAX = 1024
CARTE_MAX = 5000
SUITE = '… (la suite : « Voir en entier »)'


def _coupe(texte: str, place: int, fin: bool) -> str:
    """Un texte trop long garde son début ; ``fin`` : sa fin (les derniers
    messages d'un fil, réglé sur le bloc du type de ticket)."""
    if len(texte) <= place:
        return texte
    if fin:
        return '…' + texte[-(place - 1) :]
    return texte[: place - len(SUITE)] + SUITE


def _fins(spec: Mapping[str, Any]) -> set[str]:
    """Les champs dont la carte garde la fin (``fin: true`` sur un bloc)."""
    return {
        str(bloc.get('label') or '')
        for bloc in spec.get('contenu') or []
        if isinstance(bloc, dict) and bloc.get('fin')
    }


def _fields(
    ticket: Mapping[str, Any], spec: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], bool]:
    """Un champ par valeur du ticket, dans l'ordre de son type ; puis, s'il
    est tranché, qui l'a tranché et comment (la même carte chez tous les
    administrateurs, décision Q85). Vrai en second si un champ est coupé."""
    reste = CARTE_MAX
    fields = []
    fins = _fins(spec)
    coupe = False
    for key, value in champs_carte(ticket, spec):
        place = min(CHAMP_MAX, reste)
        if place < 60:
            coupe = True
            break
        brut = str(value) or '—'
        texte = _coupe(brut, place, str(key) in fins)
        coupe = coupe or texte != brut
        reste -= len(texte)
        fields.append({'name': str(key)[:256], 'value': texte})
    if ticket.get('tranche'):
        fields.append(
            {'name': 'Tranché', 'value': str(ticket['tranche'])[:CHAMP_MAX]}
        )
    return fields, coupe


def texte_entier(
    ticket: Mapping[str, Any], spec: Mapping[str, Any], taille: int = 1900
) -> list[str]:
    """Tout le ticket, champ par champ, en messages Discord (2 000
    caractères au plus chacun), coupés entre deux lignes, sinon entre deux
    mots."""
    messages: list[str] = []
    for key, value in champs_carte(ticket, spec):
        reste = f'**{key}**\n{strip_ids(str(value) or "—")}'
        while reste:
            if len(reste) <= taille:
                messages.append(reste)
                break
            # Entre deux lignes, sinon entre deux mots.
            coupure = reste.rfind('\n', 0, taille)
            if coupure <= taille // 2:
                coupure = reste.rfind(' ', 0, taille)
            coupure = coupure if coupure > taille // 2 else taille
            messages.append(reste[:coupure])
            reste = reste[coupure:].lstrip('\n ')
    return messages


def render_card(
    ticket: Mapping[str, Any],
    spec: Mapping[str, Any],
    *,
    now_iso: str = '',
) -> dict[str, Any]:
    """Carte de décision (embed + boutons).

    Args:
        ticket: Ticket (id, type, title, state, payload, expiry_at,
            default_action, tranche? : qui l'a tranché et comment).
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
    champs, coupe = _fields(ticket, spec)
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
            for field in champs
        ],
        'footer': {'text': strip_ids(footer)[:2048]},
    }
    if ticket.get('expiry_at'):
        embed['timestamp'] = str(ticket.get('expiry_at'))
    dead = str(ticket.get('state') or '') in TERMINAL
    components: list[dict[str, Any]] = []
    row = [
        _button(ticket_id, name, dead)
        for name in (spec.get('buttons') or [])
        if name in BUTTONS
    ]
    if coupe:
        # Lire tout le ticket reste possible une fois tranché.
        row.append(_button(ticket_id, TOUT, False))
    for debut in range(0, len(row), 5):
        components.append({'type': 1, 'components': row[debut : debut + 5]})
    return {'embeds': [embed], 'components': components[:5]}
