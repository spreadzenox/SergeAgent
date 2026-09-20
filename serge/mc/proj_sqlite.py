#!/usr/bin/env python3
"""Miroir canon : catalogue des tables + fiche structure."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from serge.db.schema import SCHEMA_VERSION

_NOM_TABLE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

# role court, remplie par, sort vers, détail
CATALOGUE: dict[str, tuple[str, str, str, str]] = {
    'schema_version': (
        'Version du schéma. Si ça dérive, Health le dit.',
        'Migration au boot.',
        'Health (alerte schéma).',
        'Une ligne : le numéro appliqué. Pas de métier ici.',
    ),
    'ventures': (
        'Les paris : une offre, un cycle, schedulable ou non.',
        'Cycle de vie, owner, builder.',
        'campaigns, contacts, transactions, work_items.',
        'Objet cliquable « venture ». SMOKE / FULL / SCALE vivent ici.',
    ),
    'contacts': (
        'Une trace sur un lieu (venue + handle), pas un humain fusionné.',
        'upsert_trace, qualification, inbound, owner.',
        'touches, inbound_events, campagnes.',
        'Deux lieux, deux lignes. funnel_state + regime sur cette trace.',
    ),
    'campaigns': (
        'Un test sur un canal (e-mail, voix…) pour une venture.',
        'Séquenceur + hypothèse approuvée.',
        'touches, inbound_events, métriques U.',
        'state RUNNING/PAUSED. n_target = N du smoke.',
    ),
    'touches': (
        'Chaque geste sortant : un e-mail, un SMS, un appel.',
        'Workers send / voice.',
        'events, inbound (si réponse), jauges quota.',
        'idempotency_key empêche le double envoi.',
    ),
    'inbound_events': (
        'Ce qui revient : réponse, bounce, « stop ».',
        'Collecte boîte, Discord, voix.',
        'classify_reply, tickets, funnel_state.',
        'signal + classe. C’est l’entrée de la conversation.',
    ),
    'consents': (
        'Droit d’écrire / d’appeler. Hashé, révocable.',
        'Opt-in, base légale.',
        'Garde-fous canal (blocage si révoqué).',
        'Jamais le contact en clair : subject_hash.',
    ),
    'blocklist': (
        'Interdits : ne plus toucher ce sujet sur ce canal.',
        'Opt-out, owner, garde.',
        'Workers send (refus).',
        'Raison + date. Fail-closed.',
    ),
    'transactions': (
        'L’argent : draft → payé. Une intent Stripe = une ligne.',
        'Collect, Stripe, dunning.',
        'Économie, lignée euro, caisse.',
        'amount_eur + status. La preuve d’encaissement.',
    ),
    'events': (
        'Le journal append-only. Rien ne s’écrase.',
        'Tous les acteurs (workers, gardes, MC, LLM).',
        'Feed, preuves, mémoire, typewriter.',
        'type + payload_json. C’est ici qu’on lit un llm.io.',
    ),
    'work_items': (
        'La file : READY, RUNNING, DONE, échoué.',
        'Ordonnanceur (enqueue).',
        'Workers (claim), file MC, tickets si blocage.',
        'priority + blocked_until. Une tâche = un kind.',
    ),
    'tickets': (
        'Ce que toi seul peux trancher (veto, guichet, hypothèse).',
        'Gardes, LLM hors bornes, owner.',
        'Discord, page Décisions, actes MC.',
        'state OPEN/APPROVED… expiry_at pour l’urgence.',
    ),
    'ticket_items': (
        'Lignes d’un ticket (garder / modifier / jeter).',
        'Création de ticket, discussion.',
        'Actes item, tout-approuver.',
        'Une décision granulaire dans un ticket.',
    ),
    'ticket_events': (
        'Fil d’un ticket : qui a dit quoi, quand.',
        'MC, Discord, système.',
        'Carte ticket, parité Discord.',
        'Append-only comme events, mais scopé ticket.',
    ),
    'lessons': (
        'Ce que Serge croit avoir appris. Candidate d’abord.',
        'consolidate, owner (confirmer / infirmer).',
        'Points LLM (retrieved), policy mémoire.',
        'confidence + sources_json. Ça expire.',
    ),
    'playbooks': (
        'Recettes : si conditions, alors étapes.',
        'Mémoire, owner.',
        'Scale, pivot, workers.',
        'steps_json. Scope global ou venture.',
    ),
    'pitfalls': (
        'Pièges déjà payés. À ne pas reproduire.',
        'Revue de test, owner.',
        'plan_scale, options_pivot.',
        'cost_observed : ce que ça a coûté.',
    ),
    'summaries': (
        'Résumés versionnés (fils, tests). Le brut reste dans events.',
        'summarize_thread, resume_test.',
        'UI, runs LLM suivants.',
        'version + previous : on peut remonter.',
    ),
    'artifacts': (
        'Livrables (page, PDF) hashés.',
        'build_artifact.',
        'review_build, envoi.',
        'path_or_url + hash. Une version = une ligne.',
    ),
    'subscriptions': (
        'MRR : abonnements récurrents.',
        'Stripe / collect.',
        'Économie (MRR).',
        'period + renews_at + status.',
    ),
    'accounts_standing': (
        'Comptes web de Serge : santé + comment crawler'
        ' (rôle, profil navigateur, cibles). Login et mot de passe'
        ' en clair (comptes créés par Serge).',
        'Writer enregistrer_compte, écoute, publication.',
        'Jauges, allocator, pauses, tools web.',
        'role ecoute/publication/les_deux. login + password en clair.',
    ),
    'policy_snapshots': (
        'Photo de la policy appliquée. On sait qui a changé quoi.',
        'Actes policy MC.',
        'Audit, Health.',
        'content_hash + active_from.',
    ),
    'llm_usage': (
        'Compteur de chaque invocation : jetons, latence, verdict.',
        'run_point() uniquement.',
        'Cerveau (matrice), jauges €, fiches LLM.',
        'Pas le prompt : juste le mètre. Le texte est dans events.',
    ),
    'episode_archives': (
        'Archives de vieux épisodes (fichiers + empreinte).',
        'Job d’archivage.',
        'Mémoire froide.',
        'path + sha256 + count.',
    ),
    'listen_docs': (
        'Pages ramassées sur le web (écoute).',
        'Worker listen.collect.',
        'cluster_demand, nœud Écoute.',
        'excerpt borné. cluster_id après regroupement.',
    ),
    'mc_sessions': (
        'Sessions owner (cookie). Pas du métier.',
        'Login MC.',
        'Auth des API.',
        'token_hash + expires_at.',
    ),
    'runtime_flags': (
        'Kills runtime (couper un point LLM sans redeploy).',
        'Cerveau (Tuer / Relancer).',
        'run_point() (verdict killed).',
        'name + expires_at + reason.',
    ),
    'pipeline_steps': (
        'Les 7 étapes du pipe : en marche ou coupée, et quels kinds.',
        'Semence au boot ; toi via la carte Live.',
        'Ordonnanceur (next_ready ignore les kinds coupés).',
        'enabled + kinds_json. Un kind sans étape n’est jamais coupé.',
    ),
    'tools': (
        'Outils qu’un jugement peut presser (mémoire, web, ticket…).',
        'Semence git + SHA du fichier.',
        'Fiches MC, jonction llm_point_tools.',
        'kind déterministe/agent/web. doc_md = texte de la fiche.',
    ),
    'llm_points': (
        'Les jugements LLM : un id, un fichier, un SHA, une étape.',
        'Semence depuis llm-points.yaml + verrou fichier.',
        'Fiches MC, runtime encore le YAML.',
        'code_sha doit matcher le .py (test).',
    ),
    'llm_point_tools': (
        'Quel jugement a le droit d’utiliser quel outil.',
        'Recalculé au boot depuis couche5 / tools: du YAML.',
        'Fiche jugement, rubrique Outils.',
        'usage : autorise, interdit, declare.',
    ),
    'db_readers': (
        'Lecteurs DB nommés : vues fixes et sorties typées pour les agents.',
        'Semence code idempotente ; contrats implémentés dans memory.py.',
        'Fiches agents et onglet Écoute.',
        'Aucun SQL libre ; chaque lecteur possède son contrat.',
    ),
    'llm_point_readers': (
        'Permissions de lecture DB par invocation LLM.',
        'Projection du champ context.db_readers dans llm-points.yaml.',
        'Runtime et Mission Control.',
        'La déclaration YAML est la source ; SQLite est la projection vérifiée.',
    ),
    'listen_cycles': (
        'Cycles de recherche business avec cibles explicites et guide owner.',
        'Mission Control, cycle lancé manuellement.',
        'Agents d’écoute et onglet Écoute.',
        'Le guide et les paramètres sont historisés.',
    ),
    'business_candidates': (
        'Mémoire canonique des besoins et business pré-prospectés.',
        'Writer déterministe après jugements.',
        'Sélection POC et Mission Control.',
        'normalized_key et status empêchent les doublons et le rechoix.',
    ),
    'canaux': (
        'Moyens d’écrire vers l’extérieur (e-mail, voix, Discord…).',
        'Semence git + SHA du fichier writer.',
        'Fiches MC, jonction brique_canaux.',
        'etat branche/prevu. doc_md = texte de la fiche.',
    ),
    'brique_canaux': (
        'Quelle brique (LLM ou tech) utilise quel canal.',
        'Recalculé au boot depuis serge/canaux.py.',
        'Fiches canal / jugement / étape.',
        'brique_kind : llm ou tech.',
    ),
}


def _meta(nom: str) -> tuple[str, str, str, str]:
    found = CATALOGUE.get(nom)
    if found:
        return found
    return (
        'Table du canon.',
        'Écritures métier.',
        'Lectures MC / workers.',
        'Voir les colonnes ci-dessous.',
    )


def _tables_live(conn: sqlite3.Connection) -> list[str]:
    """Tables réellement présentes (pas la liste figée du schéma)."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
        " AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [str(r[0]) for r in rows if _NOM_TABLE.match(str(r[0]))]


