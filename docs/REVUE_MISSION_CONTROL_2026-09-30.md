# Revue Mission Control — 30 septembre 2026

La revue a identifié 32 défauts, dont 8 prioritaires (P1), dans les
parcours disponibles. Les corrections couvrent les sessions, les décisions,
les règles, les brouillons, la navigation et la présentation sur mobile.
La documentation de référence reste [MISSION_CONTROL.md](MISSION_CONTROL.md).
Un défaut supplémentaire du hook de publication a été reproduit et
corrigé pendant la validation : 33 corrections recensées au total.

## Version examinée et changements de main

La première revue portait sur `7fdeed1`. Le worktree a ensuite été avancé
à `ce70459`, puis à `88a058d`, dernière version de main récupérée pendant
la validation. Entre la première revue et cette version : 10 PR fusionnées,
121 fichiers modifiés, 11 986 lignes ajoutées et 1 566 supprimées.

| PR | Changements examinés |
|---|---|
| #32, #33 | Suite du lot 6 : réglages et quotas dans Policy, boutons d'Écoute, jours en français, fiches de tables et de liens, page Pipeline. |
| #34 | Lot 7 : cycle d'écoute décrit en base, tri des pages, formulation et choix de business, conditions et quotas. |
| #35 | Annulation des tâches d'invocations retirées, reprises d'appels LLM et journal des passages. |
| #36 | Bornes sur les résultats d'outils, pages lues, tailles et doublons. |
| #37 | Consignes agents et lecture de la charte. |
| #38 | Cache de l'historique des boucles d'outils Anthropic. |
| #39 | Dépenses LLM au coût réel, plafonds pendant l'exécution, jetons sans coût identifié. |
| #40 | Choix du modèle par niveau, catalogue OpenRouter, prix et recommandations sur Pipeline. |
| #41 | Coût des passages LLM : ne plus annoncer zéro quand le coût manque. |

Les nouvelles fonctions ont été parcourues au navigateur et leurs API ont
été vérifiées. Le coût réel, les reprises LLM et le cycle d'écoute sont
également couverts par les scénarios du dépôt.

## Méthode

Serveur HTTP Mission Control réel, SQLite temporaire et Chromium Playwright.
Les données comprennent un ticket urgent, des propositions de leçons,
une campagne active et des abonnements récents et anciens. Le catalogue
OpenRouter est remplacé par une réponse fixe dans les tests navigateur.
Les envois, appels téléphoniques et paiements sont simulés.

Les 12 pages ont été capturées en 1440 × 1000, 1280 × 800 et 390 × 844 :
En direct, Système, Cerveau, Décisions, Mémoire, Policy, Économie, Voix,
Health, Identité, Écoute et Pipeline. Les fiches, modales, accès clavier,
erreurs réseau et changements de route ont été examinés séparément.

Les captures finales donnent 36 vues, aucune erreur JavaScript, aucun
débordement horizontal de la page, aucun champ sans nom accessible et
aucun chevauchement entre les nœuds de la carte. Les tableaux longs
conservent leur défilement horizontal dans leur propre cadre.

## Défauts et corrections

Les numéros 1 à 24 viennent de la première revue. Ils ont été réexaminés
sur main par lecture des changements et reproduction des parcours
concernés. Les numéros 25 à 32 concernent les ajouts récents. P1 désigne
un accès indu, une règle contournée ou un parcours bloquant ; P2 désigne
une information erronée ou une interaction dégradée.

