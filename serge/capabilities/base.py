#!/usr/bin/env python3
"""Les capacités de base : lire et écrire la base, chercher sur le web et
dans la mémoire, lire une page ou un flux, demander une capacité, passer
à la suite.
"""

from __future__ import annotations

from serge.capabilities.model import Capability, Param

BASE: tuple[Capability, ...] = (
    Capability(
        'db_read',
        'Lire la base',
        'Lit des lignes de la base à travers un outil de lecture. Chaque'
        ' outil déclare en base les tables, colonnes, filtres et jointures'
        ' qu’il a le droit de lire ; le modèle n’écrit jamais de SQL.',
        'serge/db/query_builder.py',
        (Param('tool_id', 'text', True, 'L’outil de lecture à utiliser.'),),
    ),
    Capability(
        'web_search',
        'Chercher sur le web',
        'Cherche une question sur le web et rend quelques résultats : titre,'
        ' adresse et extrait.',
        'serge/listen/web.py',
        (
            Param('query', 'text', True, 'La recherche à faire.'),
            Param('limit', 'number', False, 'Le nombre de résultats.'),
        ),
    ),
    Capability(
        'memory_search',
        'Chercher dans la mémoire',
        'Cherche des mots dans les leçons, les événements et les tickets de'
        ' Serge, et rend quelques extraits. Lecture seule.',
        'serge/memory/search.py',
        (
            Param('query', 'text', True, 'Les mots à chercher.'),
            Param('types', 'list', False, 'Les sortes de souvenirs visées.'),
            Param('top_k', 'number', False, 'Le nombre d’extraits.'),
        ),
    ),
    Capability(
        'echo',
        'Rendre ses paramètres',
        'Rend tels quels les paramètres qu’on lui donne. Sert aux invocations'
        ' sans LLM qui ne font qu’écrire en base ce qu’on leur transmet, par'
        ' exemple ouvrir un cycle avec le texte de guidage.',
        'serge/interpreter/tools.py',
    ),
    Capability(
        'db_write',
        'Écrire dans la base',
        'Écrit la réponse d’une invocation en base, selon ses règles'
        ' d’écriture : la table, ajouter ou modifier, quelle colonne reçoit'
        ' quel champ. Applique les protections réglées en base (tables'
        ' autorisées, changements de statut permis, doublons) et note chaque'
        ' écriture et chaque refus au journal. Toutes les invocations s’en'
        ' servent ; on ne la donne pas comme outil.',
        'serge/interpreter/writer.py',
    ),
    Capability(
        'seen_table_read',
        'Lire les tables que je vois',
        'Lit toutes les colonnes lisibles d’une table que l’invocation voit'
        ' déjà en version courte : une ligne par son numéro, ou toutes les'
        ' lignes avec un filtre simple, page par page. Les tables permises'
        ' sont calculées à chaque appel à partir de l’invocation : celles où'
        ' elle écrit, plus ou moins les ajustements réglés dans Mission'
        ' Control. Les colonnes lisibles sont réglées une fois par table.',
        'serge/interpreter/seen.py',
        (
            Param('table', 'text', True, 'La table à lire.'),
            Param(
                'column',
                'text',
                False,
                'Une colonne lisible pour filtrer (id pour une seule ligne).',
            ),
            Param(
                'value', 'text', False, 'La valeur que doit avoir la colonne.'
            ),
            Param('page', 'number', False, 'La page (1 pour commencer).'),
        ),
    ),
    Capability(
        'row_history',
        'Lire l’historique d’une ligne',
        'Rend ce qui est arrivé à une ligne que l’invocation voit (ce qu’elle'
        ' traite, ou une table à comparer) : ses derniers événements dans le'
        ' journal, du plus récent au plus ancien, page par page.',
        'serge/interpreter/seen.py',
        (
            Param('table', 'text', True, 'La table de la ligne.'),
            Param('id', 'text', True, 'Le numéro de la ligne.'),
            Param('page', 'number', False, 'La page (1 pour commencer).'),
        ),
    ),
    Capability(
        'page_read',
        'Lire une page',
        'Lit une page web publique par une simple requête, sans navigateur,'
        ' et rend ses premières lignes : une ligne est un titre, un'
        ' paragraphe ou un élément de liste. Réglée par un nombre de lignes'
        ' (un aperçu pour trier, la page entière pour formuler). Avec une'
        ' table et un numéro, ne lit qu’une page déjà en base. Refuse les'
        ' adresses du serveur et des réseaux privés.',
        'serge/listen/page.py',
        (
            Param('url', 'text', False, 'L’adresse de la page.'),
            Param('table', 'text', False, 'La table des pages en base.'),
            Param('id', 'text', False, 'Le numéro de la page en base.'),
            Param(
                'max_lines',
                'number',
                False,
                'Les lignes rendues (0 : toutes).',
            ),
        ),
    ),
    Capability(
        'rss_read',
        'Lire un flux RSS',
        'Lit un flux RSS ou Atom et rend ses pages : adresse, titre, date et'
        ' un aperçu de quelques lignes tiré du résumé du flux.',
        'serge/listen/collectors.py',
        (
            Param('url', 'text', True, 'L’adresse du flux.'),
            Param('max_items', 'number', False, 'Les pages lues au plus.'),
            Param('max_lines', 'number', False, 'Les lignes de l’aperçu.'),
        ),
    ),
    Capability(
        'request_capability',
        'Demander une nouvelle capacité',
        'Ouvre une demande à Julien quand il manque à Serge un outil ou un'
        ' accès pour faire ce qu’on lui demande.',
        'serge/demande_capacite.py',
        (
            Param('need', 'text', True, 'Ce qui manque, en une phrase.'),
            Param('context', 'text', False, 'Pourquoi on en a besoin.'),
        ),
    ),
    Capability(
        'pass_link',
        'Passer à la suite',
        'Fait partir un passage qui attendait un clic (un lien réglé à la'
        ' main), comme le bouton « Passer à la suite » de Mission Control.',
        'serge/interpreter/flow.py',
        (Param('passage', 'text', True, 'Le passage : « lien:source ».'),),
    ),
    Capability(
        'next_round',
        'Compter les tours',
        'Compte les tours d’une boucle entre invocations (critiquer puis'
        ' corriger un plan, construire puis relire) : rend « encore » et le'
        ' tour suivant tant que le tour est sous le maximum, sinon « fini ».'
        ' Le tour vient de la tâche, le maximum d’un réglage.',
        'serge/interpreter/tools.py',
        (
            Param('round', 'number', True, 'Le tour qui vient de finir.'),
            Param('max', 'number', True, 'Le nombre de tours permis.'),
        ),
    ),
)
