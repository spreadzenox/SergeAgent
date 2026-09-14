#!/usr/bin/env python3
"""Docs MC et liens d’épine : semence canon (P3, pas de SQL libre)."""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.horloge import iso_utc

# Enum fermé : clé → compteur d’occurrences (pas une requête libre).
DEBITS = frozenset(
    {
        'listen_docs',
        'campaigns',
        'contacts',
        'artifacts',
        'touches',
        'inbound_events',
        'transactions',
    }
)

_DEBIT_SQL = {
    'listen_docs': 'SELECT COUNT(*) FROM listen_docs',
    'campaigns': 'SELECT COUNT(*) FROM campaigns',
    'contacts': 'SELECT COUNT(*) FROM contacts',
    'artifacts': 'SELECT COUNT(*) FROM artifacts',
    'touches': 'SELECT COUNT(*) FROM touches',
    'inbound_events': 'SELECT COUNT(*) FROM inbound_events',
    'transactions': 'SELECT COUNT(*) FROM transactions',
}

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
            'Mêmes canaux que la prospection lourde (e-mail, appel). On coupe'
            ' ce sac, pas le kind : la lourde peut continuer à envoyer.'
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
        'comment': (
            'Qualification, conversation, prix : mêmes kinds que le smoke,'
            ' autre etape_id.'
        ),
        'doc_md': '',
    },
    'collect_feedback': {
        'titre': 'Collect feedback',
        'pourquoi': (
            'Mails, transcripts, réseaux, leçons — améliorer le livrable ou Serge.'
        ),
        'argent': 'Les leçons évitent de payer deux fois la même erreur.',
        'dependance': 'Sans échanges, rien à consolider.',
        'comment': 'Work items mémoire et invocations de consolidation.',
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

# id, de, vers, libelle, debit, rang
LIENS: tuple[tuple[str, str, str, str, str, int], ...] = (
    (
        'pre-poc',
        'pre_prospection',
        'conception_poc',
        'docs d’écoute',
        'listen_docs',
        0,
    ),
    (
        'poc-light',
        'conception_poc',
        'prospection_light',
        'campagnes',
        'campaigns',
        1,
    ),
    (
        'light-choix',
        'prospection_light',
        'choix_venture',
        'prospects',
        'contacts',
        2,
    ),
    (
        'choix-build',
        'choix_venture',
        'build_venture',
        'livrables',
        'artifacts',
        3,
    ),
    (
        'build-lourde',
        'build_venture',
        'prospection_lourde',
        'touches',
        'touches',
        4,
    ),
    (
        'lourde-feedback',
        'prospection_lourde',
        'collect_feedback',
        'réponses',
        'inbound_events',
        5,
    ),
    (
        'lourde-caisse',
        'prospection_lourde',
        'caisse',
        'factures',
        'transactions',
        6,
    ),
)


class LienError(ValueError):
    """Lien d’épine ou débit inconnu."""


def compter_debit(conn: sqlite3.Connection, debit: str) -> int:
    """Compte les occurrences d’un débit (enum fermé).

    Args:
        conn: Canon.
        debit: Clé ``DEBITS``.

    Returns:
        Entier ≥ 0 (0 si clé inconnue).
    """
    sql = _DEBIT_SQL.get(debit)
    if not sql:
        return 0
    row = conn.execute(sql).fetchone()
    return int(row[0]) if row else 0


def ensure_etape_liens(conn: sqlite3.Connection) -> None:
    """Pose les arêtes Live ; met à jour libellé/débit, jamais un SQL libre.

    Args:
        conn: Canon (commit par l’appelant).
    """
    now = iso_utc()
    ids: list[str] = []
    for ident, de, vers, libelle, debit, rang in LIENS:
        if debit not in DEBITS:
            raise LienError(f'débit inconnu : {debit}')
        ids.append(ident)
        found = conn.execute(
            'SELECT 1 FROM etape_liens WHERE id=?', (ident,)
        ).fetchone()
        if found:
            conn.execute(
                'UPDATE etape_liens SET de=?, vers=?, libelle=?, debit=?,'
                ' rang=? WHERE id=?',
                (de, vers, libelle, debit, rang, ident),
            )
            continue
        conn.execute(
            'INSERT INTO etape_liens(id, de, vers, libelle, debit, rang,'
            " files_sha, updated_at) VALUES(?,?,?,?,?,?, '', ?)",
            (ident, de, vers, libelle, debit, rang, now),
        )
    conn.execute(
        'DELETE FROM etape_liens WHERE id NOT IN'
        f' ({",".join("?" * len(ids))})',
        ids,
    )


def precedente(conn: sqlite3.Connection, ident: str) -> str:
    """Id d’étape amont (premier lien entrant), ou vide.

    Args:
        conn: Canon.
        ident: Étape cible.

    Returns:
        Id source, ou ``''``.
    """
    row = conn.execute(
        'SELECT de FROM etape_liens WHERE vers=? ORDER BY rang, id LIMIT 1',
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
