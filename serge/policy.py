#!/usr/bin/env python3
"""Les réglages généraux : lire le fichier de départ, vérifier une valeur.

``config/policy.yaml`` décrit chaque réglage (valeur de départ, titre,
aide, sorte, bornes, choix) et les relations entre réglages. Il ne sert
qu'à remplir la base (``serge/policy_store.py``) : en marche, les réglages
sont lus en base, et changés dans Mission Control (décision Q68).

Une valeur est vérifiée selon la sorte du réglage. Exemple : un réglage
``curseur`` de 0 à 200 refuse 2,5 (pas un entier) et 250 (trop grand).
"""

from __future__ import annotations

import math
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

SCHEMA_VERSION = 2

# Les sortes de réglage : un nombre (entier ou non), un choix, une liste.
NUMBER_KINDS = frozenset({'eur', 'pct', 'nombre'})
INTEGER_KINDS = frozenset({'curseur', 'heure'})
CHOICE_KINDS = frozenset({'canaux', 'jours'})
# La page de Mission Control d'une famille de réglages.
PAGES = frozenset({'policy', 'pipeline'})
KINDS = (
    NUMBER_KINDS
    | INTEGER_KINDS
    | CHOICE_KINDS
    | {
        'liste',
        'fenetres',
        'nombres',
    }
)


class PolicyError(ValueError):
    """Config invalide ou illisible : le boot doit refuser."""


@dataclass(frozen=True)
class Setting:
    """Un réglage tel que le décrit ``policy.yaml`` ou la base."""

    id: str
    section_id: str
    position: int
    title: str
    help: str
    kind: str
    value: Any
    min: float | None = None
    max: float | None = None
    step: float | None = None
    choices: tuple = ()


@dataclass(frozen=True)
class Relation:
    """« ``lower`` ≤ ``upper`` » (« < » si ``strict``)."""

    lower: str
    upper: str
    strict: bool


def config_dir() -> Path:
    """Dossier config (override SERGE_CONFIG_DIR pour les tests).

    Returns:
        Chemin du dossier contenant policy.yaml et registres.
    """
    override = os.environ.get('SERGE_CONFIG_DIR', '').strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[1] / 'config'


def is_test_env() -> bool:
    """True quand SERGE_ENV=test (policy test + allowlist, jamais prod).

    Returns:
        True si l'environnement de test live-prudent est actif.
    """
    return os.environ.get('SERGE_ENV', '').strip().lower() == 'test'


def read_yaml_file(path: Path) -> dict[str, Any]:
    """Lit un YAML de config (mapping racine exigé).

    Args:
        path: Fichier à lire.

    Returns:
        Le mapping racine.

    Raises:
        PolicyError: Si illisible, invalide, ou racine non-mapping.
    """
    try:
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
    except OSError as exc:
        raise PolicyError(f'config illisible : {path}') from exc
    except yaml.YAMLError as exc:
        raise PolicyError(f'config YAML invalide : {path}') from exc
    if not isinstance(data, dict):
        raise PolicyError(f'config racine invalide : {path}')
    return data


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None


def _bounded(number: float, setting: Setting) -> str:
    if setting.min is not None and number < setting.min:
        return f'au moins {setting.min:g}'
    if setting.max is not None and number > setting.max:
        return f'au plus {setting.max:g}'
    return ''


def choice_ids(setting: Setting) -> list[str]:
    """Les valeurs permises : ``FR``, ou ``voice`` pour ``[voice, Voix]``."""
    return [
        str(c[0]) if isinstance(c, list | tuple) else str(c)
        for c in setting.choices
    ]


def _check_windows(value: Any) -> str:
    if not isinstance(value, list):
        return 'une liste de plages attendue'
    for plage in value:
        numbers = (
            [_number(x) for x in plage] if isinstance(plage, list) else []
        )
        if len(numbers) != 4 or any(n is None or n != int(n) for n in numbers):
            return 'une plage s’écrit [heure, minute, heure, minute]'
        h1, m1, h2, m2 = (int(n or 0) for n in numbers)
        if not (0 <= h1 <= 23 and 0 <= h2 <= 23):
            return 'une heure va de 0 à 23'
        if not (0 <= m1 <= 59 and 0 <= m2 <= 59):
            return 'une minute va de 0 à 59'
    return ''


def _check_numbers(setting: Setting, value: Any) -> str:
    if not isinstance(value, list) or not value:
        return 'une liste de nombres attendue'
    for item in value:
        number = _number(item)
        if number is None or number != int(number):
            return 'des nombres entiers attendus'
        if problem := _bounded(number, setting):
            return problem
    return ''


