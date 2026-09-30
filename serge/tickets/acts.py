#!/usr/bin/env python3
"""Les noms des actes tickets communs à Discord et Mission Control."""

APPROVE = frozenset(
    {
        'approuver',
        'approuver_version',
        'cest_fait',
        'confirmer',
        'ouvrir',
        'tout_approuver',
    }
)
REJECT = frozenset({'rejeter', 'abandonner', 'refuser', 'annuler'})
