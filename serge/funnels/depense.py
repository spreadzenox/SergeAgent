#!/usr/bin/env python3
"""Ce qu'un business a dépensé, et ses points par euro (grille de points).

« Dépensé » compte (décision Q84) :

- le coût réel des appels au modèle faits pour ses tâches (celles dont le
  paramètre ``venture_id`` est le business), converti en euros au taux de
  la page Policy (``budget.eur_per_usd``) ; les jetons d'un appel dont le
  coût n'est pas connu sont comptés à part, jamais estimés ;
- ses minutes d'appel, au prix réglé sur la page Policy
  (``budget.call_minute_eur``).

Les achats (publicité, domaines) s'ajouteront quand ils existeront.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.llm.runtime import VERDICTS_COMPTES
from serge.policy_store import setting_value


def depense_business(
    conn: sqlite3.Connection, venture_id: str
) -> dict[str, Any]:
    """Ce qu'un business a dépensé, en euros, avec le détail.

    Returns:
        ``{modeles_eur, jetons_sans_cout, minutes, appels_eur, total_eur}``.
    """
    from serge.voice.agent import call_seconds

    eur_per_usd = float(setting_value(conn, 'budget.eur_per_usd') or 0)
    prix_minute = float(setting_value(conn, 'budget.call_minute_eur') or 0)
    row = conn.execute(
        'SELECT COALESCE(SUM(u.cost_usd), 0), COALESCE(SUM(CASE WHEN'
        ' u.cost_usd IS NULL THEN u.tokens_in + u.tokens_out ELSE 0 END), 0)'
        ' FROM llm_usage u JOIN task_params p ON p.task_id=u.task_id'
        " AND p.name='venture_id'"
        f' WHERE p.value=? AND u.verdict IN {VERDICTS_COMPTES}',
        (venture_id,),
    ).fetchone()
    modeles = float(row[0]) * eur_per_usd
    minutes = call_seconds(conn, venture_id) / 60
    appels = minutes * prix_minute
    return {
        'modeles_eur': round(modeles, 4),
        'jetons_sans_cout': int(row[1]),
        'minutes': round(minutes, 1),
        'appels_eur': round(appels, 4),
        'total_eur': round(modeles + appels, 4),
    }


def points_par_euro(points: float, depense_eur: float) -> float | None:
    """Les points par euro dépensé, ou ``None`` si rien n'a été dépensé."""
    if depense_eur <= 0:
        return None
    return round(points / depense_eur, 1)


def texte_euros(montant: float) -> str:
    """``3.2`` → ``3,20``."""
    return f'{montant:.2f}'.replace('.', ',')
