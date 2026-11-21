#!/usr/bin/env python3
"""Mission Control : la réponse d'une tâche LLM, écrite pour être lue.

Le modèle rend un objet JSON (``tasks.answer_json``). La fiche de la tâche
ne le montre pas brut : chaque champ a sa ligne, un texte long se lit
comme un texte, et une liste (les discussions trouvées par une fouille)
donne un cadre par liste, un bloc par élément. Le JSON exact reste dans la
« Preuve » de la fiche.

Exemple : ``{"resume": "Deux avis.", "trouvailles": [{"url": "https://…",
"titre": "Un fil"}]}`` donne un cadre « Ce que le modèle a rendu » avec le
champ « Resume », puis un cadre « Trouvailles (1) » avec un bloc
« Url », « Titre ».
"""

from __future__ import annotations

import json
from typing import Any

TITRE = 'Ce que le modèle a rendu'


def _nom(cle: Any) -> str:
    """Le nom d'un champ, sans ses tirets bas : ``compte_rendu`` devient
    « Compte rendu »."""
    return str(cle).replace('_', ' ').strip().capitalize()


def _texte(valeur: Any) -> str:
    if valeur is None or valeur == '':
        return '—'
    if isinstance(valeur, bool):
        return 'oui' if valeur else 'non'
    if isinstance(valeur, (dict, list)):
        return json.dumps(valeur, ensure_ascii=False)
    return str(valeur)


def _champs(objet: dict[str, Any]) -> list[dict[str, str]]:
    return [{'k': _nom(k), 'v': _texte(v)} for k, v in objet.items()]


def cadres_reponse(answer_json: str) -> list[dict[str, Any]]:
    """Les cadres de la réponse d'une tâche ; ``[]`` sans réponse."""
    if not answer_json:
        return []
    try:
        reponse = json.loads(answer_json)
    except ValueError:
        return [{'titre': TITRE, 'pre': str(answer_json)}]
    if not isinstance(reponse, dict):
        return [{'titre': TITRE, 'pre': _texte(reponse)}]
    simples: dict[str, Any] = {}
    suite: list[dict[str, Any]] = []
    for cle, valeur in reponse.items():
        if isinstance(valeur, dict) and valeur:
            suite.append(
                {'titre': f'{TITRE} : {_nom(cle)}', 'champs': _champs(valeur)}
            )
        elif isinstance(valeur, list) and valeur:
            if all(isinstance(element, dict) for element in valeur):
                suite.append(
                    {
                        'titre': f'{_nom(cle)} ({len(valeur)})',
                        'groupes': [_champs(element) for element in valeur],
                    }
                )
            else:
                simples[cle] = '\n'.join(_texte(e) for e in valeur)
        else:
            simples[cle] = valeur
    cadres = [{'titre': TITRE, 'champs': _champs(simples)}] if simples else []
    return cadres + suite