def _lignes(conn: sqlite3.Connection, nom: str) -> int:
    if not _NOM_TABLE.match(nom):
        return 0
    return int(conn.execute(f'SELECT COUNT(*) FROM {nom}').fetchone()[0])


def project_sqlite(
    conn: sqlite3.Connection, ident: str = ''
) -> dict[str, Any]:
    """Catalogue vivant : une ligne par table, compteur à jour."""
    _ = ident
    total = 0
    lignes = []
    noms = _tables_live(conn)
    for nom in noms:
        role, par, vers, _detail = _meta(nom)
        n = _lignes(conn, nom)
        total += n
        lignes.append(
            {
                'id': nom,
                'type': 'table',
                'cellules': [nom, role, par, vers, str(n)],
            }
        )
    return {
        'type': 'sqlite',
        'id': 'canon',
        'titre': 'Canon SQLite',
        'pourquoi': (
            'Une seule vérité. Chaque table est un tiroir du métier :'
            ' qui l’écrit, qui la lit, où ça ressort. Les compteurs'
            ' sont ceux de cette instance, maintenant.'
        ),
        'champs': [
            {'k': 'Tables', 'v': str(len(noms))},
            {'k': 'Lignes', 'v': str(total)},
            {'k': 'Schéma', 'v': f'v{SCHEMA_VERSION}'},
        ],
        'tableau': {
            'titre': 'Tables du canon',
            'colonnes': [
                'Table',
                'Rôle',
                'Remplie par',
                'Sort vers',
                'Lignes',
            ],
            'lignes': lignes,
        },
        'enfants': [],
        'preuve': '',
    }


