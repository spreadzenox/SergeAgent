# La mémoire de Serge

Ce document explique ce dont Serge se souvient, où il le range, et ce que
chaque invocation a le droit de voir quand elle travaille. Une invocation
est une brique de travail de Serge : soit un appel au LLM avec son prompt,
soit un traitement sans LLM.

On a volontairement gardé le modèle le plus simple possible. Il remplace
un ancien modèle en « 5 couches » qui était devenu difficile à suivre. On
n'ajoute de la complexité que le jour où un vrai problème l'exige.

---

## Trois sortes de souvenirs

Serge range ce qu'il sait en trois familles, qui répondent chacune à une
question différente. Toutes vivent dans la même base de données.

**L'état répond à la question « qu'est-ce qui est vrai maintenant ? ».**
Ce sont les tables qui décrivent le monde tel qu'il est : les business,
les prospects et clients, les campagnes de test, les paiements. Une ligne
d'état peut être modifiée : quand un business passe du test léger à la
construction, on change son statut sur sa ligne. C'est le code qui écrit
l'état, jamais le LLM directement. Exemple : « le business *devis-artisan*
est en test léger » est un fait d'état. La fiche produit d'un business
(ce que fait le produit, son prix, ses délais, les questions fréquentes)
fait aussi partie de l'état : elle est mise à jour à chaque nouvelle
version du produit.

**Le journal répond à la question « que s'est-il passé ? ».** C'est la
liste de tout ce qui est arrivé, dans l'ordre : chaque envoi à un
prospect, chaque réponse reçue, chaque décision prise, chaque changement
de ticket. On y ajoute des lignes, on n'en modifie ni n'en supprime
jamais. Chaque décision automatique y est notée avec l'invocation qui l'a
prise, par exemple une fiche de business écartée parce qu'elle
ressemblait trop à une autre, un business refusé parce qu'il était déjà
en test, ou une relance annulée parce que le prospect avait répondu.
Exemple : « le 12 septembre, la fiche *X* a été écartée parce qu'elle
ressemblait à la fiche *Y* » est une ligne du journal.

**La connaissance répond à la question « qu'a-t-on appris ? ».** Ce sont
les leçons, les procédures qui marchent, les pièges à éviter et des
résumés. Elles sont proposées par la consolidation (l'étape 7 de la
chaîne), qui relit le journal, et Julien garde ou jette chaque leçon.
Exemple : « les artisans répondent surtout entre 7 h et 8 h » est une
leçon.

La recherche dans la mémoire n'est pas une quatrième famille. C'est un
outil, que les invocations peuvent appeler pour chercher un mot dans les
trois familles à la fois.

---

## Ce que voit une invocation aujourd'hui

Tout ce qu'une invocation LLM reçoit est lu en base à chaque appel, et
affiché sur sa fiche dans Mission Control :

1. **Ses lectures données d'office** (ce qu'elle doit traiter). Elles sont
   réglées invocation par invocation (`invocation_tools`, en mode
   `given`) : Serge fait la lecture avant l'appel et met le résultat
   directement dans le prompt. Ce n'est pas un outil que le modèle appelle. Exemple :
   « Formuler des idées » reçoit le cycle en cours, dont le numéro vient
   du lien qui l'a lancée.
2. **La version courte des tables à comparer.** Toutes les tables où elle
   écrit, sans rien régler pour elle : la base dit, une fois par table
   (`table_views`, `table_view_columns`), quelles colonnes forment sa
   version courte. Sur la fiche de l'invocation, un bouton retire une de
   ces tables ou en ajoute une autre (`invocation_compare_tables`).
3. **Ses leçons**, les plus fiables d'abord.
4. **Le bloc « Qui est Serge »**, si la case est cochée sur sa fiche.

Chaque information donnée d'office a un nombre maximum de lignes (le
maximum de l'invocation, 50 par défaut ; une lecture d'office peut avoir
le sien). Au-delà, elle reçoit les lignes les plus récentes et le nombre
exact de lignes laissées de côté ; la fiche de la tâche dans Mission
Control affiche par exemple « 20 lignes, 230 laissées de côté ».

