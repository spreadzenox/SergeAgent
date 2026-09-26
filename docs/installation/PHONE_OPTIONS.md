# Téléphonie kit : deux options, pas de relais perso

Le kit propose **deux** montages téléphone. Pas de Tailscale vers le
téléphone de l'owner, pas d'émulateur Android sur le VPS, pas de eSIM
logicielle : ces trois impasses sont documentées plus bas pour ne plus
les réexplorer.

- **Option A — SMS-only** : un vrai 06/07 qui reçoit tous les OTP/2FA.
  Tuto : [`PHONE_SMS_ONLY.md`](PHONE_SMS_ONLY.md).
- **Option B — SMS + voix commerciale** : Option A **plus** un tronc SIP
  VoIP avec numéro conforme pour que Serge appelle et décroche.
  Tuto : [`PHONE_VOICE_SMS.md`](PHONE_VOICE_SMS.md).

L'Option B n'est **pas** « un seul numéro qui fait tout ». C'est deux
numéros, chacun dans son rôle légal et technique. La section
« Pourquoi pas un seul numéro » explique pourquoi c'est le seul montage
honnête en France en 2026.

## Matrice de choix

|  | Option A (SMS-only) | Option B (A + voix SIP) |
| --- | --- | --- |
| Numéros | Un 06/07 SIM MNO | 06/07 SIM **+** DID VoIP NPV/géo |
| OTP / 2FA banques, WhatsApp, Google | Oui, tout passe | Oui (par la SIM) |
| Serge appelle | Non | Oui, N canaux SIP |
| Serge décroche | Non (SMS only) | Oui (agent vocal) |
| Légalité prospection FR | N/A (pas d'appels) | Oui si NPV + consentement + horaires |
| Matériel | Android dédié quelconque | Même Android, rien de plus |
| Install | ~45 min, sans root | +~1 h de SIP/Asterisk |
| Coût type | SIM 2 €/mois + phone occaz | + ~2–6 €/mois DID + conso |
| Fragilité | Téléphone allumé H24 | Idem + dépendance trunk SIP |

Règle de décision :

- « Je veux juste que Serge reçoive les codes » → **A**.
- « Je veux que Serge appelle des prospects / clients » → **B**.
- « Je veux un seul 06 qui fait OTP + prospection automatisée » →
  **n'existe pas légalement**. Lire la suite.

## Pourquoi pas un seul numéro

### Un 06/07 ne peut pas prospecter

Depuis le 1er janvier 2023, les 06/07 sont **interdits** pour le
démarchage commercial. La prospection automatisée doit présenter un
numéro polyvalent vérifié (NPV) : 0162, 0163, 0270, 0271, 0377, 0378,
0424, 0425, 0568, 0569, 0948, 0949 (métropole). Depuis le 11 août 2026,
le démarchage est en plus **interdit par principe** sauf contrat en
cours en rapport ou consentement préalable explicite, avec plages
lun–ven 10h–13h / 14h–20h, max 4 sollicitations / 30 jours, et
certification ARCEP des CLI (blocage de l'usurpation).

Un gsm2sip / Android rooté / modem Quectel derrière un 06 fait un
excellent téléphone **relationnel** (un humain appelle Serge, Serge
rappelle un client connu). Branché sur un robot de prospection, c'est
un 06 qui spam : suspension SIM par l'opérateur, flag anti-spam,
et infraction. Le kit ne documente pas ce montage comme voie
commerciale.

### Un numéro VoIP ne reçoit pas les OTP

Banques, WhatsApp, Google, Leboncoin et consorts interrogent le type
de ligne avant d'envoyer un code (Twilio Lookup V2
`line_type_intelligence`, Telesign, etc.) :

- `mobile` (vraie SIM MNO) → passe.
- `nonFixedVoip` (Twilio, Zadarma, Skype, TextNow…) → **rejeté**,
  parfois avec suspension différée du compte.

C'est un filtre anti-fraude, pas un bug. Il est plus strict à la
**création** de compte qu'au login quotidien, et maximal pour les
banques. Aucun trunk SIP « pas cher » ne contourne ça : s'il n'y a pas
de SIM d'opérateur derrière, le HLR le dit.

Conséquence : **tout Serge qui crée des comptes a besoin d'une vraie
SIM**, même si toute sa voix passe en SIP. C'est l'Option A, socle
obligatoire de l'Option B.

### Les fausses bonnes idées, classées

| Idée | Verdict | Pourquoi |
| --- | --- | --- |
| eSIM opérateur dans un émulateur / VPS | Impasse | Pas de puce eUICC, pas de baseband, pas de radio. Les eSIM « voyage » sont du data, pas un 06 qui appelle. |
| Android-x86 / Waydroid / Redroid sur VPS | Impasse | Même cause : pas de modem cellulaire. |
| Cloud phone ARM loué | Mauvais | Télécommander un téléphone distant + re-streamer l'audio : pire que SIP, souvent hors FR, OTP non garantis. |
| Bluetooth `chan_mobile` | Sale | HFP 8 kHz, MTU capricieux, pairing fragile. OK pour bricoler, pas pour un agent. |
| Stick Quectel / SIM7600 voix USB | Piège 2026 | Propre quand ça marche (USB Audio → Asterisk), mais Free éteint la 3G : sans VoLTE + profil MBN opérateur, le stick ne téléphone plus. Loteries firmware par opérateur. |
| GoIP 1 canal 4G | Cher et sale | 100–150 €+, firmware fermé, ressemble à une SIM box aux yeux des opérateurs. |
| gsm2sip sur Poco X3 NFC | Bon, mais niche | Le meilleur pont radio→SIP FOSS actuel (PCM modem, G.722, SMS). Réservé aux users qui acceptent Lineage + Magisk + un modèle précis. Chemin **relationnel**, jamais prospection. |
| `gsm-sip-bridge` (IMS/VoWiFi hôte) | Trop tôt FR | Le plus propre sur le papier (AMR-WB natif), mais suppose qu'un opérateur FR accepte un client IMS/ePDG générique. Non démontré sur Free/Orange. SMS in-only. |

## Ce que « Serge commercial » impose vraiment

Serge utilisera le téléphone **essentiellement pour du commercial**,
plus des usages secondaires (relances, rappels RDV, SAV inbound, OTP,
callbacks). Ça donne des contraintes différentes d'un « téléphone de
geek » :

1. **Deux identités d'appel.** NPV pour la prospection automatisée
   (légal, traçable), 06 SIM pour le relationnel humain (confiance,
   rappels, OTP). Un seul CLI ne peut pas faire les deux.
2. **N canaux, pas 1.** gsm2sip = 1 appel à la fois. Un trunk SIP =
   N appels, files d'attente, enregistrement, transcription. La
   prospection ne tient pas sur un canal.
3. **Taux de décroché vs conformité.** Un NPV/09 décroche moins bien
   qu'un 06 — c'est le prix de la légalité, et les gens ont appris à
   reconnaître les tranches démarchage. L'inverse (prospecter en 06)
   décroche mieux et fait suspendre la ligne.
4. **Preuve et contrôle.** Enregistrement (MixMonitor), CDR, consentement
   tracé, respect Bloctel/horaires/quotas, kill-switch. Le mandat
   `sandbox` coupe la voix sortante ; le mandat live doit borner
   volumes et plages. La voix est une mutation externe comme les
   paiements : même discipline broker.
5. **Réputation CLI.** Certification ARCEP 2026, STIR/SHAKEN-like,
   scoring spam des opérateurs. Pas de spoofing de CLI, pas de
   rotation de numéros pour contourner les quotas : c'est exactement
   ce que la régulation punit.
6. **Coûts prévisibles.** DID au mois + minutes. Pas de « SIM illimitée »
   qui se fait couper au 200e appel automatisé.

## Recommandations kit (résumé)

- **Défaut SMS (obligatoire si Serge crée des comptes)** : SIM MNO FR
  + Android dédié + passerelle SMS → webhook → `sms_broker`
  (Option A). 2 €/mois, pas de root, pas d'Asterisk.
- **Défaut voix commerciale** : trunk SIP FR + Asterisk minimal sur le
  VPS + voix temps réel (`voice` = xAI ou OpenAI, speech-to-speech ;
  repli tour-par-tour livré), en **plus** de l'Option A (Option B).
  Zadarma ou OVH en premier, Twilio en plan C API-riche.
- **gsm2sip** : option documentée « radio réelle + voix propre » pour
  le relationnel 06/07, pas le chemin prospection, pas le défaut kit.
- **Relais Tailscale + téléphone perso** : Julien-only, historique,
  hors kit. Ne pas copier.

## Intégration kit (livrée)

- `features.phone_sms` / `features.phone_voice` dans le TOML, **on**
  par défaut (tout-ou-rien). `phone_voice` exige `phone_sms` + `voice` ;
  `phone_sms` exige `ingress` + `public_hostname`.
- Secrets : `sms_gateway_token` (webhook, généré par le wizard si vide),
  `sip_trunk_password` (rendu dans `pjsip.conf` 0600). Nombres E.164
  dans `[identity]`, trunk dans `[phone_voice]`.
- Builder : units `serge-sms-receiver` (8787), `serge-asterisk`
  (user-space), `serge-voice-bridge` (8791), configs Asterisk,
  route ingress `sms.<domaine>`, CLI verrouillé au NPV.
- Runtime : `serge/sms/` (receiver → `SmsInbox`, OTP only),
  `serge/voice/` (`policy.py` mandat/consentement/horaires/quotas/kill-switch,
  `ledger.py` CDR, `bridge.py` originate gaté, `turn.py` AGI tour-par-tour
  livré comme repli robuste ; cible rework : speech-to-speech, point P5).
- Mandat `sandbox` : voix sortante coupée. `sergectl doctor` vérifie
  la complétude phone ; capabilities `voice_answer` / `voice_call`.

Un Serge sans téléphone (`phone_sms = false`, `phone_voice = false`)
reste un TOML valide et boot normalement — mais ce n'est plus le
défaut, et ce n'est plus 100 % des capacités.
