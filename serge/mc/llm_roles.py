#!/usr/bin/env python3
"""Textes simples des jugements LLM : rôle, flux, lectures autorisées."""

from __future__ import annotations

# role, entre, sort, vers, forme
ROLES: dict[str, tuple[str, str, str, str, str]] = {
    'cluster_demand': (
        'Serge lit ce que des inconnus ont écrit sur internet'
        ' (forums, fils RSS… aujourd’hui surtout des flux, pas encore'
        ' LinkedIn en direct). Il met ensemble les gens qui veulent'
        ' à peu près la même chose. Ça sert à trouver une idée de'
        ' business assez répétée pour valoir un petit essai — pas'
        ' une intuition sortie de nulle part.',
        'Les pages vraiment lues (titre, extrait, source), plus une'
        ' grille de notation, plus un moule pour nommer un paquet,'
        ' plus un échantillon des phrases des gens. Les leçons déjà'
        ' apprises et la mémoire peuvent s’ajouter s’il demande plus.',
        'Des paquets de demandes qui se ressemblent. Chaque paquet'
        ' a un nom en français (ex. « indépendants qui veulent un'
        ' timer pour facturer ») et une note : on en voit beaucoup,'
        ' ou presque pas.',
        'L’étape suivante : écrire une idée de business à tester'
        ' sur un petit groupe.',
        'Une liste de paquets : nom, note de volume, quelques extraits.',
    ),
    'draft_hypothesis_smoke': (
        'Écrit l’idée de business à tester tout de suite : quoi vendre,'
        ' à quel prix de départ, par quel canal (e-mail, appel…), à'
        ' combien de personnes, pendant combien de jours. Sans ça,'
        ' on ne saura pas si l’essai a marché.',
        'Les paquets de demandes, tes envies écrites (SERGE.md),'
        ' les règles du jeu (combien c’est « assez »).',
        'Une fiche d’idée courte, prête à essayer.',
        'Toi : tu valides ou tu corriges. Puis Serge commence l’essai.',
        'Fiche : offre, prix de départ, canal, nombre de gens, durée.',
    ),
    'draft_hypothesis_full': (
        'Même idée de business, mais après le premier essai : on a'
        ' des vrais chiffres. On décide si on agrandit l’essai.'
        ' Si on ne peut pas encore encaisser l’argent, on s’arrête.',
        'Résultats du petit essai, leçons, état de la caisse.',
        'Une fiche d’idée plus solide, à valider.',
        'Toi : ticket de décision avant d’agrandir.',
        'Fiche + « oui / non / conditions ».',
    ),
    'resume_test': (
        'Raconte l’essai avec les vrais chiffres. Il n’a pas le droit'
        ' d’inventer un nombre : soit c’est dans la base, soit il se tait.',
        'Compteurs (combien de gens touchés, réponses, oui) et objections.',
        'Un résumé qu’un humain de 18 ans peut lire.',
        'Toi, et la mémoire (quoi retenir).',
        'Quelques phrases + les chiffres copiés de la base.',
    ),
    'plan_scale': (
        'Si l’essai a marché : comment faire plus, sans casser la'
        ' machine ni le budget. S’il propose trop gros, ça devient'
        ' une question pour toi — Serge n’emballe pas tout seul.',
        'Résultats, argent restant, recettes qui ont déjà marché,'
        ' erreurs déjà payées.',
        'Un plan par étapes, avec des limites.',
        'Toi si ça dépasse les limites, sinon info seulement.',
        'Plan : quoi, combien, pourquoi, jusqu’où.',
    ),
    'options_pivot': (
        'Si l’essai a perdu : trois autres idées, vraiment différentes.'
        ' Interdit de proposer « on refait pareil ».',
        'Ce que les gens ont reproché, leçons des échecs.',
        'Trois pistes + ce qui change par rapport à avant.',
        'Toi : tu en choisis une (ou aucune).',
        'Trois fiches d’idée, chacune avec un écart visible.',
    ),
    'qualify_prospect': (
        'Regarde une personne et dit : « elle est dans la cible de'
        ' cette idée de business, ou on perd notre temps ? » Un non'
        ' ici évite des e-mails inutiles.',
        'La fiche de la personne + les critères de l’idée en cours.',
        'Oui / non, avec une raison simple.',
        'La suite : on lui écrit, ou on passe à quelqu’un d’autre.',
        'Décision + phrase de motif.',
    ),
    'fill_slots': (
        'Remplit les cases vides d’une fiche (besoin, créneau, ville)'
        ' à partir de ce que la personne a déjà dit. Interdit d’inventer.',
        'La conversation + les cases encore vides.',
        'Des propositions de cases, chacune avec d’où ça vient.',
        'La fiche de la personne, parfois une question pour toi.',
        'Liste : nom de case, valeur, source.',
    ),
    'score_lead_departage': (
        'Deux personnes se valent : laquelle relancer en premier ?'
        ' Il s’appuie sur ce qui s’est vraiment passé, pas sur un feeling.',
        'Les deux fiches + l’historique des messages.',
        'La personne retenue + pourquoi.',
        'La file : qui est le prochain message.',
        'Gagnant + motif.',
    ),
    'write_followup': (
        'Écrit un message de relance, calé sur le dernier signal :'
        ' silence, doute, curiosité. Il respecte les heures où on a'
        ' le droit d’écrire.',
        'Le fil, les leçons de relance, les horaires autorisés.',
        'Un brouillon de message.',
        'L’e-mail ou Discord, après les gardes (pas deux fois, pas trop tard).',
        'Texte + canal.',
    ),
    'voice_script': (
        'Prépare ce qu’on va dire au téléphone : bonjour, question,'
        ' comment terminer. Pas d’improvisation hors des règles FR.',
        'La personne, l’offre, les règles voix (consentement, horaires).',
        'Un script d’appel.',
        'L’appel sortant.',
        'Ouverture, questions, fin.',
    ),
    'voice_dialog': (
        'Pendant l’appel : la prochaine phrase, courte, dans le script'
        ' et seulement si la personne a accepté d’être appelée.',
        'Ce qui vient d’être dit + le script.',
        'Une réplique.',
        'Le téléphone, tout de suite.',
        'Une phrase, durée limitée.',
    ),
    'summarize_thread': (
        'Résume une conversation trop longue pour qu’on n’ait pas à'
        ' tout relire. Les messages bruts restent dans le journal.',
        'Les messages échangés.',
        'Un résumé daté.',
        'Toi, et le prochain jugement qui a besoin du fil.',
        'Un paragraphe + numéro de version.',
    ),
    'classify_reply': (
        'Lit une réponse reçue et dit ce que c’est : une ouverture'
        ' (« oui, envoyez »), une objection (« trop cher »), ou autre'
        ' chose. Ça décide la suite : devis, relance, ou un humain.',
        'Le texte reçu + ce qu’on a déjà appris sur ce genre de phrases.',
        'Une classe, une confiance, une suite proposée.',
        'La conversation : devis, relance, ou ticket pour toi.',
        'Classe + confiance + suite.',
    ),
    'extract_meeting': (
        'Cherche un rendez-vous ou un créneau dans un message.'
        ' S’il n’y en a pas, il le dit clairement.',
        'Le message reçu.',
        'Une date/heure, ou rien.',
        'Un ticket « rendez-vous » si c’est solide.',
        'Quand, ou vide.',
    ),
    'reply_intent': (
        'Répond à quelqu’un qui veut clairement acheter (« oui »,'
        ' « combien », « envoyez le devis ») sans promettre un prix'
        ' inventé.',
        'Le signal d’achat + l’offre + les prix autorisés.',
        'Une réponse + le prochain geste (devis, appel, pause).',
        'Le même canal que la conversation.',
        'Texte + geste.',
    ),
    'review_other': (
        'Relit les messages mis dans « autre » : vrai bruit, ou un'
        ' oui mal formulé qu’on allait jeter ?',
        'Les messages classés « autre ».',
        'Garder, jeter, ou reclasser.',
        'La file des réponses.',
        'Décision + motif.',
    ),
    'score_call': (
        'Après un appel : utile ou pas, suite ou pas. Pour améliorer'
        ' les prochains appels, pas pour se faire plaisir.',
        'Compte-rendu d’appel + extraits.',
        'Une note + des raisons.',
        'La qualité voix et les leçons.',
        'Note + motifs.',
    ),
    'draft_price': (
        'Propose un prix, seulement entre le minimum et le maximum'
        ' autorisés. Hors fourchette : ça ne part pas.',
        'L’offre, les leçons sur les prix, les bornes.',
        'Un montant + pourquoi ce montant.',
        'Le devis (pas encore payé).',
        'Euros + motif.',
    ),
    'judge_allocator': (
        'Où mettre le prochain euro : plus d’e-mails, un appel, ou'
        ' on pause. Il justifie. Il ne dépense pas tout seul.',
        'Budgets, santé des comptes, résultats des essais.',
        'Une reco : canal, combien, pourquoi.',
        'Toi si ça sort des limites.',
        'Canal + enveloppe + motif.',
    ),
    'build_artifact': (
        'Fabrique un livrable (page, PDF, texte) à partir de l’idée'
        ' de business. On garde une version et une empreinte.',
        'L’offre + les moules de fabrication.',
        'Un fichier (chemin + empreinte).',
        'La relecture, puis l’envoi.',
        'Type, chemin, version.',
    ),
    'review_build': (
        'Relit le livrable avant envoi : promesse, prix, ton.'
        ' Une erreur ici peut brûler un compte (e-mail, réseau).',
        'Le livrable + une checklist.',
        'OK, ou une liste de retouches.',
        'On corrige, ou on envoie.',
        'Avis + retouches.',
    ),
    'summarize_build_debt': (
        'Liste ce qu’il reste à fabriquer pour que l’argent puisse'
        ' vraiment rentrer. Visible, pas honteux.',
        'Livrables déjà faits + tickets ouverts.',
        'Une liste dans l’ordre.',
        'Toi, et la file de fabrication.',
        'Liste priorisée.',
    ),
    'consolidate': (
        'Transforme « ce qui s’est passé » en une leçon proposée.'
        ' Ce n’est pas encore une vérité : ça attend une confirmation.',
        'Le journal + les leçons déjà là.',
        'Une phrase à garder, modifier ou jeter.',
        'La mémoire (table des leçons).',
        'Énoncé + d’où ça vient + confiance.',
    ),
    'edit_serge_md': (
        'Propose une modification de tes envies écrites (SERGE.md).'
        ' Jamais en silence : tu vois le avant / après.',
        'Le texte actuel + ce que tu viens de demander.',
        'Un diff.',
        'Toi : tu acceptes ou non.',
        'Patch texte.',
    ),
    'render_context_fr': (
        'Traduit un truc technique en français simple, pour toi ou'
        ' pour un appel. Pas de jargon brut.',
        'L’objet ou l’événement source.',
        'Un court paragraphe.',
        'L’écran, la voix, ou Discord.',
        'Texte court.',
    ),
    'classify_owner_intent': (
        'Lit ce que toi tu as dit et classe : un ordre, une question,'
        ' ou juste une info. Évite qu’un « stop » parte en relance.',
        'Ton message.',
        'Une intention + une action proposée.',
        'Les règles, ou un ticket « ordre ».',
        'Classe + action.',
    ),
    'judge_consequence': (
        'Avant un geste qu’on ne peut pas défaire : quelles suites,'
        ' dans quelles limites. Il juge, il n’exécute pas.',
        'Le geste proposé + les règles.',
        'Autoriser, refuser, ou poser des conditions.',
        'Une garde, parfois un ticket pour toi.',
        'Décision + conditions.',
    ),
    'install_guide': (
        'Aide à installer Serge (dossiers, secrets, premiers gestes).'
        ' Il explique. Il ne touche à rien tout seul.',
        'Où on en est dans l’install.',
        'La prochaine étape humaine.',
        'Toi, devant le terminal.',
        'Étape + commande sûre.',
    ),
}