Pendant son exécution, elle peut appeler ses outils dans la limite réglée
sur l'invocation (douze allers-retours par défaut). Trois outils sont
donnés à toutes les invocations, quand ils leur servent : « Lire les
tables que je vois », « Lire l'historique » et « Demander une nouvelle
capacité ». Le détail est ci-dessous.

Il y a aussi un défaut connu : l'outil de recherche dans la mémoire
cherche dans un index que rien ne remplit en production. Il ne renvoie
donc jamais rien pour l'instant ; il est donné invocation par invocation,
pas à toutes.

---

## Les règles de ce que voit une invocation

Julien a validé les règles suivantes. Elles sont construites (lot 6),
sauf ce qui est listé à la fin de ce document.

**Tout ce que voit une invocation est décrit en base.** Julien et Clem
ont décidé que le code n'est qu'un interpréteur de la base (voir
[`PIPELINE.md`](PIPELINE.md)). Ce qu'une invocation reçoit dès le départ,
les outils qu'elle peut appeler, leurs paramètres figés et le nombre
maximum de lignes sont donc des lignes en base, modifiables dans Mission
Control, et jamais des valeurs écrites dans le code.

**Une invocation ne voit que ce que la base lui donne.** Rien n'est
ajouté par le code : ce qu'elle reçoit suit des règles écrites en base,
les mêmes pour toutes les invocations, et réglables dans Mission Control.
Tout ce qu'elle reçoit est affiché sur sa fiche, pour qu'on puisse
toujours savoir sur quoi elle a travaillé.

**Ce qu'elle reçoit se range en trois cercles.** Le premier cercle, c'est
ce qu'elle doit traiter : elle le reçoit en entier. Par exemple, une
invocation qui trie des pages web reçoit le texte complet de la page à
trier. Le deuxième cercle, c'est ce qui lui sert à comparer : elle le
reçoit en version courte. Par exemple, pour savoir si une idée de
business est nouvelle, elle reçoit la liste des business déjà connus,
mais seulement leur numéro et leur titre. Le troisième cercle, c'est le
détail de ce qu'elle voit en version courte, et l'historique : elle peut
le demander si elle en a besoin, avec un outil. Par exemple, la fiche
complète du business n° 12, qu'elle a vu dans sa liste courte.

**Le journal n'est jamais donné d'office.** Il est trop gros et
l'invocation n'en a presque jamais besoin en entier. Elle peut seulement
demander l'historique d'une ligne qu'elle voit, par exemple les vingt
derniers événements du business sur lequel elle travaille, ou d'un
business de sa liste courte.

**Le détail et l'historique ne sont pas la même chose.** Le détail d'un
business, c'est ce qu'il contient maintenant : son nom, sa description,
son offre, son statut. Son historique, c'est ce qui lui est arrivé :
créé par « Formuler des business » le 27, choisi par « Choisir les
business à tester » le 28, une écriture refusée le 29.

**Chaque information donnée d'office a un nombre maximum de lignes.**
Par exemple, on donne au plus 50 business à une invocation. S'il y en a
140, elle reçoit les 50 plus récents, suivis d'une phrase qui dit « 90
autres business ne sont pas montrés ». Si elle a besoin des autres, elle
les demande avec « Lire les tables que je vois ». Ce maximum vaut 50 par défaut et
se règle invocation par invocation dans Mission Control. À chaque
passage, Mission Control affiche combien de lignes l'invocation a
vraiment reçues.

**On ne règle pas chaque invocation à la main : les cercles se déduisent
de la chaîne.** Ce que l'invocation doit traiter, c'est ce que lui
apporte l'invocation d'avant. Par exemple, quand « Trier les pages »
passe la main à « Formuler des business », elle lui transmet les pages
qu'elle a marquées comme signalant un besoin. Ce qui sert à comparer,
c'est la version courte des tables où l'invocation écrit : « Formuler des
business » écrit des business, donc elle reçoit la liste courte des
business déjà connus. C'est systématique, mais pas écrit dans le code :
la base dit, une fois pour chaque table, quelles colonnes forment sa
version courte, et l'interpréteur applique cette règle à toutes les
invocations. Sur la fiche d'une invocation, dans Mission Control, on peut
ajouter une table à comparer ou en retirer une.

