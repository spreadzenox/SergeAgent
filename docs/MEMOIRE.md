# La mémoire de Serge

Ce document explique ce dont Serge se souvient, et ce que chaque invocation
LLM a le droit de voir.

Il remplace l'ancien modèle « 5 couches ». On garde le plus simple
possible, et on n'ajoute de la complexité que face à un vrai problème.

---

## Trois familles et un outil

| Famille | Question | Où | Qui écrit |
|---|---|---|---|
| **L'état** | Qu'est-ce qui est vrai maintenant ? | Les tables métier : `ventures`, `contacts`, `campaigns`, `transactions`… | Le code. Une ligne peut être modifiée. |
| **Le journal** | Que s'est-il passé ? | `events`, `touches`, `inbound_events`, `ticket_events` | Le code. On ajoute, on ne modifie jamais. |
| **La connaissance** | Qu'a-t-on appris ? | `lessons`, `playbooks` (procédures qui marchent), `pitfalls` (pièges), `summaries` (résumés) | La consolidation (étape 7), validée par Julien. |

**La recherche n'est pas une mémoire.** C'est un tool, `memory_search`, qui
lit les trois familles.

### Exemples

- « Le business *devis-artisan* est en test léger » : c'est de l'**état**
  (`ventures.lifecycle`).
- « Le 12 septembre, la fiche *X* a été écartée parce qu'elle ressemblait
  à *Y* » : c'est du **journal** (`events`). Chaque décision automatique
  (doublon écarté, business refusé parce que déjà en test, relance
  annulée) y est écrite, avec l'invocation qui l'a prise.
- « Les artisans répondent surtout entre 7 h et 8 h » : c'est de la
  **connaissance** (`lessons`).

---

## Ce que voit une invocation

### Aujourd'hui

- Chaque invocation LLM a une liste de tools en base (`llm_point_tools`).
  Elle peut les appeler pendant son exécution, 12 tours maximum.
- Certaines invocations de l'étape 1 ont aussi des « capsules »
  (`db_readers`, `llm_point_readers`) : des tools de lecture de la base
  avec des paramètres figés.
- Le tool « Demander une nouvelle capacité » est offert à toutes les
  invocations.
- **Défaut connu** : `memory_search` cherche par mots-clés dans un index
  que rien ne remplit en production. Il ne renvoie donc rien.

### Décidé : quatre règles

1. **Rien par défaut.** Une invocation ne voit que ce qu'on lui a donné,
   et c'est écrit sur sa fiche dans Mission Control.
2. **Trois cercles :**
   - **ce qu'elle traite** : reçu en entier. Exemple : la page à trier ;
   - **ce qui sert à comparer** : reçu en version courte. Exemple : la
     liste des business déjà connus, juste leur numéro et leur titre ;
   - **le reste** : sur demande, avec un tool. Exemple : la fiche complète
     d'un business, ou les leçons.
3. **Le journal n'est jamais donné d'office.** On peut seulement demander
   l'historique de l'objet traité. Exemple : les 20 derniers événements
   de ce business.
4. **Un maximum de lignes** pour chaque information donnée d'office.
   Exemple : on donne au plus 50 business à l'invocation. S'il y en a
   plus, elle reçoit les 50 plus récents et un message qui dit « 140
   autres business ne sont pas montrés ». Ce nombre se règle invocation
   par invocation dans Mission Control. Mission Control affiche combien de
   lignes l'invocation a reçues à chaque passage.

### Décidé : les cercles se déduisent tout seuls

On ne règle pas chaque invocation à la main.

- **Ce qu'elle traite** = ce que lui apporte le lien entrant. Exemple : le
  lien « Trier les pages → Formuler des business » apporte les pages
  marquées « signal ».
- **Ce qui sert à comparer** = la version courte des tables où elle écrit,
  ou auxquelles sa réponse fait référence. Exemple : « Formuler des
  business » écrit des business, donc elle reçoit la liste des business
  connus.
- **Le reste** = trois tools donnés automatiquement à chaque invocation :
  - « historique de l'objet traité » ;
  - « leçons » (les siennes lui sont déjà données d'office, voir
    ci-dessous) ;
  - « demander une nouvelle capacité ».

Réglages à faire :

- **une fois par table**, les colonnes de la version courte. Exemple :
  pour un business, le numéro et le titre ; pour une page, l'adresse et
  le titre ;
- **un maximum de lignes par défaut**, dans la policy (exemple : 50) ;
- **des exceptions à la main** dans Mission Control.

### Décidé : les leçons et le contexte général

- Une leçon est rattachée à une invocation, sinon à une étape, sinon à
  tout Serge. Une invocation reçoit d'office **ses propres leçons**, les
  plus fiables d'abord.
- Les invocations de niveau moyen et intelligent reçoivent un court bloc
  **« Qui est Serge et quelle est ta place »**, fabriqué depuis la base à
  chaque appel. Exemple :

  > **Serge** est un opérateur économique autonome : il repère des
  > besoins, teste des business, vend et livre, sous le contrôle de
  > Julien.
  > **La chaîne :** 1. Pré-prospection → 2. Conception du POC → … →
  > 8. Caisse.
  > **Ta place :** tu es « Formuler des business A », dans l'étape 1.
  > **Avant toi :** « Trier les pages » t'a transmis les pages marquées
  > « signal ».
  > **Après toi :** tes fiches passent par « Dédoublonner », puis
  > « Choisir les business à tester ».

  Le texte de présentation est en base, modifiable dans Mission Control.
  Une case sur la fiche de l'invocation l'active ou non.

---

## La consolidation

Voir [`etapes/7-memoire.md`](etapes/7-memoire.md).

## L'oubli

- Les événements anciens peuvent être archivés dans des fichiers
  compressés (`serge/memory/archive.py`, table `episode_archives`). On
  peut les relire.
- Une leçon contredite plusieurs fois passe au statut `deprecated`. Elle
  n'est pas effacée.
- Une page d'écoute marquée « bruit » sera oubliée après X jours ; une page
  qui sert de preuve est gardée (décidé, voir l'étape 1).