MATERIEL: dict[str, tuple[str, str]] = {
    'rubric_volume_intensite_recurrence_willingness': (
        'Grille de notation des demandes',
        'Quatre questions toutes bêtes, pour chaque paquet :'
        ' on en voit beaucoup ? (volume) les gens ont l’air'
        ' embêtés pour de vrai ? (intensité) ça revient souvent ?'
        ' (récurrence) est-ce qu’ils paieraient ? (volonté).'
        ' Ce n’est pas un code secret : c’est un barème.',
    ),
    'template_cluster': (
        'Moule pour nommer un paquet',
        'La recette pour écrire le nom et le résumé d’un paquet'
        ' de demandes. Sans moule, le modèle invente un titre'
        ' différent à chaque fois et on ne peut plus comparer.',
    ),
    'verbatims_echantillonnes_3000t': (
        'Phrases vraies des gens (échantillon)',
        'Un morceau des textes originaux (commentaires, posts).'
        ' « 3000 t » veut dire : on ne lui donne pas tout le web,'
        ' juste assez pour juger — pour limiter le coût et le bruit.',
    ),
    'template_smoke': (
        'Moule de la petite idée à tester',
        'Les cases à remplir : quoi vendre, prix de départ, canal,'
        ' combien de gens, combien de jours.',
    ),
    'template_full': (
        'Moule de l’idée après le premier essai',
        'Même chose, plus les chiffres du premier essai et'
        ' « est-ce qu’on peut encaisser ? ».',
    ),
    'template_plan': ('Moule du plan pour grandir', 'Les sections d’un plan : où, combien, limites.'),
    'template_option_x3': (
        'Moule des trois autres idées',
        'Oblige à écrire trois pistes vraiment différentes.',
    ),
    'template_resume': (
        'Moule du résumé d’essai',
        'Un canevas : chiffres d’abord, blabla ensuite. Pas l’inverse.',
    ),
    'serge_md': (
        'Tes envies écrites',
        'Le petit texte versionné où tu dis qui tu es et ce que'
        ' Serge a le droit de poursuivre. C’est SERGE.md.',
    ),
    'seuils_A': (
        'Ce qui compte comme « ça a marché »',
        'Les nombres décidés à l’avance : par exemple « au moins'
        ' X oui sur N personnes ». Sans ça, on triche après coup.',
    ),
    'policy': (
        'Les règles chiffrées',
        'Les nombres qui autorisent ou refusent un acte : budget'
        ' du jour, e-mails max, heures d’appel…',
    ),
    'gate_collect': (
        'La porte de la caisse',
        'Est-ce qu’on peut vraiment prendre l’argent (Stripe, devis)'
        ' ou on vend du vent ?',
    ),
    'budget_restant': (
        'L’argent encore dépensable aujourd’hui',
        'Ce qu’il reste dans l’enveloppe du jour (modèle + e-mails).',
    ),
    'ecoute_top5_1200t': (
        'Les 5 pages les plus parlantes',
        'Un petit tas des lectures les plus utiles, pas tout le web.',
    ),
    'lecons_hypothesis_top3_800t': (
        'Leçons déjà apprises sur les idées',
        'Ce qu’on a déjà compris en se trompant (ou en réussissant)'
        ' sur les idées de business.',
    ),
    'lecons_full_test_top3_800t': (
        'Leçons des essais plus larges',
        'Pareil, mais après avoir touché plus de monde.',
    ),
    'lecons_pivot_top3_800t': (
        'Leçons des changements de cap',
        'Ce qui a déjà foiré quand on a changé d’idée.',
    ),
    'lecons_candidates_400t': (
        'Leçons pas encore confirmées',
        'Des phrases qu’on croit vraies, en attente de ton « ok ».',
    ),
    'objections_top10_1500t': (
        'Ce que les gens reprochent le plus',
        'Les 10 critiques les plus fréquentes (prix, timing, confiance).',
    ),
    'top_objections_800t': (
        'Objections de l’essai en cours',
        'Ce que les gens de CET essai ont dit en face.',
    ),
    'compteurs_verdict_preuves_800t': (
        'Les compteurs de l’essai',
        'Combien de gens touchés, de réponses, de oui — et les preuves.',
    ),
    'resultats_smoke_2000t': (
        'Chiffres du petit essai',
        'Le bilan chiffré du premier test, borné pour ne pas tout noyer.',
    ),
    'resultats_full': (
        'Chiffres de l’essai plus large',
        'Le bilan une fois qu’on a touché plus de monde.',
    ),
    'etat_collect_300t': (
        'État de la caisse',
        'Devis, Stripe, abonnements : est-ce que l’argent peut entrer ?',
    ),
    'playbooks_scale_top3_1000t': (
        'Recettes pour grandir',
        'Des procédures qui ont déjà marché sans tout casser.',
    ),
    'taxonomie_2exemples_1200t': (
        'Exemples de classes de réponses',
        'Deux ou trois exemples : voilà un « oui », voilà un « trop cher »,'
        ' voilà un hors-sujet. Pour que le modèle range pareil.',
    ),
    'message_2000t_tronque': (
        'Le message reçu (coupé si trop long)',
        'Le texte de la personne, limité pour ne pas tout avaler.',
    ),
    'contexte_micro_300t': (
        'Tout petit contexte autour du message',
        'Qui a écrit, à propos de quelle idée, dernière phrase utile.',
    ),
    'playbooks_domaine_600t': (
        'Recettes du métier',
        'Ce qui marche dans ce domaine (artisans, freelances…).',
    ),
    'pitfalls_scale_top3_800t': (
        'Pièges déjà payés',
        'Les erreurs qui ont déjà coûté de l’argent en grandissant.',
    ),
    'standing_500t': (
        'Santé des comptes (e-mail, réseaux)',
        'Avertissements, pauses, risque de se faire fermer un compte.',
    ),
    'benchmarks_canal_400t': (
        'Repères par canal',
        '« Un e-mail, en moyenne, ça donne quoi ? » pour ne pas rêver.',
    ),
    'etats_sortie': (
        'Fins d’essai autorisées',
        'Les issues propres : on arrête, on agrandit, on change d’idée.',
    ),
    'secrets': ('Interdit : secrets', 'Mots de passe, jetons, clés. Jamais dans un jugement.'),
    'pii_tiers': (
        'Interdit : vies privées des autres',
        'Pas le droit de recracher des données perso de tiers.',
    ),
    'autres_ventures': (
        'Interdit : mélanger les idées',
        'On ne pique pas les infos d’une autre idée de business.',
    ),
    'montants_non_catalogue': ('Interdit : un prix hors liste', 'Pas de tarif inventé.'),
    'montants_inventes': ('Interdit : un prix inventé', 'Même idée : le prix vient du catalogue.'),
    'engagements_contractuels': (
        'Interdit : promettre un contrat',
        'Serge ne signe pas à ta place.',
    ),
    'refaire_pareil': (
        'Interdit : refaire le même essai perdu',
        'Si ça n’a pas marché, on change quelque chose de visible.',
    ),
    'pii_non_anonymisee': (
        'Interdit : noms et e-mails en clair',
        'On anonymise avant de faire lire au modèle.',
    ),
    'pii_verbatims_anonymises': (
        'Interdit : phrases trop personnelles',
        'Même les extraits du web : on enlève ce qui identifie quelqu’un.',
    ),
    'system_prompt_guide': (
        'Consigne du guide d’install',
        'Le texte fixe qui dit au modèle : explique, ne touche à rien.',
    ),
    'etape_courante': ('Étape d’install en cours', 'Où tu en es dans l’installation.'),
    'resume_non_secret': (
        'Résumé sans secret',
        'Un état de l’install, sans mot de passe.',
    ),
}


