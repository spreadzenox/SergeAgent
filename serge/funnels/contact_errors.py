#!/usr/bin/env python3
"""Erreurs et états terminaux partagés par les modules contact."""


class ContactError(ValueError):
    pass


TERMINAL = frozenset(
    {
        'REJECTED',
        'UNREACHABLE',
        'OPTED_OUT',
        'BLOCKED',
        'INVALID',
        'CUSTOMER',
    }
)
