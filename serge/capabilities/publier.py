#!/usr/bin/env python3
"""La capacité de publication : mettre un produit en ligne.

Le business, le livrable, la cible (staging ou prod) et le nom court du
produit sont des paramètres figés en base : le modèle ne choisit jamais
où un produit est publié.
"""

from __future__ import annotations

from serge.capabilities.model import Capability, Param

PUBLIER: tuple[Capability, ...] = (
    Capability(
        'publish_version',
        'Publier un produit',
        'En staging : fige le chantier du business en une version'
        ' (files/<business>/<livrable>/v<N>/), construit son image à partir'
        ' de son Dockerfile, lance le produit dans son conteneur et le met'
        ' en ligne derrière Caddy, sur staging-<produit>.<domaine>, non'
        ' indexé. En prod : reprend telle quelle la version du staging, sur'
        ' <produit>.<domaine> ou le domaine du produit. Rend l’adresse, ou'
        ' la fin du journal de construction ou du produit qui ne répond pas.',
        'serge/sandbox/publier.py',
        (
            Param('venture_id', 'text', True, 'Le business.'),
            Param('deliverable', 'text', True, 'Le livrable : poc, produit…'),
            Param('target', 'text', True, 'staging ou prod.'),
            Param('slug', 'text', False, 'Le nom court du produit.'),
            Param('domain', 'text', False, 'Le domaine du produit fini.'),
            Param('task_id', 'text', False, 'La tâche qui publie.'),
        ),
    ),
)
