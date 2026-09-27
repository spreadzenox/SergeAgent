#!/usr/bin/env python3
"""Outils pressables par une invocation (table tools + semence git)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

KINDS_OUTIL = frozenset({'deterministe', 'web', 'agent', 'db_read'})


def outil_peut_invoquer(appelant_kind: str, cible_kind: str) -> bool:
    """Seul un non-agent (invocation LLM) enchaîne un tool agent.

    Args:
        appelant_kind: Kind de l’appelant (tool ou ``llm``).
        cible_kind: Kind du tool cible.

    Returns:
        False si un agent appellerait un autre agent.
    """
    return not (appelant_kind == 'agent' and cible_kind == 'agent')


# id, kind, path, titre, doc, etat, montre_partout
# L’empreinte du fichier est calculée au boot (serge/objet_sha.py).
SEED: tuple[tuple[str, str, str, str, str, str, int], ...] = (
    (
        'memory_search',
        'deterministe',
        'serge/memory/search.py',
        'Chercher dans la mémoire',
        'Un seul outil pour fouiller la mémoire. Si le dossier prévu'
        ' ne suffit pas, l’invocation pose une question (« objections'
        ' prix artisans ») et ramène quelques extraits — dans un budget.'
        ' Lecture seule : ça informe, ça n’écrit pas. Certaines invocations'
        ' n’y ont pas droit (un appel, un résumé chiffré) : ils restent'
        ' sur le dossier figé.',
        'branche',
        0,
    ),
    (
        'contact_upsert',
        'deterministe',
        'serge/funnels/contact_tool.py',
        'Créer ou enrichir un contact',
        'Upsert déterministe par références JSON de canal. Compare toutes les'
        ' références de la venture avant création, puis ajoute les canaux actifs.'
        ' Les anciennes colonnes email/phone/venue/handle/profile_url ne sont'
        ' jamais écrites par cet outil.',
        'branche',
        0,
    ),
    (
        'navigateur',
        'web',
        '',
        'Ouvrir le web (navigateur)',
        'Un vrai navigateur (Brave / Chromium) pour aller voir une'
        ' page, un fil Reddit, un profil. Pas encore branché comme'
        ' outil de l’invocation. Aujourd’hui Serge ramasse surtout des'
        ' flux RSS. Un budget navigateur existe déjà dans les règles.',
        'prevu',
        1,
    ),
    (
        'identity_basique',
        'deterministe',
        'serge/identite.py',
        'Identité de Serge (basique)',
        'Lecteur unique : email, prénom, nom, pseudo, n° 2FA, n° DID,'
        ' SIRET. Source = instance, pas une table. Interdit d’ouvrir'
        ' le TOML dans un prompt.',
        'branche',
        0,
    ),
    (
        'identity_advanced',
        'deterministe',
        'serge/identite.py',
        'Identité avancée (IBAN, facturation)',
        'Même source que le basique, plus IBAN et adresse de'
        ' facturation. Personne ne l’appelle tant qu’un acte n’est'
        ' pas nommé. Pas de carte en clair.',
        'prevu',
        0,
    ),
    (
        'boite_serge',
        'deterministe',
        'serge/boite.py',
        'Boîte mail et SMS',
        'Lecture : corps brut, heure, expéditeur, destinataire,'
        ' historique. Le 2FA se lit tout seul. Pas un GUICHET.',
        'branche',
        0,
    ),
    (
        'demande_capacite',
        'deterministe',
        'serge/demande_capacite.py',
        'Demander une nouvelle capacité',
        'Quand Serge ne peut pas (pas de canal, pas d’outil), il'
        ' pose un ticket REQUESTED (« j’ai besoin de X ») plutôt'
        ' que d’inventer. Offert à toutes les invocations. Un appel'
        ' par invocation ; le même besoin déjà ouvert n’est pas'
        ' recréé.',
        'branche',
        1,
    ),
    (
        'agenda',
        'deterministe',
        '',
        'Agenda',
        'Créneaux et disponibilités. Cité par le dialogue voix.'
        ' Pas encore un module runtime.',
        'prevu',
        0,
    ),
    (
        'catalogue',
        'deterministe',
        '',
        'Catalogue',
        'Prix et offres ownés. L’invocation n’invente pas un montant.'
        ' Pas encore un module runtime.',
        'prevu',
        0,
    ),
    (
        'fiches',
        'deterministe',
        '',
        'Fiches prospect',
        'Fiche de la personne en cours d’appel. Cité par le dialogue voix.'
        ' Pas encore un module runtime.',
        'prevu',
        0,
    ),
    (
        'current_listen_cycle',
        'db_read',
        'serge/db/query_builder.py',
        'Lire le cycle d’écoute courant',
        'Lecture DB bornée par le catalogue du tool et son paramètre cycle_id.',
        'branche',
        0,
    ),
    (
        'listen_cycle_documents',
        'db_read',
        'serge/db/query_builder.py',
        'Lire les documents du cycle',
        'Lecture des documents rattachés au cycle fourni par le contexte.',
        'branche',
        0,
    ),
    (
        'known_business_candidates',
        'db_read',
        'serge/db/query_builder.py',
        'Lire les business connus',
        'Lecture des candidats business déjà persistés.',
        'branche',
        0,
    ),
    (
        'eligible_poc_candidates',
        'db_read',
        'serge/db/query_builder.py',
        'Lire les candidats POC éligibles',
        'Lecture des candidats dont le statut permet encore une sélection.',
        'branche',
        0,
    ),
    (
        'web_search',
        'web',
        'serge/listen/web.py',
        'Chercher sur le web public',
        'Recherche publique en lecture seule, sans compte ni action externe.',
        'branche',
        0,
    ),
)


def ensure_tools(conn: sqlite3.Connection) -> None:
    """Sème les outils. Chemin/kind depuis git ; titre/doc seulement à l’insert.

    Args:
        conn: Canon (commit par l’appelant).
    """
    for (
        ident,
        kind,
        path,
        titre,
        doc,
        etat,
        partout,
    ) in SEED:
        row = conn.execute(
            'SELECT 1 FROM tools WHERE id=?', (ident,)
        ).fetchone()
        if row:
            conn.execute(
                'UPDATE tools SET kind=?, code_path=?, etat=?,'
                ' montre_partout=? WHERE id=?',
                (kind, path, etat, partout, ident),
            )
            continue
        conn.execute(
            'INSERT INTO tools(id, kind, code_path, titre,'
            ' doc_md, etat, montre_partout) VALUES(?,?,?,?,?,?,?)',
            (ident, kind, path, titre, doc, etat, partout),
        )


def outil_par_id(
    conn: sqlite3.Connection, ident: str
) -> dict[str, Any] | None:
    """Une ligne tools, ou None.

    Args:
        conn: Canon.
        ident: Id d’outil (par exemple ``memory_search``).

    Returns:
        Dict ou None.
    """
    ensure_tools(conn)
    row = conn.execute(
        'SELECT id, kind, code_path, code_sha, titre, doc_md, etat,'
        ' montre_partout, files_sha, updated_at FROM tools WHERE id=?',
        (ident,),
    ).fetchone()
    if row is None:
        return None
    return _ligne(row)


def outils_partout(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Outils affichés sur toutes les fiches invocation."""
    ensure_tools(conn)
    rows = conn.execute(
        'SELECT id, kind, code_path, code_sha, titre, doc_md, etat,'
        ' montre_partout, files_sha, updated_at FROM tools'
        ' WHERE montre_partout=1 ORDER BY id'
    ).fetchall()
    return [_ligne(r) for r in rows]


def mtime_fichier(root: Path, rel: str) -> str:
    """Date de modification du fichier, ou vide.

    Args:
        root: Racine repo.
        rel: Chemin relatif.

    Returns:
        ISO UTC, ou ``''``.
    """
    if not rel:
        return ''
    path = root / rel
    if not path.is_file():
        return ''
    stamp = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    return stamp.isoformat()


def _ligne(row: Any) -> dict[str, Any]:
    return {
        'id': str(row[0]),
        'kind': str(row[1]),
        'code_path': str(row[2] or ''),
        'code_sha': str(row[3] or ''),
        'titre': str(row[4]),
        'doc_md': str(row[5]),
        'etat': str(row[6]),
        'montre_partout': bool(row[7]),
        'files_sha': str(row[8] or '') if len(row) > 8 else '',
        'updated_at': str(row[9] or '') if len(row) > 9 else '',
    }