**Le reste est accessible par des outils donnés à toutes les
invocations :**

1. **« Lire les tables que je vois »**. Ce n'est pas un outil écrit pour
   une invocation, mais une sorte d'outil : il en existe un par
   invocation, construit à chaque appel à partir de la base. Il ne donne
   accès qu'aux tables que l'invocation voit en version courte (son
   deuxième cercle). Dans ces tables, le modèle peut demander toutes les
   lignes, et toutes les colonnes marquées lisibles. Exemple : « Formuler
   des business » voit la liste courte des business ; elle peut demander
   la fiche complète du business n° 12, ou tous les business au statut
   `CANDIDATE`, mais elle ne peut pas lire les paiements, qu'elle ne voit
   pas. Les colonnes qui ne doivent jamais sortir, comme les mots de passe
   des comptes web, ne sont pas marquées lisibles.
2. **« Lire l'historique »** d'une ligne qu'elle voit (premier ou
   deuxième cercle) : ses derniers événements dans le journal.
3. **« Chercher dans la mémoire »** : une recherche par mots dans les
   leçons, les événements et les tickets. Il sera donné à toutes les
   invocations quand son index sera rempli.
4. **« Demander une nouvelle capacité »**, pour dire à Julien qu'il lui
   manque quelque chose.

Il ne reste donc que quelques choses à régler, en base : une fois pour
chaque table, les colonnes qui forment sa version courte (pour un
business, son numéro et son titre ; pour une page, son adresse et son
titre) et les colonnes lisibles ; le maximum de lignes par défaut ; et, à
la main dans Mission Control, les quelques exceptions.

**Exemple : ce que reçoit « Traiter une réponse ».** Quand un prospect
répond, l'invocation qui lui répond reçoit en entier, dans ce qu'elle
traite, tout son fil de discussion, sa fiche, la fiche du business et la
fiche produit. C'est ce qui lui permet de répondre juste à une question
sur le produit sans rien inventer. L'agent vocal reçoit les mêmes
informations quand il reconnaît le numéro de celui qui appelle.

**Chaque invocation reçoit ses propres leçons.** Une leçon est rattachée
à l'invocation qu'elle concerne, sinon à une étape de la chaîne, sinon à
tout Serge. Une invocation reçoit d'office les leçons qui la concernent
directement, les plus fiables en premier.

**Les invocations qui réfléchissent reçoivent un court texte qui leur
explique où elles sont.** Les invocations qui utilisent un modèle moyen
ou intelligent reçoivent, en tête de prompt, un bloc « Qui est Serge et
quelle est ta place ». Il est fabriqué à chaque appel à partir de la
base, pour être toujours à jour. Par exemple :

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

Le texte de présentation de Serge est en base et modifiable dans Mission
Control, et une case sur la fiche de chaque invocation permet de
l'activer ou non.

---

## Tirer des leçons

La consolidation relit régulièrement le journal et propose des leçons,
des procédures et des pièges. Julien garde ou jette chacune ; sans
réponse de sa part sous 48 heures, elles sont acceptées. Le détail est
dans [`etapes/7-memoire.md`](etapes/7-memoire.md).

---

## Oublier

Serge n'efface presque rien, mais il range. Les événements anciens du
journal peuvent être archivés dans des fichiers compressés, et on peut
toujours les relire. Une leçon contredite plusieurs fois n'est pas effacée :
elle est marquée comme dépassée. Enfin, une fois l'étape 1 refaite, une
page web marquée « bruit » sera oubliée au bout d'un certain nombre de
jours, réglable, alors qu'une page qui sert de preuve à un business sera
toujours gardée.

---

## Ce qui reste à faire

- [ ] **Rattacher les leçons à une invocation ou à une étape.** Une leçon
  rattachée à une invocation (portée `invocation:<id>`) ou à une étape
  (`etape:<id>`) est déjà donnée d'office à qui la concerne ; il reste à
  ce que la consolidation (l'étape 7) propose ce rattachement.
- [ ] **Remplir l'index de recherche dans la mémoire.** Chaque nouvelle
  leçon, chaque nouvel événement et chaque nouveau ticket doit y être
  ajouté au moment où il est écrit, pour que la recherche renvoie enfin
  quelque chose.
