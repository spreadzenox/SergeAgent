#!/usr/bin/env python3
"""Erreurs partagées par le constructeur de requêtes DB."""


class DbReadError(ValueError):
    """Contrat DB invalide ou arguments hors contrat."""
