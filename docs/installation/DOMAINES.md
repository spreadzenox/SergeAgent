# Les domaines des produits (Hostinger)

Depuis le lot 10, Serge achète seul le nom de domaine du produit fini
d'un business (étape 5), une fois son nom validé dans le ticket « Plan »
et le produit essayé dans le ticket « Tester le produit » (décision Q91).
Il l'achète chez Hostinger, par la capacité « Appeler une API » : le
service `hostinger` est décrit en base (table `api_services`, page
SQLite), et ses outils sont « Un nom de domaine est-il libre ? », « Le
prix d'un nom de domaine », « Acheter un nom de domaine », « Un nom de
domaine du compte » et « Faire pointer un domaine vers le serveur ».

## À faire une fois, dans hPanel

1. **Un jeton d'API** : hPanel → profil → « API » → créer un jeton.
   Le copier dans `~/.config/serge/secrets/hostinger-api.key` sur le
   serveur (une ligne, droits 0600).
2. **Un moyen de paiement par défaut** : la carte de Serge. L'achat la
   débite sans rien demander.
3. **Un profil WHOIS par extension** : hPanel → Domaines → profils WHOIS.
   Hostinger refuse l'achat d'un `.fr` sans profil WHOIS pour `.fr`
   (de même pour `.com`). Le titulaire est l'entreprise de Julien.

## Ce que Serge fait

- Il vérifie que le nom est libre, lit son prix dans le catalogue
  (en centimes : la première année et le renouvellement), et n'achète que
  sous le prix maximum de la page Policy (invocation « Acheter le domaine
  du produit », réglage « prix_max_eur », 30 € par an au départ).
- Il fait pointer le domaine vers le serveur : un enregistrement A pour
  `@`, vers l'adresse IPv4 du domaine de l'instance (outil « L'adresse du
  serveur de Serge »). Caddy obtient le certificat HTTPS tout seul.
- Un nom pris, trop cher ou refusé ouvre le ticket « Domaine », avec des
  noms libres proposés. « À corriger » avec un nom (exemple :
  `devis-artisan.fr`) achète ce nom ; « Valider » réessaie celui du plan,
  par exemple après avoir relevé le prix maximum.

## Pièges

| Symptôme | Cause typique |
| --- | --- |
| `secret_absent` dans le journal (`connecteur : hostinger : secret hostinger-api.key absent`) | Le jeton n'est pas posé sur le serveur. |
| HTTP 422 à l'achat | Pas de profil WHOIS pour cette extension, ou nom déjà pris. |
| HTTP 202 à l'achat | Le paiement est en cours : le domaine n'est pas enregistré. Le finir dans hPanel. |
| Le produit ne répond pas sur son domaine | Le DNS n'a pas encore propagé (jusqu'à une heure), ou l'enregistrement A ne vise pas le serveur. |