def project_table(
    conn: sqlite3.Connection, ident: str
) -> dict[str, Any] | None:
    """Structure d’une table : colonnes réelles + explication."""
    if ident not in _tables_live(conn):
        return None
    role, par, vers, detail = _meta(ident)
    cols = conn.execute(f'PRAGMA table_info({ident})').fetchall()
    lignes = []
    for col in cols:
        lignes.append(
            {
                'id': '',
                'type': '',
                'cellules': [
                    str(col[1]),
                    str(col[2] or '—'),
                    'clé primaire' if col[5] else '—',
                ],
            }
        )
    return {
        'type': 'table',
        'id': ident,
        'titre': f'Table {ident}',
        'pourquoi': f'{role} {detail}',
        'champs': [
            {'k': 'Remplie par', 'v': par},
            {'k': 'Sort vers', 'v': vers},
            {'k': 'Lignes maintenant', 'v': str(_lignes(conn, ident))},
            {'k': 'Colonnes', 'v': str(len(cols))},
        ],
        'tableau': {
            'titre': 'Structure',
            'colonnes': ['Colonne', 'Type', 'Clé'],
            'lignes': lignes,
        },
        'cadres': [
            {
                'titre': 'Canon',
                'liens': [
                    {
                        'type': 'sqlite',
                        'id': 'canon',
                        'titre': 'Toutes les tables',
                    }
                ],
            }
        ],
        'enfants': [],
        'preuve': '',
    }
