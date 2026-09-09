# Option A — SMS-only 2FA-proof (tuto installateur)

Objectif : Serge reçoit les SMS — surtout les codes OTP/2FA — sur un
**vrai 06/07** qui passe tous les contrôles de type de ligne. Pas
d'appels, pas de root, pas d'Asterisk.

Vue d'ensemble : [`PHONE_OPTIONS.md`](PHONE_OPTIONS.md).

- Durée : ~45 min.
- Coût : SIM 2 €/mois + un Android d'occasion (20–60 €, une fois).
- Compétences : installer une app Android, copier une URL, ouvrir un
  port WireGuard.

## Principe

```
opérateur (Free, B&YOU, SFR, Orange…)
    ↕ radio (vraie SIM, line_type=mobile)
Android dédié, branché H24, Wi-Fi
    ↕ webhook HTTPS sortant (l'app pousse, rien à exposer)
VPS Serge ──► sms_broker (SmsInbox : OTP only, HMAC, pas de body brut)
```

L'important : c'est le téléphone qui **pousse** vers le VPS. Pas de
port à ouvrir chez l'installateur, pas de Tailscale, pas de relais sur
le téléphone perso. Le VPS expose déjà son ingress ; le webhook SMS
s'y accroche comme n'importe quel callback signé.

Le broker (`serge/sms/inbox.py`, couvert par
`tests/test_sms_approval_brokers.py`) ne stocke que l'OTP extrait,
jamais le corps brut ni l'expéditeur. Ce tuto ne change pas ce
contrat : il lui donne une source propre.

## Matériel (BOM)

| Quoi | Recommandé | Pièges |
| --- | --- | --- |
| SIM voix+SMS au nom de l'owner | Free 2 €, B&YOU, SFR, Orange | Pas de SIM data-only, pas de SIM voyage, pas de numéro virtuel. La SIM doit pouvoir **recevoir** des SMS courts (banques, Google). |
| Android dédié | N'importe quel Android 8+ avec 4G, batterie encore honnête | Pas besoin de root, pas besoin de Qualcomm (c'est SMS-only). Éviter les téléphones d'entreprise avec MDM. |
| Chargeur + câble | Chargeur lent, à demeure | Un téléphone H24 sur charge rapide gonfle. Limiter à 60–80 % si l'OS le permet. |
| Wi-Fi stable | Le téléphone reste en Wi-Fi | La 4G du téléphone sert à la radio SMS, le webhook passe par Wi-Fi. Les deux doivent être up. |

Ne pas utiliser le téléphone quotidien de l'owner. Une SIM Serge =
un appareil Serge. C'est ce qui rend le montage portable et ce qui
évite de mélanger OTP perso et OTP Serge.

## Logiciel : SMS Gateway for Android

