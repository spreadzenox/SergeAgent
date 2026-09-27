#!/usr/bin/env python3
"""Les textes de chaque étape, montrés dans Mission Control."""

from __future__ import annotations

import sqlite3
from typing import Any

# id → textes fiche / carte Live.
FICHES: dict[str, dict[str, str]] = {
    'pre_prospection': {
        'titre': 'Pré-prospection',
        'pourquoi': (
            'Serge lit ce que des inconnus ont déjà écrit (forums, flux…).'
            ' But : sentir une demande réelle, pas inventer une idée.'
        ),
        'argent': 'Sans demande observée, pas de pré-venture à concevoir.',
        'dependance': 'Rien avant. C’est le début du pipe.',
        'comment': (
            'Ramasser des pages, les ranger, puis une invocation LLM les'
            ' met en paquets. Le navigateur n’est pas encore un bouton.'
        ),
        'doc_md': '',
    },
    'conception_poc': {
        'titre': 'Conception d’un PoC',
        'pourquoi': (
            'On écrit la pré-venture : produit, specs, prérequis, puis on'
            ' appelle le builder si un livrable est nécessaire.'
        ),
        'argent': 'Le PoC sert à faire valoir que le produit existe.',
        'dependance': (
            'Sans paquets de demandes (pré-prospection), on n’a qu’une intuition.'
        ),
        'comment': (
            'Le PoC (landing, SaaS, livrable) sert ensuite au smoke test :'
            ' on ne vend plus seulement un concept.'
        ),
        'doc_md': '',
    },
    'prospection_light': {
        'titre': 'Prospection light',
        'pourquoi': (
            'Smoke test multicanal (N configurable dans Mission Control),'
            ' avec le PoC s’il existe.'
        ),
        'argent': 'On mesure le message, pas encore l’encaissement.',
        'dependance': (
            'Sans pré-venture écrite, on ne saurait pas ce qu’on mesure.'
        ),
        'comment': (
            'Mêmes canaux que la prospection lourde (e-mail, appel). Couper'
            ' cette étape laisse la prospection lourde continuer.'
        ),
        'doc_md': '',
    },
    'choix_venture': {
        'titre': 'Choix de venture',
        'pourquoi': (
            'Parmi les N pré-ventures et leurs smokes, garder la plus prometteuse.'
        ),
        'argent': 'Un seul actif aujourd’hui ; MC pourra en ouvrir d’autres.',
        'dependance': (
            'Sans résultats de smoke, le choix n’est qu’une préférence.'
        ),
        'comment': (
            'Aujourd’hui N=1 actif max. Mission Control pourra ouvrir la porte.'
        ),
        'doc_md': '',
    },
    'build_venture': {
        'titre': 'Build / rebuild',
        'pourquoi': (
            'Créer ou améliorer la venture active : livrable, delivery,'
            ' onboarding client.'
        ),
        'argent': 'Sans livrable, la prospection lourde vend du vent.',
        'dependance': (
            'On build à partir de la pré-venture choisie et des retours.'
        ),
        'comment': (
            'Toute la partie building / delivery est ici, y compris après vente.'
        ),
        'doc_md': '',
    },
    'prospection_lourde': {
        'titre': 'Prospection lourde',
        'pourquoi': (
            'Échanges, démo, jusqu’à la signature d’un devis et un client actif.'
        ),
        'argent': 'C’est ici qu’une touche devient un contrat.',
        'dependance': 'Sans venture active et livrable, on vend du vent.',
        'comment': ('Qualification, conversation, prix.'),
        'doc_md': '',
    },
    'collect_feedback': {
        'titre': 'Collect feedback',
        'pourquoi': (
            'Mails, transcripts, réseaux, leçons — améliorer le livrable ou Serge.'
        ),
        'argent': 'Les leçons évitent de payer deux fois la même erreur.',
        'dependance': 'Sans échanges, rien à consolider.',
        'comment': 'La consolidation des leçons (pas encore branchée).',
        'doc_md': '',
    },
    'caisse': {
        'titre': 'Caisse',
        'pourquoi': (
            'L’euro entre (Stripe, devis payé). Dunning et relances d’encaissement.'
        ),
        'argent': 'L’euro entre ici. Tout le reste sert ce nœud.',
        'dependance': 'Sans client / devis, encaisser ce serait vendre du vent.',
        'comment': (
            'Pas une invocation LLM qui « crée l’argent ». Le rail encaisse ;'
            ' les règles autorisent ou refusent.'
        ),
        'doc_md': '',
    },
}


def precedente(conn: sqlite3.Connection, ident: str) -> str:
    """L'étape d'avant dans la chaîne (par rang), ou vide.

    Args:
        conn: Connexion à la base.
        ident: Étape visée.

    Returns:
        Id de l'étape d'avant, ou ``''`` pour la première.
    """
    row = conn.execute(
        'SELECT id FROM pipeline_steps WHERE rang < (SELECT rang FROM'
        ' pipeline_steps WHERE id=?) ORDER BY rang DESC LIMIT 1',
        (ident,),
    ).fetchone()
    return str(row[0]) if row else ''


def fiche_etape(conn: sqlite3.Connection, ident: str) -> dict[str, Any] | None:
    """Ligne docs d’une étape, ou None.

    Args:
        conn: Canon.
        ident: Id d’étape.

    Returns:
        ``{titre, pourquoi, argent, dependance, comment, doc_md,
        files_sha, updated_at}``.
    """
    row = conn.execute(
        'SELECT titre, pourquoi, argent, dependance, comment, doc_md,'
        ' files_sha, updated_at FROM pipeline_steps WHERE id=?',
        (ident,),
    ).fetchone()
    if row is None:
        return None
    return {
        'titre': str(row[0] or ''),
        'pourquoi': str(row[1] or ''),
        'argent': str(row[2] or ''),
        'dependance': str(row[3] or ''),
        'comment': str(row[4] or ''),
        'doc_md': str(row[5] or ''),
        'files_sha': str(row[6] or ''),
        'updated_at': str(row[7] or ''),
    }