| N° | Priorité | Défaut | Correction |
|---|---|---|---|
| 1 | P1 | Accès aux enregistrements sans session via une signature utilisant une clé publique dans le code. | Audio réservé à l'authentification propriétaire ; suppression des liens signés MC. |
| 2 | P1 | Enregistrer les jours supprimait le mardi. | Mardi utilise `tue`, lundi `mon`, avec libellés français inchangés. |
| 3 | P1 | Une taille d'essai incohérente pouvait rendre les lectures suivantes inutilisables. | Validation partagée des entiers et de leurs relations avant sauvegarde ; refus des nombres non finis. |
| 4 | P1 | Modifier toute la policy contournait le verrou des essais en cours. | Même verrou sur l'édition générale et l'édition dédiée. |
| 5 | P1 | Des types de tickets n'avaient aucun de leurs boutons disponibles. | Boutons complets du registre, actes partagés avec Discord, QCM et réponse libre. |
| 6 | P1 | Un flux déjà ouvert continuait après révocation de la session. | Vérification à chaque tick, événement d'expiration puis fermeture. |
| 7 | P1 | Un urgent ancien disparaissait derrière 50 tickets plus récents. | Tous les tickets actifs restent disponibles, complétés des 50 derniers clos. |
| 8 | P2 | Chevauchements dans la carte, aggravés sur mobile. | Grille responsive ; traits calculés depuis les positions réellement affichées. |
| 9 | P2 | Les visites successives d'En direct multipliaient les confirmations. | Retrait des écouteurs à la sortie de page et protection du clic en cours. |
| 10 | P2 | Une fiche lente s'affichait après avoir quitté sa route et fermait le nouveau flux. | Vérification de la route après les opérations asynchrones. |
| 11 | P2 | Un urgent ouvrait une fiche sans action. | Même carte interactive dans Décisions et la fiche complète. |
| 12 | P2 | Le deuxième message d'une discussion échouait et les messages étaient invisibles. | Discussion continue et texte des messages dans l'historique. |
| 13 | P2 | Une proposition de leçon ouvrait un identifiant de leçon inexistant. | Les propositions ouvrent leur ticket ; libellé corrigé. |
| 14 | P2 | Aucune interface pour modifier ou jeter une leçon existante. | Texte intégral et actions de curation dans sa fiche. |
| 15 | P2 | Le MRR dépendait des 20 lignes récentes et oubliait des abonnements actifs. | Agrégation indépendante sur tous les abonnements mensuels actifs. |
| 16 | P2 | Des envois étaient annoncés comme réponses et tous les artifacts comme dette. | Libellés « Derniers envois » et « Derniers livrables », conformes aux données affichées. |
| 17 | P2 | La pastille restait verte après perte de connexion ou déconnexion. | État du flux réel, message d'erreur ou d'expiration ; refus HTTP à l'ouverture également détecté. |
| 18 | P2 | Le guidage saisi dans Écoute était perdu lors d'une mise à jour de quota. | Conservation des champs modifiés et du focus lors du remplacement du formulaire. |
| 19 | P2 | Une saisie Unicode autorisée dépassait la limite de 4 Ko et produisait un mauvais message. | JSON limité à 64 Kio avec réponse 413 explicite ; limite de connexion conservée. |
| 20 | P2 | La commande Policy ne fonctionnait pas depuis une autre page ; nouvelles pages absentes de la palette. | Ouverture directe de la modale et commandes Écoute, Pipeline et Système. |
| 21 | P2 | Système redirigeait vers En direct malgré la page annoncée. | Route Système rétablie, accès depuis la palette et le nœud Mail. |
| 22 | P2 | Champs sans nom accessible, modales sans confinement du focus et focus invisible. | Noms des champs, rôle et titre des modales, cycle Tab, restauration du focus et styles visibles. |
| 23 | P2 | Notifications placées au bas du document, hors écran. | Conteneur fixe partagé, adapté à la largeur du mobile. |
| 24 | P2 | Le statut public annonçait « opérationnel » même arrêté ou en cas d'erreur. | État factuel arrêté, au repos, au travail ou indisponible ; page mise en forme. |
| 25 | P1 | `2.5`, `NaN` ou `Infinity` pouvaient être sauvegardés comme un nombre de résultats puis casser l'invocation. | Réglages de compte limités aux entiers finis ; quotas bornés à la capacité de SQLite. |
| 26 | P2 | Sauver un niveau de modèle effaçait le brouillon d'un autre niveau. | Conservation des brouillons Pipeline, nettoyage des seuls champs sauvegardés. |
| 27 | P2 | Sauver un réglage effaçait la saisie d'un autre réglage. | Même protection des brouillons sur Policy. |
| 28 | P2 | Cliquer dans un champ de réglage lançait une fausse action et un toast d'erreur. | L'action vise uniquement le bouton d'enregistrement. |
| 29 | P2 | Un prix vide recevait un succès sans modification. | Champ requis dans le navigateur et valeur nulle refusée par l'API. |
| 30 | P2 | Lignes de tableaux cliquables sans activation clavier. | Activation par Entrée et Espace dans Pipeline et les fiches. |
| 31 | P2 | Une panne réseau lors d'une sauvegarde Pipeline n'offrait aucun retour. | Message visible, bouton réactivé, saisie conservée. |
| 32 | P2 | Catalogue indisponible avec cache ancien : la saisie libre promise était quand même refusée. | Mode non vérifié tant que le catalogue est en erreur, même avec un cache. |
| 33 | P1 | Depuis un hook Git, les scénarios d'installation héritaient du dépôt courant et modifiaient son index au lieu du dépôt temporaire. | Contexte Git retiré avant les contrôles ; scénario réel vérifiant que l'index et la configuration du dépôt poussé restent intacts. |

Le MRR du scénario de revue passe de 99 € à 118 €, correspondant à
99 € récents plus 19 € d'un ancien abonnement toujours actif.

## Vérification reproductible

`tests/test_mc_review.py` ajoute 12 scénarios API et navigateur : refus
de règles invalides et verrouillées, nombres, formulaire Unicode,
révocation du flux et de l'audio, backlog complet, discussions, actes des
13 types de tickets, MRR, brouillons, erreurs réseau, clavier, modales,
navigation rapide, QCM, action urgente et curation d'une leçon.

```sh
uv run python -m unittest tests.test_mc_review
uv run python scripts/pre-push-check.py
```

Le second contrôle exécute Ruff, les types, le scan de secrets, toute la
suite déterministe avec Chromium, puis le scénario LLM OpenRouter réel.
Le hook de push exige son succès. La PR donne le résultat de ce passage
et de la CI GitHub, avec les chiffres de tests.

Les images et relevés détaillés sont conservés localement dans
`reports/mission-control-review-main-2026-09-30/`, notamment
`after/evidence.json`. Ce dossier est ignoré par Git. Cette revue locale
ne certifie pas une instance de production : Discord réel, téléphonie
réelle et paiements Stripe ne sont pas déclenchés par ces scénarios.
