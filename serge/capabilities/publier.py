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
            Param(
                'base_domain',
                'text',
                False,
                'Le domaine commun des produits finis : la prod sur'
                ' <produit>.<ce domaine>.',
            ),
            Param(
                'same_address',
                'text',
                False,
                'oui : la prod garde l’adresse où ce produit est déjà en'
                ' ligne (une nouvelle version).',
            ),
            Param(
                'contact',
                'text',
                False,
                'oui : le produit reçoit son adresse de contact'
                ' (CONTACT_EMAIL), et les e-mails écrits à cette adresse'
                ' sont rattachés à son business.',
            ),
            Param('task_id', 'text', False, 'La tâche qui publie.'),
            Param(
                'env_secrets',
                'text',
                False,
                'Les secrets du produit, figés en base :'
                ' STRIPE_SECRET_KEY=stripe-test.key.',
                frozen=True,
            ),
        ),
    ),
    Capability(
        'product_address',
        'Adresse d’un produit',
        'Rend l’adresse où un produit est, ou sera, publié, calculée comme la'
        ' publication la calcule : <produit>.<domaine commun> ou'
        ' <produit>.<domaine de l’instance> en prod, staging-<produit>… en'
        ' staging. Pour faire pointer ce nom vers le serveur avant de'
        ' publier.',
        'serge/ingress/adresse.py',
        (
            Param('venture_id', 'text', True, 'Le business.'),
            Param('target', 'text', False, 'staging ou prod (prod).'),
            Param('domain', 'text', False, 'Le domaine acheté, s’il y en a.'),
            Param('base_domain', 'text', False, 'Le domaine commun.'),
            Param('slug', 'text', False, 'Le nom court du produit.'),
        ),
    ),
    Capability(
        'server_address',
        'Adresse du serveur',
        'Rend le domaine de l’instance et l’adresse IPv4 publique du'
        ' serveur de Serge, pour faire pointer le domaine d’un produit vers'
        ' lui (un enregistrement DNS de type A).',
        'serge/ingress/adresse.py',
        (),
    ),
)