def role_de(nom: str) -> tuple[str, str, str, str, str]:
    """Retourne (rôle, entre, sort, vers, forme)."""
    found = ROLES.get(nom)
    if found:
        return found
    titre = nom.replace('_', ' ')
    return (
        f'Un jugement « {titre} » : il lit un dossier borné, décide,'
        ' et rend la main. Rien n’est dépensé sans les règles.',
        'Le dossier prévu pour ce jugement (lectures + éventuellement recherche).',
        'Une décision structurée, pas un roman.',
        'L’étape suivante du travail (message, ticket, ou toi).',
        'Un petit objet clair (oui/non, texte, liste).',
    )


def titre_materiel(cle: str) -> str:
    """Titre humain d’une lecture autorisée."""
    if cle in MATERIEL:
        return MATERIEL[cle][0]
    brut = cle
    if brut.endswith('t') and '_' in brut:
        tete, _, queue = brut.rpartition('_')
        if queue[:-1].isdigit():
            brut = tete
    mot = brut.replace('_', ' ').strip()
    return mot[:1].upper() + mot[1:] if mot else cle


def texte_materiel(cle: str) -> str:
    """Explication d’une lecture autorisée."""
    if cle in MATERIEL:
        return MATERIEL[cle][1]
    return (
        f'« {titre_materiel(cle)} » : un morceau du dossier prévu'
        ' pour ce jugement. On ne lui donne que ça, pour limiter'
        ' le coût et éviter de tout lui verser.'
    )
