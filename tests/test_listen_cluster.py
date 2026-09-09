#!/usr/bin/env python3
"""Clustering dét : Jaccard, union-find, seuils opportunité chaude."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.listen.cluster import (  # noqa: E402
    cluster_docs,
    hot_clusters,
    jaccard,
    tokens,
)

POLICY = {'listen': {'hot_min_volume': 0.7, 'hot_min_willingness': 0.7}}


class ClusterTests(unittest.TestCase):
    def test_tokens_et_jaccard(self) -> None:
        self.assertIn('artisans', tokens('Les artisans et le prix'))
        self.assertNotIn('les', tokens('Les artisans'))
        self.assertEqual(jaccard(set(), {'a'}), 0.0)
        self.assertAlmostEqual(
            jaccard({'a', 'b'}, {'b', 'c'}), 1 / 3, places=3
        )

    def test_regroupe_proches(self) -> None:
        docs = [
            {
                'id': 'd1',
                'title': 'Facture artisan trop chère',
                'excerpt': 'Les artisans se plaignent des factures salées.',
            },
            {
                'id': 'd2',
                'title': 'Artisans : factures salées',
                'excerpt': 'La facture des artisans augmente encore.',
            },
            {
                'id': 'd3',
                'title': 'Recette quiche lorraine',
                'excerpt': 'Battre les œufs avec la crème fraîche.',
            },
        ]
        clusters = cluster_docs(docs, threshold=0.25)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]['doc_ids'], ['d1', 'd2'])

    def test_seuil_strict_separe(self) -> None:
        docs = [
            {'id': 'd1', 'title': 'Prix email', 'excerpt': 'Email pas cher.'},
            {
                'id': 'd2',
                'title': 'Voix téléphone',
                'excerpt': 'Appels longs.',
            },
        ]
        self.assertEqual(cluster_docs(docs, threshold=0.9), [])

    def test_hot_filtre(self) -> None:
        labels = [
            {'id': 'k1', 'volume': 0.8, 'willingness': 0.9},
            {'id': 'k2', 'volume': 0.8, 'willingness': 0.2},
            {'id': 'k3', 'volume': 0.1, 'willingness': 0.9},
        ]
        hot = hot_clusters(labels, POLICY)
        self.assertEqual([item['id'] for item in hot], ['k1'])


if __name__ == '__main__':
    unittest.main()