App recommandée : [SMS Gateway for Android](https://github.com/capcom6/android-sms-gateway)
(~5k stars, Kotlin, mode **Local Server** + webhooks `sms:received`).
Elle expose une API locale et pousse chaque SMS entrant vers une URL
à nous. Les messages partent **du téléphone vers le VPS** : l'éditeur
ne voit rien en mode local.

Alternatives notées, non recommandées par défaut :

- `httpSMS` (NdoleStudio, AGPL, ~4k stars) : bon projet mais backend
  Docker + Firebase + SMTP à self-héberger. Trop lourd pour « recevoir
  des OTP ».
- `SelfhostSim` : orienté GoHighLevel, Redis, FCM. Hors sujet kit.
- Modem USB + gammu/smsd : viable en headless, mais AT commands, SMS
  over IMS capricieux sur Orange/Free, pas plus simple qu'un Android.

## Installation pas à pas

### 1. Activer la SIM (10 min)

1. Souscrire la SIM **au nom légal de l'owner** (KYC opérateur).
2. L'insérer dans l'Android dédié, démarrer, entrer le PIN.
3. **Désactiver la demande de PIN au démarrage** (ou noter le PIN dans
   le coffre owner — un reboot à 4h du matin ne doit pas bloquer les
   OTP). Réglages → Sécurité → Verrouillage SIM.
4. Tester : envoyer un SMS depuis son propre téléphone vers le numéro
   Serge, vérifier la réception sur l'Android.
5. Tester un vrai OTP : lancer une vérification Google ou GitHub vers
   ce numéro. Si l'OTP arrive, la ligne est bonne pour 2FA.

### 2. Préparer l'Android (10 min)

1. Mettre à jour Android / Play Services au minimum raisonnable.
2. Verrouillage écran : code simple noté au coffre (le téléphone reste
   à domicile, mais pas ouvert à tout le monde).
3. Batterie : exemption d'optimisation pour l'app gateway
   (Réglages → Apps → SMS Gateway → Batterie → Non restreinte),
   démarrage auto autorisé.
4. Wi-Fi : oublier les réseaux instables, fixer le Wi-Fi domicile,
   activer « rester connecté en veille ».
5. Branché en permanence. Si l'OS propose une limite de charge,
   la régler à 80 %.

### 3. Installer et configurer la gateway (10 min)

1. Installer SMS Gateway for Android (Play Store ou APK du repo).
2. L'ouvrir, lui donner les permissions SMS (envoyeur + lecture —
   l'app en a besoin même si Serge ne lit que les OTP).
3. Activer **Local Server** : noter `http://<ip-lan>:8080`,
   créer `username` + `password` forts (coffre owner, jamais dans le
   TOML).
4. Tester en local depuis un PC du LAN :
   `curl -u user:pass http://<ip>:8080/health` (ou équivalent
   selon la version — voir la doc de l'app).

### 4. Relier au VPS Serge (10 min)

Le téléphone pousse, le VPS reçoit. Deux bouts à configurer.

**Côté VPS** — déjà câblé par le builder : unit `serge-sms-receiver`
(loopback `127.0.0.1:8787`) + route ingress `sms.<domaine>` :

- `POST https://sms.<domaine>/hooks/sms`, auth au choix :
  `X-SMS-Signature: HMAC_SHA256(secret, body)`, `X-SMS-Token: <secret>`,
  ou `?token=<secret>` pour les apps sans headers custom.
- Le secret partagé est `sms_gateway_token` (sidecar age → fichier
  `secrets/sms-gateway.token` 0600), jamais dans le TOML.
- Le handler normalise le payload de l'app puis appelle
  `SmsInbox.ingest(..., purpose='ACCOUNT_VERIFICATION')` : OTP extrait,
  body jeté, idempotence sur `id`, rate-limit 10/min/expéditeur.

**Côté Android** — enregistrer le webhook (depuis le LAN) :

```sh
curl -X POST -u '<username>:<password>' \
  -H 'Content-Type: application/json' \
  -d '{"id":"serge-vps","url":"https://sms.<domaine>/hooks/sms?token=<sms_gateway_token>","event":"sms:received"}' \
  'http://<ip-android>:8080/webhooks'
```

Le `<sms_gateway_token>` est celui affiché par le wizard à la
génération (ou dans le sidecar déchiffré). Préférer le header
`X-SMS-Token` si l'app permet des headers customs.

Vérifier dans les logs de l'app que le webhook est enregistré, puis
s'envoyer un SMS de test depuis son téléphone : il doit apparaître
côté Serge (OTP extrait, pas de body en base).

### 5. Durcir (5 min)

- [ ] Secret webhook ≥ 32 octets aléatoires, rotation possible sans
  réinstaller l'app (changer le secret des deux côtés).
- [ ] HTTPS only côté VPS (ingress existant). Jamais de webhook en
  HTTP clair sur internet.
- [ ] Rate-limit : quelques SMS/min max par expéditeur ; au-delà,
  log + drop (un flood SMS ne doit pas remplir le broker).
- [ ] Le téléphone ne quitte pas le domicile. En déplacement
  prolongé, prévoir le reboot à distance (prise connectée) ou un
  second chargeur.
- [ ] Noter au coffre : PIN/PUK SIM, code écran, user/pass gateway,
  URL webhook, numéro Serge.

## Vérification de fin

1. OTP Google → reçu, `latest_otp()` correct, base exempte de body.
2. OTP bancaire ou WhatsApp → reçu (le test qui tue les VoIP).
3. Reboot du téléphone → gateway redémarre seule, webhook toujours
   enregistré, OTP suivant reçu sans intervention.
4. Coupure Wi-Fi 2 min → les SMS reçus entre-temps sont poussés à la
   reconnexion (file d'attente de l'app) ou documentés comme perdus
   selon la version — tester, ne pas supposer.

## Dépannage

| Symptôme | Cause probable | Fix |
| --- | --- | --- |
| SMS reçu sur l'Android, rien sur Serge | Webhook non enregistré / URL fausse / secret faux | Relire les logs app, re-POST le webhook, tester le HMAC avec un payload connu. |
| Tout marchait, plus rien après une nuit | Optimisation batterie a tué l'app | Exemption batterie + verrouiller l'app en mémoire (selon surcouche). |
| OTP banque jamais reçu | Ligne ou expéditeur filtré | Tester avec un second service ; vérifier que la SIM reçoit bien les SMS courts (certains MVNO filtrent). Changer de MNO si besoin — pas d'app qui répare ça. |
| Doublons côté Serge | Retry webhook de l'app | Normal : `SmsInbox` est idempotent sur `id`. Ne pas « fixer » en supprimant l'idempotence. |
| Téléphone éteint / déchargé | Chargeur arraché, batterie morte | Prise + câble de rechange, limite de charge, capability `sms_read` qui passe en `READY_LOCKED` quand l'unit tombe. |

## Limites assumées

- Pas d'appels (c'est l'Option B).
- Un canal SMS : ~1 SMS / 2–3 s. Largement assez pour des OTP,
  insuffisant pour du marketing SMS de masse (qui est un autre
  métier, avec OACP et sender alphanumérique).
- Dépend d'un objet physique allumé. C'est le prix du `line_type=mobile`.
  Un monitoring « silence radio » est prévu mais pas codé ici.

## Envoi de SMS depuis Serge : non par défaut

Ce tuto couvre la **réception**. L'envoi (`sms_send`) reste
désactivé par principe : un Serge qui envoie des SMS depuis un 06,
c'est un 06 qui peut spammer, et les opérateurs coupent vite. Si un
jour l'envoi est ouvert, ce sera derrière le broker (allowlist de
destinataires, quotas, mandat explicite) — pas un `curl` libre vers
l'app. Ne pas activer l'API d'envoi « pour tester » sans ce garde-fou.
