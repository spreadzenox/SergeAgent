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
    'capabilities': (
        'Ce que le code sait faire : lire la base, chercher sur le web…',
        'Le code, au démarrage.',
        'Les outils et les invocations sans LLM.',
        'available = 0 : la capacité a été retirée du code.',
    ),
    'invocations': (
        'Chaque invocation, avec ou sans LLM, et tous ses réglages.',
        'pipeline.yaml au départ, puis Mission Control.',
        'Le runner, qui lit ces réglages pour chaque tâche.',
        'deleted_at rempli : supprimée, jamais recréée au démarrage.',
    ),
    'invocation_tools': (
        'Les outils de chaque invocation : donnés d’office ou appelables.',
        'pipeline.yaml au départ, puis Mission Control.',
        'Le prompt de l’invocation et ses appels d’outils.',
        'mode = given : lu avant l’appel ; callable : le modèle décide.',
    ),
    'invocation_writes': (
        'Où chaque invocation écrit sa réponse, et comment.',
        'pipeline.yaml au départ, puis Mission Control.',
        'Le code d’écriture générique.',
        'Une ligne par table visée ; les colonnes sont dans'
        ' invocation_write_values.',
    ),
    'links': (
        'Les liens entre invocations : qui passe la main à qui.',
        'pipeline.yaml au départ, puis Mission Control.',
        'Le runner, à la fin de chaque tâche.',
        'mode = per_row : une tâche par ligne écrite.',
    ),
    'triggers': (
        'Ce qui lance une invocation : une ligne écrite, une heure, un bouton.',
        'pipeline.yaml au départ, puis Mission Control.',
        'Le runner.',
        'event = every, at, row_written ou button.',
    ),
    'tasks': (
        'La file des tâches : une tâche lance une invocation.',
        'Les liens, les déclencheurs et les boutons.',
        'Le runner, deux files en parallèle.',
        'Les paramètres de chaque tâche sont dans task_params.',
    ),
    'task_inputs': (
        'Ce qu’une tâche a reçu d’office : lignes données, lignes laissées.',
        'L’interpréteur, avant l’appel au modèle.',
        'Fiche d’une tâche.',
        'Une ligne par outil donné d’office.',
    ),
    'writable_tables': (
        'Les tables qu’une invocation a le droit d’écrire.',
        'pipeline.yaml au départ.',
        'Le code d’écriture générique (refus sinon).',
        'Colonnes permises dans writable_columns.',
    ),
    'status_transitions': (
        'Les changements de statut permis, par table et colonne.',
        'pipeline.yaml au départ.',
        'Le code d’écriture générique.',
        'Exemple : CANDIDATE → POC_SELECTED ; tout autre passage est refusé.',
    ),
    'dedup_rules': (
        'Comment repérer un doublon dans une table.',
        'pipeline.yaml au départ.',
        'Le code d’écriture générique (ligne écartée, notée au journal).',
        'method exact ou shared_words (un seuil en %).',
    ),
    'queues': (
        'Les deux files : conversations et travaux.',
        'pipeline.yaml au départ ; le coupe-circuit de MC.',
        'Les deux programmes serge-queue.',
        'enabled = 0 : la file ne prend plus de tâche.',
    ),
    'schema_version': (
        'Version du schéma. Si ça dérive, Health le dit.',
        'Migration au boot.',
        'Health (alerte schéma).',
        'Une ligne : le numéro appliqué. Pas de métier ici.',
    ),
    'ventures': (
        'Les business, de leur découverte à leur fermeture. Une ligne par business.',
        'Étape 1 (découverte, choix), puis le cycle de vie.',
        'campaigns, contacts, transactions, venture_sources.',
        'lifecycle = le statut : CANDIDATE, POC_SELECTED, SMOKE_…, FULL_…',
    ),
    'contacts': (
        'Une fiche par personne, dans un business : où elle en est.',
        'Tool contact_upsert, qualification, réponses reçues.',
        'contact_addresses, touches, inbound_events, campagnes.',
        'funnel_state = l’étape du prospect, regime = qui a écrit en premier.',
    ),
    'contact_addresses': (
        'Les adresses d’une personne : une ligne par adresse, jamais écrasée.',
        'Tool contact_upsert.',
        'Envois (e-mail, appel), relève de la boîte mail.',
        'channel = email, phone ou un réseau. active = 0 : ne plus écrire là.',
    ),
    'campaigns': (
        'Un test sur un canal (e-mail, voix…) pour une venture.',
        'Hypothèse approuvée + workers du canal.',
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
        'Tous les acteurs (tâches, écritures, gardes, MC).',
        'Feed, preuves, mémoire.',
        'type + payload_json. Chaque écriture et chaque refus y sont notés.',
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
        'Points LLM disposant de l’outil mémoire, policy mémoire.',
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
        'Compteur de chaque appel au modèle : jetons, durée, verdict.',
        'L’interpréteur, à chaque appel.',
        'Cerveau (invocations), jauges €, fiches invocation.',
        'point = l’invocation. Pas le prompt : juste le mètre.',
    ),
    'episode_archives': (
        'Archives de vieux épisodes (fichiers + empreinte).',
        'Job d’archivage.',
        'Mémoire froide.',
        'path + sha256 + count.',
    ),
    'listen_docs': (
        'Pages ramassées sur le web (écoute).',
        'L’écoute du web (étape 1).',
        'Cycles d’écoute, preuves des business.',
        'excerpt borné.',
    ),
    'mc_sessions': (
        'Sessions owner (cookie). Pas du métier.',
        'Login MC.',
        'Auth des API.',
        'token_hash + expires_at.',
    ),
    'runtime_flags': (
        'Interrupteurs à chaud. Aujourd’hui : Serge arrêté en entier.',
        'Coupe-circuit « Serge » de la page En direct.',
        'Les deux files (elles ne prennent plus de tâche).',
        'name + expires_at + reason.',
    ),
    'pipeline_steps': (
        'Les 8 étapes de la chaîne : en marche ou coupée.',
        'Semence au boot ; toi via la carte Live.',
        'Les files : une étape coupée laisse ses tâches attendre.',
        'enabled + rang (l’ordre de la chaîne).',
    ),
    'tools': (
        'Les outils : une capacité réglée pour un usage précis.',
        'pipeline.yaml au départ.',
        'invocation_tools, fiches outil.',
        'capability_id ; montre_partout = donné à toutes les invocations.',
    ),
    'tool_db_tables': (
        'Tables accessibles par un tool db_read.',
        'Catalogue DB, sans SQL libre.',
        'Query builder et schémas OpenAI.',
        'Une ligne par table autorisée.',
    ),
    'tool_db_columns': (
        'Colonnes retournables par un tool db_read.',
        'Catalogue DB, sans SQL libre.',
        'Query builder et schémas OpenAI.',
        'Le LLM ne peut choisir que ces colonnes.',
    ),
    'tool_db_filters': (
        'Filtres de lignes structurés d’un tool db_read.',
        'Catalogue DB.',
        'Query builder.',
        'Valeur fixe, paramètre déclaré ou enum persistée.',
    ),
    'tool_db_filter_values': (
        'Valeurs autorisées des filtres enum.',
        'Catalogue DB.',
        'Query builder.',
        'Aucun WHERE libre.',
    ),
    'tool_db_joins': (
        'Jointures toujours faites par un outil de lecture.',
        'pipeline.yaml au départ.',
        'Query builder.',
        'Exemple : les pages d’un cycle avec leur titre et leur texte.',
    ),
    'tool_db_params': (
        'Paramètres dynamiques déclarés par un tool db_read.',
        'Catalogue DB.',
        'Query builder et schémas OpenAI.',
        'Type, obligation et défaut sont scalaires.',
    ),
    'tool_db_param_enums': (
        'Enums des paramètres dynamiques DB.',
        'Catalogue DB.',
        'Query builder et schémas OpenAI.',
        'Valeurs et libellés séparés, sans JSON.',
    ),
    'listen_cycles': (
        'Cycles de recherche business avec cibles explicites et guide owner.',
        'L’invocation qui ouvre un cycle.',
        'Invocations de l’étape 1 et onglet Écoute.',
        'Le guide et les paramètres sont historisés.',
    ),
    'venture_sources': (
        'Pages qui prouvent le besoin derrière un business.',
        'Étape 1, à l’écriture des business trouvés.',
        'Fiche business, Mission Control.',
        'Une ligne par business, page et cycle.',
    ),
    'canaux': (
        'Moyens d’écrire vers l’extérieur (e-mail, voix).',
        'Semence git + SHA du fichier d’envoi.',
        'Fiches MC.',
        'etat branche/prevu. doc_md = texte de la fiche.',
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