def check_value(setting: Setting, value: Any) -> str:
    """Ce qui ne va pas dans ``value`` pour ce réglage, ou ``''``.

    Exemple : ``check_value(<curseur de 0 à 200>, 250)`` rend
    ``'au plus 200'``.
    """
    kind = setting.kind
    if kind in NUMBER_KINDS or kind in INTEGER_KINDS:
        number = _number(value)
        if number is None:
            return 'un nombre attendu'
        if kind in INTEGER_KINDS and number != int(number):
            return 'un nombre entier attendu'
        return _bounded(number, setting)
    permis = choice_ids(setting)
    if kind == 'liste':
        ok = isinstance(value, str) and value in permis
        return '' if ok else f'un choix parmi {", ".join(permis)}'
    if kind in CHOICE_KINDS:
        ok = isinstance(value, list) and all(
            isinstance(v, str) and v in permis for v in value
        )
        return '' if ok else f'des choix parmi {", ".join(permis)}'
    if kind == 'fenetres':
        return _check_windows(value)
    if kind == 'nombres':
        return _check_numbers(setting, value)
    return f'sorte de réglage inconnue : {kind}'


def check_relations(
    values: Mapping[str, Any], relations: Iterable[Relation]
) -> str:
    """La première relation que ``values`` ne respecte pas, en clair, ou ``''``.

    Exemple : « standing.capital_min doit rester ≤ standing.capital_max ».
    """
    for rel in relations:
        low, high = (
            _number(values.get(rel.lower)),
            _number(values.get(rel.upper)),
        )
        if low is None or high is None:
            continue
        if low > high or (rel.strict and low == high):
            sign = '<' if rel.strict else '≤'
            return f'{rel.lower} doit rester {sign} {rel.upper}'
    return ''


def nest(flat: Mapping[str, Any]) -> dict[str, Any]:
    """``{'budget.monthly_eur': 50}`` → ``{'budget': {'monthly_eur': 50}}``."""
    out: dict[str, Any] = {}
    for ident, value in flat.items():
        *parents, last = ident.split('.')
        node = out
        for part in parents:
            node = node.setdefault(part, {})
        node[last] = value
    return out


def _flat(node: Mapping[str, Any], prefix: str = '') -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in node.items():
        if isinstance(value, Mapping):
            out.update(_flat(value, f'{prefix}{key}.'))
        else:
            out[f'{prefix}{key}'] = value
    return out


def _settings(sections: list) -> list[Setting]:
    out = []
    for section in sections:
        for position, raw in enumerate(section.get('settings') or []):
            out.append(
                Setting(
                    id=f'{section["id"]}.{raw["id"]}',
                    section_id=str(section['id']),
                    position=position,
                    title=str(raw['title']),
                    help=str(raw.get('help') or ''),
                    kind=str(raw['kind']),
                    value=raw['value'],
                    min=raw.get('min'),
                    max=raw.get('max'),
                    step=raw.get('step'),
                    choices=tuple(raw.get('choices') or ()),
                )
            )
    return out


def load_policy_seed(directory: Path | None = None) -> dict[str, Any]:
    """Lit ``policy.yaml`` (avec ``policy.test.yaml`` en test) et le vérifie.

    Returns:
        ``{sections, settings, relations, renamed, changes, deleted}`` :
        ``settings`` est une liste de ``Setting``, ``relations`` une liste
        de ``Relation``, ``renamed`` une liste de ``(ancien, nouveau)``.

    Raises:
        PolicyError: Fichier illisible, réglage mal décrit, valeur de
            départ hors de ses bornes, relation non respectée.
    """
    root = directory or config_dir()
    data = read_yaml_file(root / 'policy.yaml')
    if data.get('schema_version') != SCHEMA_VERSION:
        raise PolicyError(
            f'policy.schema_version doit valoir {SCHEMA_VERSION}'
        )
    sections = list(data.get('sections') or [])
    try:
        settings = _settings(sections)
        relations = [
            Relation(str(low), str(high), op == '<')
            for low, op, high in data.get('relations') or []
        ]
        renamed = [
            (str(old), str(new)) for old, new in data.get('renamed') or []
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise PolicyError(f'policy.yaml mal formé : {exc}') from exc
    if is_test_env():
        overlay = read_yaml_file(root / 'policy.test.yaml')
        overlay.pop('extends', None)
        overlay.pop('schema_version', None)
        values = _flat(overlay)
        settings = [
            replace(s, value=values[s.id]) if s.id in values else s
            for s in settings
        ]
    for section in sections:
        if section.get('page', 'policy') not in PAGES:
            raise PolicyError(
                f'policy.{section["id"]} : page {section["page"]}'
            )
    for setting in settings:
        if setting.kind not in KINDS:
            raise PolicyError(f'policy.{setting.id} : sorte {setting.kind}')
        if problem := check_value(setting, setting.value):
            raise PolicyError(f'policy.{setting.id} : {problem}')
    problem = check_relations({s.id: s.value for s in settings}, relations)
    if problem:
        raise PolicyError(f'policy : {problem}')
    return {
        'sections': sections,
        'settings': settings,
        'relations': relations,
        'renamed': renamed,
        'changes': data.get('changes') or [],
        'deleted': [str(i) for i in data.get('deleted') or []],
    }


def load_policy(directory: Path | None = None) -> dict[str, Any]:
    """Les valeurs de départ de ``policy.yaml``, rangées par section.

    Exemple : ``load_policy()['budget']['monthly_eur']`` vaut 50.0. En
    marche, la valeur en vigueur est en base : ``policy_en_vigueur``.
    """
    seed = load_policy_seed(directory)
    return nest({s.id: s.value for s in seed['settings']})
