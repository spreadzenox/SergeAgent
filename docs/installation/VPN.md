# Le VPN du navigateur (Télécom Paris)

Le navigateur de Serge sort par un VPN Télécom Paris. Sans lui, LinkedIn et
Reddit refusent l'adresse IP du VPS.

## Ce qui passe par le VPN, et ce qui n'y passe pas

Seul le trafic **web des deux conteneurs Chrome** de Serge
(`serge-navigateur` et `serge-vrai-chrome`) sort par le tunnel. C'est un
sidecar Docker, `serge-vpn` (image gluetun), qui porte le tunnel ; les deux
Chrome partagent son réseau. Le reste du serveur n'est pas touché : les
autres projets, les chantiers, les routes de l'hôte, le DNS du serveur.

L'écran du vrai Chrome (noVNC, `/owner/vrai-chrome` dans Mission Control)
n'est pas dévié : le sidecar publie ses ports sur `127.0.0.1`, et Mission
Control relaie l'écran par l'IP du VPS. Un humain qui vient résoudre un
captcha passe donc par le serveur, pas par le tunnel. La sortie web des
Chrome, elle, passe bien par le VPN.

Si le tunnel tombe, gluetun coupe la sortie du réseau partagé : les pages
échouent franchement et l'IP du VPS ne sert pas de repli (pas de fuite).

## Le réglage

Page Policy, « Bac à sable », **Désactiver le VPN** (`navigateur.vpn_off`) :

- `non` (défaut) : les deux Chrome sortent par le VPN ;
- `oui` : les deux Chrome reprennent le réseau des chantiers et publient
  leurs ports eux-mêmes, comme avant le VPN.

Le changement vaut au prochain lancement d'un des deux Chrome : un
conteneur déjà lancé n'est pas déplacé tant qu'il tourne.

## Installation du compte, une fois par serveur

Les deux secrets sont sur le serveur, jamais dans le dépôt :

```sh
install -m 600 /dev/null ~/.config/serge/secrets/telecom-vpn-login
install -m 600 /dev/null ~/.config/serge/secrets/telecom-vpn-password
printf 'cpesquet-25\n' > ~/.config/serge/secrets/telecom-vpn-login
printf 'LE_MOT_DE_PASSE\n' > ~/.config/serge/secrets/telecom-vpn-password
```

Le fichier du tunnel est `config/vpn/telecom-paris.ovpn` dans le dépôt
(certificats publics, aucun secret). Gluetun refuse un nom d'hôte : à
chaque lancement du sidecar, `serge/sandbox/vpn.py` résout
`vpn.telecom-paris.fr` et écrit une copie avec l'IP dans
`~/.config/serge/vpn/telecom-paris.ovpn`.

Sans ces secrets, le lancement du navigateur échoue avec « secret absent
sur ce serveur : telecom-vpn-login », au journal de la file `works` (page
Health).

## Les ports

Le sidecar publie sur `127.0.0.1` seulement : le débogage du navigateur
sans écran (`9222`), le débogage du vrai Chrome (`9223`), l'écran du vrai
Chrome (`6080`). Dans le réseau partagé, le vrai Chrome écoute son propre
débogage sur `9224` pour laisser `9222` au navigateur sans écran (son
`demarrer.sh` lit `CHROME_PORT`).

## Vérifier

Une fois le VPN actif, l'outil navigateur doit joindre
`https://ifconfig.me` et montrer une IP de Télécom Paris (137.194.x.x), et
LinkedIn doit s'ouvrir. `http://chantier:<port>` doit continuer de joindre
le chantier (le sidecar est branché sur le réseau `serge-chantiers` et son
pare-feu autorise `172.18.0.0/16`).

En cas d'échec, les dernières lignes de gluetun sont au journal :

```sh
docker logs --tail 30 serge-vpn
```

## Revenir en arrière

Passer `navigateur.vpn_off` à `oui`. Au lancement suivant, chaque Chrome
est refait sur le réseau des chantiers, comme avant. Le sidecar peut rester
lancé : il ne sert simplement plus. Pour l'arrêter :

```sh
docker rm -f serge-vpn
```

## Tests

`tests/test_vpn.py` couvre le lancement du sidecar (réseau, ports,
secrets), le réglage, l'absence de secrets et le tunnel qui ne s'établit
pas. `tests/test_chrome.py` couvre le placement des deux Chrome dans le
réseau du VPN, la reconstruction au changement de réglage, et le retour au
comportement direct quand le VPN est désactivé.
