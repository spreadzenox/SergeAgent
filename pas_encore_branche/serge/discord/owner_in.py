#!/usr/bin/env python3
"""Sens inverse owner → Serge (H §6) : parse + plan, pur et testable.

Mention/slash → H2 (injecté) → H3 (injecté) → plan : refus constitution
(dét, jamais bypassé), hint boutons (P3 : prose ne tranche jamais),
OWNER_ORDER (confirmé ou bypass logué + FYI post-hoc). v1 : pas de
réponse directe factuelle (un ticket OWNER_ORDER contextualisé fait foi).
"""

from __future__ import annotations

from typing import Any

from serge.points.checkers import fold

# §14.1a : interdits constitutionnels (FR/EN, stems pliés). Bypass impossible.
FORBIDDEN_14_1A = (
    'faux avis',
    'fake review',
    'fausses evaluations',
    'usurpation',
    'impersonat',
    'usurper',
    'fausse identite',
    'spam illegal',
    'spam illégal',
    'hameconnage',
    'phishing',
    'rancongiciel',
    'malware',
    'logiciel espion',
    'fraude',
    'carte volee',
    'blanchiment',
    'chantage',
    'menace de',
    'doxxing',
    'donnees volees',
    'contrefacon',
)
SLASH_CMDS = {'ask': 'ASK', 'order': 'ORDER', 'veto': 'VETO', 'info': 'INFO'}


def check_constitution(text: str) -> str:
    """Check dét §14.1a (après le juge, jamais bypassé).

    Args:
        text: Ordre/message owner.

    Returns:
        Le motif fautif ou ''.
    """
    folded = fold(text)
    for pattern in FORBIDDEN_14_1A:
        if fold(pattern) in folded:
            return pattern
    return ''


def parse_mention(text: str, bot_user_id: str) -> str | None:
    """Extrait le texte adressé au bot (<@id> / <@!id>).

    Args:
        text: Message brut.
        bot_user_id: Snowflake du bot.

    Returns:
        Texte sans mention, ou None si pas adressé.
    """
    if not bot_user_id:
        return None
    for form in (f'<@{bot_user_id}>', f'<@!{bot_user_id}>'):
        if form in text:
            return text.replace(form, '').strip()
    return None


def parse_slash(text: str) -> dict[str, Any] | None:
    """Parse /serge <ask|order|veto|info> corps [--force].

    Args:
        text: Message brut (déjà sans mention).

    Returns:
        Dict cmd/intent/body/force ou None si pas un slash.
    """
    stripped = text.strip()
    if not stripped.startswith('/serge'):
        return None
    rest = stripped[len('/serge') :].strip().split(None, 1)
    if not rest or rest[0] not in SLASH_CMDS:
        return None
    body = rest[1] if len(rest) > 1 else ''
    force = body.rstrip().endswith('--force')
    if force:
        body = body.rstrip()[: -len('--force')].strip()
    return {
        'cmd': rest[0],
        'intent': SLASH_CMDS[rest[0]],
        'body': body,
        'force': force,
    }


def detect_bypass(text: str) -> tuple[str, bool]:
    """Bypass owner : préfixe ! / suffixe --force / 'sans confirmation'.

    Args:
        text: Message brut.

    Returns:
        Tuple (texte nettoyé, bypass).
    """
    bypass = False
    clean = text.strip()
    lowered = clean.lower()
    if '--force' in lowered or 'sans confirmation' in lowered:
        bypass = True
        clean = clean.replace('--force', '').replace('--FORCE', '')
        for form in (
            'sans confirmation',
            'Sans confirmation',
            'SANS CONFIRMATION',
        ):
            clean = clean.replace(form, '')
        clean = ' '.join(clean.split())
    if clean.startswith('!'):
        bypass = True
        clean = clean[1:].strip()
    return clean, bypass


def plan_owner_message(
    text: str,
    *,
    thread_ticket_id: str = '',
    h2: dict[str, Any] | None = None,
    h3: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Planifie la réponse (H2/H3 pré-calculés, purs en entrée).

    Args:
        text: Message owner (mention retirée par l'appelant).
        thread_ticket_id: Ticket du fil courant ('' si hors fil).
        h2: Sortie classify_owner_intent (intent/confiance/cible).
        h3: Sortie judge_consequence (consequence/confiance) ou None.

    Returns:
        Plan {action, ...} : refuse | hint_buttons | create_owner_order.
    """
    hit = check_constitution(text)
    if hit:
        return {
            'action': 'refuse',
            'reason': f'constitution_14_1a:{hit}',
            'message': (
                'Refusé : contraire à la constitution (§14.1a). Même avec '
                'bypass, je ne peux pas exécuter ça.'
            ),
        }
    clean, bypass = detect_bypass(text)
    slash = parse_slash(clean)
    if slash is not None:
        intent = str(slash['intent'])
        cible = ''
        body = str(slash['body'])
        bypass = bypass or bool(slash['force'])
    else:
        intent = str((h2 or {}).get('intent') or 'OTHER')
        cible = str((h2 or {}).get('cible') or '')
        body = clean
    if thread_ticket_id and intent in {'APPROVE', 'REJECT'}:
        return {
            'action': 'hint_buttons',
            'ticket_id': thread_ticket_id,
            'message': (
                'Pour trancher, utilise les boutons de la carte ci-dessus '
                '👆 (je ne devine jamais une décision depuis du texte).'
            ),
        }
    consequence = str((h3 or {}).get('consequence') or 'OUI')
    needs_confirm = consequence == 'OUI' and not bypass
    return {
        'action': 'create_owner_order',
        'intent': intent,
        'cible': cible,
        'body': body,
        'bypass': bypass,
        'needs_confirm': needs_confirm,
        'thread_ticket_id': thread_ticket_id,
        'h3_criteres': (h3 or {}).get('criteres') or [],
        'fyi_posthoc': bypass,
    }
