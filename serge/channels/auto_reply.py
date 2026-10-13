#!/usr/bin/env python3
"""Reconnaître une réponse automatique à ses en-têtes (lot 10 bis, Q93).

Une réponse d'absence (« je suis absent jusqu'au 20 ») ou un accusé de
réception (« votre demande n° 1234 est bien reçue ») porte en général un
en-tête qui le dit : ``Auto-Submitted`` (RFC 3834, toute valeur autre que
``no``), ``X-Autoreply``, ``X-Autorespond``, ou ``Precedence``
(``auto_reply``, ``bulk``, ``junk``, ``list``). Le canal le marque : la
relève le range dans le fil sans le faire traiter, et Serge ne répond pas,
sans même appeler le modèle. Une réponse automatique sans ces en-têtes est
reconnue par « Traiter une réponse » (réaction « absence »).
"""

from __future__ import annotations

from collections.abc import Mapping

# La sorte d'un message reçu qui est une réponse automatique
# (``inbound_events.native_type``).
AUTO_REPLY = 'auto_reply'
_PRECEDENCE = frozenset({'auto_reply', 'bulk', 'junk', 'list'})


def is_auto_reply(headers: Mapping[str, str]) -> bool:
    """Vrai si les en-têtes disent une réponse automatique.

    ``headers`` : les en-têtes du message, noms en minuscules.
    """
    submitted = str(headers.get('auto-submitted', '')).strip().lower()
    if submitted and submitted != 'no':
        return True
    if headers.get('x-autoreply') or headers.get('x-autorespond'):
        return True
    precedence = str(headers.get('precedence', '')).strip().lower()
    return precedence in _PRECEDENCE
