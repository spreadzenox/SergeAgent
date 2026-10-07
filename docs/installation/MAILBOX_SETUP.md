# Mailbox : boîte de confiance SMTP/IMAP (sans OAuth)

Alternative à [`GMAIL_SETUP.md`](GMAIL_SETUP.md) : une boîte email classique
en SMTP (envoi) + IMAP (lecture), pilotée par 2 secrets (login + mot de passe),
sans binaire externe, sans navigateur, sans drift de version. 100 % stdlib,
TLS vérifié, transportable dans le couple → collaborateur clé en main.

## 1. Choisir le fournisseur (recommandé : Infomaniak)

| Preset | SMTP | IMAP | Notes |
|---|---|---|---|
| `infomaniak` (défaut) | `mail.infomaniak.com:587` STARTTLS | `mail.infomaniak.com:993` SSL | Login = adresse complète. Pas d'alerte nouvelle IP. |
| `gmail` | `smtp.gmail.com:587` STARTTLS | `imap.gmail.com:993` SSL | 2FA + App Password obligatoires. |
| `fastmail` | `smtp.fastmail.com:587` STARTTLS | `imap.fastmail.com:993` SSL | App password recommandé. |
| `custom` | à saisir (587 STARTTLS / 465 SSL) | à saisir (993 SSL / 143 STARTTLS) | Tout serveur standard. |

**Pourquoi pas un Gmail partagé ?** Un compte Google utilisé depuis plusieurs
lieux déclenche des alertes « connexion suspecte » (voire des blocages) —
incompatible avec une boîte partagée clé en main. Pour Gmail, préfère un
compte par collaborateur ([GMAIL_SETUP.md](GMAIL_SETUP.md)) ou une boîte
dédiée chez un fournisseur IMAP simple.

## 2. Kit (wizard)

- `features.mailbox = true` → preset (défaut `infomaniak`) + login (+ 4
  hosts/ports si `custom`) → mot de passe à l'étape secrets.
- Sidecar → `secrets/mailbox-password` (`0600`).
- Cohabitation : `mailbox` on → SMTP prioritaire ; `gmail` seul → gog ;
  aucun → pas de canal e-mail (sa fiche dit « prévu », rien n'est relevé
  ni envoyé).

## 3. Tester

Dans Mission Control, la fiche du canal E-mail doit dire « branché » :
Serge relève alors la boîte de réception toutes les 2 minutes, et range
une copie de chaque message envoyé dans le dossier des envoyés (c'est elle
qui confirme un envoi interrompu).

## 4. Dépannage

- `AUTH: smtp/imap refusé` → login ou mot de passe faux (app password ?).
- `NETWORK: smtp/imap (...)` → hôte/port injoignable, TLS (certificat du
  serveur vérifié, pas désactivable).
- `API: destinataire refusé (...)` → l'adresse n'existe pas : l'envoi passe
  en échec.

## 5. Sécurité

- Mot de passe : `0600`, sidecar chiffré, jamais dans git, le TOML ou un chat.
- TLS toujours vérifié (STARTTLS/SSL selon port) ; aucun mode non chiffré.
- Envois bornés par les garde-fous et par « E-mails envoyés au plus, par jour »
  (`channels.email.max_per_day`, 40 au départ, page Policy).
