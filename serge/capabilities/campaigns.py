#!/usr/bin/env python3
"""Les capacités des campagnes : démarrer, suivre, ajouter un prospect,
mesurer un test, appliquer le choix du principal, enregistrer une vente.
"""

from __future__ import annotations

from serge.capabilities.model import Capability, Param

CAMPAIGNS: tuple[Capability, ...] = (
    Capability(
        'start_campaign',
        'Démarrer une campagne',
        'Démarre une campagne prête : vérifie que son canal est branché,'
        ' fixe son volume d’après les réglages de l’invocation (un jeu par'
        ' canal : <canal>_test pour un test léger, <canal>_semaine et'
        ' <canal>_total pour la prospection lourde) et, pour un test, sa'
        ' fin prévue (la durée du plan, au plus duree_max_jours). Rend ce'
        ' que les règles d’écriture rangent. Une campagne sur un canal non'
        ' branché est annulée, avec la raison.',
        'serge/campaigns/start.py',
        (Param('campaign_id', 'text', True, 'La campagne à démarrer.'),),
    ),
    Capability(
        'follow_campaign',
        'Suivre une campagne',
        'Regarde une campagne en cours et rend ce qu’il faut faire : la'
        ' clore (elle a son compte, plus rien n’attend et rien n’est parti'
        ' depuis jours_sans_envoi jours ; ou la durée de son test est'
        ' atteinte ; ou elle ne trouve plus de prospects), lui chercher des'
        ' prospects (il lui en manque et Serge a moins de jours_d_avance'
        ' jours d’envois d’avance), ou attendre.',
        'serge/campaigns/follow.py',
        (Param('campaign_id', 'text', True, 'La campagne à suivre.'),),
    ),
    Capability(
        'add_prospect',
        'Ajouter un prospect',
        'Ajoute une personne à une campagne : sa fiche, son adresse sur le'
        ' canal de la campagne, et un premier message à rédiger. Vérifie'
        ' tout de suite et dit pourquoi elle refuse : adresse générique'
        ' (contact@, info@…), adresse mal formée, domaine qui ne reçoit pas'
        ' d’e-mails, personne déjà contactée pour ce business ou'
        ' désinscrite, campagne qui a son compte.',
        'serge/campaigns/prospect.py',
        (
            Param('campaign_id', 'text', True, 'La campagne.'),
            Param('name', 'text', True, 'Son prénom et son nom.'),
            Param('company', 'text', False, 'Son entreprise.'),
            Param('role', 'text', False, 'Son rôle (gérante, par exemple).'),
            Param('why', 'text', False, 'Pourquoi cette personne est visée.'),
            Param(
                'address',
                'text',
                True,
                'Son adresse directe sur le canal de la campagne : un'
                ' e-mail à son nom, un numéro au format +33…, ou'
                ' l’adresse de son profil sur le réseau'
                ' (https://www.linkedin.com/in/…).',
            ),
            Param(
                'source_url',
                'text',
                True,
                'La page où cette adresse a été trouvée.',
            ),
        ),
    ),
    Capability(
        'measure_test',
        'Mesurer un test',
        'Compte ce qu’a donné le test léger d’un business (prospects'
        ' contactés par canal, réactions, points, dépense, points par euro)'
        ' et le juge avec les seuils réglés sur l’invocation (prospects_min,'
        ' points_min, points_par_euro_min) : retenu, ou non, avec la raison.',
        'serge/campaigns/measure.py',
        (Param('venture_id', 'text', True, 'Le business testé.'),),
    ),
    Capability(
        'apply_principal',
        'Appliquer le choix du principal',
        'Lit la réponse au ticket « Choix du principal » et rend le business'
        ' choisi (la proposition validée, un autre nommé dans la réponse, ou'
        ' aucun) et les autres tests retenus, à mettre de côté. Un nom qui'
        ' ne désigne aucun business qui attend ne change rien.',
        'serge/campaigns/principal.py',
        (
            Param('choice_id', 'text', True, 'La proposition.'),
            Param('acte', 'text', True, 'valider, choisir_autre ou aucun.'),
            Param('texte', 'text', False, 'Le nom du business voulu.'),
        ),
    ),
    Capability(
        'record_sale',
        'Enregistrer une vente',
        'Relie un paiement arrivé à un contact du business, par l’e-mail du'
        ' payeur, et le passe à « client » ; un acheteur inconnu devient un'
        ' contact entrant. Dit si c’est la première vente du business.',
        'serge/campaigns/sale.py',
        (Param('transaction_id', 'text', True, 'Le paiement arrivé.'),),
    ),
)
