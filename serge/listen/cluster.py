#!/usr/bin/env python3
"""Clustering écoute dét (Jaccard + union-find) + filtre opportunité chaude.

v1 sans embeddings (sqlite-vec absent) : Jaccard sur tokens FR/EN hors
stopwords, seuil policy. Singletons = bruit (restent non clusterisés,
re-tentés au prochain batch). Chaud = volume ET willingness ≥ seuils.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from serge.policy import PolicyError

STOPWORDS = frozenset(
    """
    le la les de des du un une et ou mais donc or ni car pour dans avec sur
    sous plus moins tres aussi tout tous toute toutes ce cette ces mon ton son
    ma ta sa mes tes ses notre votre leur nos vos leurs il elle ils elles nous
    vous je tu on que qui quoi dont ou est sont etait avoir faire dire plus
    the a an and or but for with on in at to of is are was were be been have
    has this that these those you your we our they their he she it his her its
    """.split()
)


def tokens(text: str) -> set[str]:
    """Tokens significatifs (minuscules, ≥ 3 lettres, hors stopwords).

    Args:
        text: Texte brut.

    Returns:
        Ensemble de tokens.
    """
    words = re.findall(r'[a-zàâäéèêëîïôöùûüç]+', text.lower())
    return {word for word in words if len(word) >= 3 and word not in STOPWORDS}


def jaccard(left: set[str], right: set[str]) -> float:
    """Similarité Jaccard (0-1, 0 si vide).

    Args:
        left: Tokens doc A.
        right: Tokens doc B.

    Returns:
        Intersection / union.
    """
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def cluster_docs(
    docs: Sequence[Mapping[str, Any]],
    *,
    threshold: float = 0.25,
    min_size: int = 2,
) -> list[dict[str, Any]]:
    """Regroupe par Jaccard (union-find). Singletons écartés.

    Args:
        docs: [{id, title, excerpt}].
        threshold: Seuil Jaccard (policy).
        min_size: Taille min cluster.

    Returns:
        Clusters [{id: k1..., doc_ids[]}] (triés, stables).
    """
    items = list(docs)
    parent = list(range(len(items)))
    tokenized = [
        tokens(f'{item.get("title", "")} {item.get("excerpt", "")}')
        for item in items
    ]

    def _find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for left in range(len(items)):
        for right in range(left + 1, len(items)):
            if jaccard(tokenized[left], tokenized[right]) >= threshold:
                parent[_find(left)] = _find(right)
    groups: dict[int, list[str]] = {}
    for index, item in enumerate(items):
        groups.setdefault(_find(index), []).append(str(item.get('id')))
    clusters = []
    for rank, (_, doc_ids) in enumerate(
        sorted(groups.items(), key=lambda kv: min(kv[1])), start=1
    ):
        if len(doc_ids) >= max(2, min_size):
            clusters.append({'id': f'k{rank}', 'doc_ids': sorted(doc_ids)})
    return clusters


def hot_thresholds(policy: Mapping[str, Any]) -> tuple[float, float]:
    """Seuils opportunité chaude (policy listen, validés).

    Args:
        policy: Policy.

    Returns:
        Tuple (volume_min, willingness_min).

    Raises:
        PolicyError: Seuils invalides.
    """
    section = policy.get('listen') or {}
    try:
        volume = float(section.get('hot_min_volume', 0.7))
        willing = float(section.get('hot_min_willingness', 0.7))
    except (TypeError, ValueError) as exc:
        raise PolicyError('policy.listen.hot_* invalide') from exc
    if not 0.0 <= volume <= 1.0 or not 0.0 <= willing <= 1.0:
        raise PolicyError('policy.listen.hot_* hors [0,1]')
    return volume, willing


def hot_clusters(
    labels: Sequence[Mapping[str, Any]], policy: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Filtre les clusters chauds (volume ET willingness ≥ seuils).

    Args:
        labels: Sortie J1 [{id, label, volume, willingness...}].
        policy: Policy (seuils listen).

    Returns:
        Sous-liste chaude.
    """
    volume_min, willing_min = hot_thresholds(policy)
    hot: list[dict[str, Any]] = []
    for item in labels:
        try:
            volume = float(item.get('volume', 0))
            willing = float(item.get('willingness', 0))
        except (TypeError, ValueError):
            continue
        if volume >= volume_min and willing >= willing_min:
            hot.append(dict(item))
    return hot
