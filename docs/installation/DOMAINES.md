# Les domaines des produits (Cloudflare)

Depuis le lot 10, Serge achète seul le nom de domaine du produit fini
d'un business (étape 5), une fois son nom validé dans le ticket « Plan »
et le produit essayé dans le ticket « Tester le produit » (décision Q91).
Il l'achète chez **Cloudflare**, avec **sa propre carte**, enregistrée
sur son compte Cloudflare : jamais une carte personnelle. C'est là que
l'ancien Serge a déjà acheté un domaine, en août 2026.

## Le domaine commun des produits finis (au début)

Pour ne pas dépenser un domaine par produit, un réglage les publie tous
sous un domaine que Serge possède déjà : page Policy, invocation
« Choisir le domaine du produit », réglage `domaine_commun`.

- **Rempli** (exemple : `exemple-serge.com`) : après ton essai du produit,
  Serge n'achète rien ; la prod va sur `<produit>.exemple-serge.com`
  (exemple : `calculatrice.exemple-serge.com`). Le nom de domaine que
  propose le plan est alors ignoré.
- **Vide** : Serge achète un domaine par produit, comme décrit plus bas.

Pour chaque produit, Serge crée lui-même, dans la zone Cloudflare de ce
domaine, l'enregistrement A de son sous-domaine vers le serveur, sans le
proxy de Cloudflare (invocation « Faire pointer le sous-domaine du
produit », qui n'a aucun outil d'achat), puis le met en vente. Un seul nom
par produit, jamais `*` : seuls les produits publiés mènent au serveur.
Caddy obtient le certificat HTTPS de chacun. Le domaine doit être au
compte Cloudflare de Serge. Le réglage se change à tout moment ; il vaut
pour les produits qui n'ont pas encore passé l'essai.

Serge passe par la capacité « Appeler une API ». Deux services sont
décrits en base (table `api_services`, page SQLite) :

- `cloudflare_registrar` : vérifier qu'un nom est libre et lire son prix,
  l'acheter, lister les domaines du compte ;
- `cloudflare_dns` : trouver la zone d'un domaine et faire pointer le
  domaine vers le serveur.

## Ce qu'il faut sur le serveur

| Fichier | Ce que c'est |
|---|---|
| `~/.config/serge/secrets/cloudflare-registrar.key` | Un jeton d'API Cloudflare pour le registrar : lire et acheter des domaines du compte. |
| `~/.config/serge/secrets/cloudflare-infra.key` | Un jeton d'API Cloudflare pour le DNS : lire les zones du compte et modifier leurs enregistrements, pour toutes les zones (un domaine acheté crée une zone nouvelle). |
| `~/.config/serge/cloudflare-account-id` | L'identifiant du compte Cloudflare. Il n'est pas secret, mais propre à l'instance : il n'est jamais écrit dans le dépôt. Serge le lit au moment de l'appel (`{config:cloudflare-account-id}` dans le chemin des outils). |

Une ligne par fichier, droits 0600. Sur le compte Cloudflare, la carte
de Serge est le moyen de paiement (Billing → Payment methods).

## Ce que Serge fait

1. Il regarde si le nom est déjà au compte : il ne l'achète pas deux fois.
2. Il vérifie qu'il est libre et non premium, et lit son prix en dollars
   (la première année et le renouvellement). Il compte 1 $ = 1,10 € pour
   rester prudent, et n'achète que sous le prix maximum de la page
   Policy (invocation « Acheter le domaine du produit », réglage
   « prix_max_eur », 30 € par an au départ). Cloudflare ne vend pas
   toutes les extensions : un `.com` passe toujours.
3. Il l'achète pour un an, sans renouvellement automatique (figé en base).
4. Il fait pointer le domaine vers le serveur : un enregistrement A, sans
   le proxy de Cloudflare, vers l'adresse IPv4 du domaine de l'instance
   (outil « L'adresse du serveur de Serge »). Caddy obtient le
   certificat HTTPS tout seul.

Un nom pris, trop cher ou refusé ouvre le ticket « Domaine », avec des
noms libres proposés. « À corriger » avec un nom (exemple :
`devis-artisan.com`) achète ce nom ; « Valider » réessaie celui du plan,
par exemple après avoir relevé le prix maximum.

## Pièges

| Symptôme | Cause typique |
|---|---|
| `secret_absent` dans le journal (`connecteur : cloudflare_registrar : secret cloudflare-registrar.key absent`) | Le jeton n'est pas posé sur le serveur. |
| `config_absente` (`réglage cloudflare-account-id absent de config_root`) | L'identifiant du compte manque dans `~/.config/serge/`. |
| HTTP 403 sur le DNS d'un domaine neuf | Le jeton DNS ne couvre qu'une zone : lui donner « toutes les zones » du compte. |
| `registrable: false` | Le nom est pris, ou l'extension n'est pas vendue par Cloudflare. |
| Le produit ne répond pas sur son domaine | Le DNS n'a pas encore propagé (quelques minutes), ou l'enregistrement A ne vise pas le serveur. |
