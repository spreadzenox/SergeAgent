# Option B — SMS + voix commerciale (tuto installateur)

Objectif : Serge **appelle et décroche** pour du commercial, tout en
gardant une SIM réelle pour les OTP et le relationnel. C'est l'Option A
**plus** un tronc SIP VoIP — pas un remplacement.

Vue d'ensemble : [`PHONE_OPTIONS.md`](PHONE_OPTIONS.md).
Prérequis : [`PHONE_SMS_ONLY.md`](PHONE_SMS_ONLY.md) installé et vérifié.

- Durée : ~1 h de SIP/Asterisk après l'Option A.
- Coût : Option A (2 €/mois) + DID ~2–6 €/mois + minutes
  (~0,01–0,04 €/min FR). Mois calme ≈ 5–15 € tout compris.
- Compétences : compte SIP + KYC, éditer deux fichiers Asterisk,
  ouvrir les ports SIP/RTP sur le VPS.

## Architecture cible

```
                         ┌── SIM 06/07 (Option A) ── OTP + relationnel humain
                         │
Serge (voix temps réel speech-to-speech, repli tour-par-tour)
    ↕ SIP/RTP local
Asterisk minimal sur le VPS (pjsip + dialplan + enregistrement)
    ↕ trunk SIP (TLS/SRTP si possible)
Opérateur VoIP ── DID NPV/géo ──↕ RTC ── prospects / clients
```

Deux numéros, deux rôles, zéro ambiguïté :

| Numéro | Rôle | Jamais |
| --- | --- | --- |
| 06/07 SIM (Option A) | OTP/2FA, rappels clients connus, inbound humain | Prospection automatisée (illégal + suspension SIM) |
| DID VoIP NPV (0162…) | Prospection automatisée conforme, voix agent sortante | OTP/2FA (rejet `nonFixedVoip`), urgence |

Si l'installateur ne retient qu'une phrase : **la SIM prouve que
Serge est quelqu'un, le SIP prouve que Serge est une entreprise.**

## Pourquoi VoIP-only ne suffit pas (limites dans le cadre Serge)

Cette section est le cœur du choix B = A + SIP. Chaque limite est
évaluée pour un Serge commercial.

### 1. OTP / création de comptes : rédhibitoire

Voir [`PHONE_OPTIONS.md`](PHONE_OPTIONS.md) : les plateformes
filtrent `nonFixedVoip` avant d'envoyer le code. Pour Serge, qui crée
des comptes (Google, WhatsApp Business, banques, marketplaces),
un VoIP-only = des créations qui échouent en silence ou des comptes
suspendus après coup. Aucun fournisseur SIP « FR » ne change le
`line_type`. **Mitigation : la SIM de l'Option A.** Non négociable.

### 2. Prospection : le VoIP est obligatoire, mais pas n'importe lequel

Le 06 est interdit en prospection ; le NPV est imposé pour les appels
automatisés. Donc pour la voix sortante commerciale, le VoIP n'est pas
une limitation — c'est **la seule forme légale**. La limitation, c'est
de croire qu'un DID « FR » quelconque suffit : il faut un numéro dont
l'opérateur garantit la présentation CLI autorisée (délégation
explicite du titulaire, exigée par l'ARCEP pour les NPV) et qui
survit à la certification 2026 (blocage de l'usurpation).

Concrètement : commander explicitement un NPV (ou un géo affecté à
l'entreprise avec délégation propre), pas « le premier 09 dispo ».

### 3. Taux de décroché : le prix de la légalité

Les Français ont appris les tranches NPV/09-démarchage : le taux de
décroché est structurellement plus bas qu'un 06. C'est un coût
commercial réel, pas un bug technique. L'inverse (prospecter en 06
ou en CLI usurpé) décroche mieux pendant quelques jours puis fait
couper la ligne et expose à la DGCCRF. Le kit ne documente pas de
contournement : horaires, quotas (4/30j), consentement/contrat,
Bloctel.

### 4. Réputation et certification CLI

Depuis janvier 2026, les opérateurs FR certifient l'identité de
l'appelant et bloquent les CLI non autorisés ; les signalements
« J'alerte l'ARCEP » ont doublé en 2025. Un trunk qui permet de
présenter n'importe quel CLI est un trunk à fuir : c'est le pattern
fraude. Exiger : CLI = le DID affecté, pas de rotation de numéros,
pas de spoofing « pour tester ».

### 5. SMS du trunk : ne pas compter dessus

En FR, le SMS d'un DID VoIP est souvent in-only, alphanumérique
(OACP), ou absent. Le P2P 06/07 n'existe pas en SIP. Tous les flux
SMS de Serge restent sur la SIM (Option A). Le trunk fait la voix,
point.

### 6. Souveraineté et support

- Zadarma : prix imbattables, SIP simple, mais siège hors FR,
  support variable.
- OVH Telecom : FR, conforme, intégration propre, tarifs corrects,
  API moins sexy.
- Twilio : meilleures API voix/IA (Media Streams), mais DID FR
  mobile = parcours dossier + semaines, prix US, données US.

Pour un kit FR commercial : **Zadarma ou OVH d'abord**, Twilio si on
veut la voix programmable la plus riche et qu'on accepte le coût et
le KYC. Aircall/Diabolocom = étape « centre d'appels », hors kit.

### 7. Qualité audio et urgence

Qualité SIP sur VPS correct : G.711/G.722, jitter maîtrisé, largement
assez pour un agent (le RTC est de toute façon en 8–16 kHz). Prévoir
quand même : pas d'appels d'urgence fiables en nomade, pas de garantie
RTC sur coupure internet, monitoring du trunk (OPTIONS ping,
alerte si registration perdue).

## Fournisseur : commander le bon numéro

1. Créer le compte au **nom légal de l'entreprise/owner** (KYC :
   pièce + justificatif, parfois KBIS). Le titulaire du numéro doit
   être le donneur d'ordre des campagnes.
2. Commander un DID **NPV** (tranches listées dans
   [`PHONE_OPTIONS.md`](PHONE_OPTIONS.md)) si l'usage est la
   prospection automatisée. Un géo 01–05 affecté à l'entreprise
   convient pour du relationnel sortant non automatisé.
3. Noter : serveur SIP, transport (TLS préféré), username,
   password, DID au format E.164. Serveur/username/DID partent dans
   le TOML (`[phone_voice]` + `[identity]`, non secrets) ; le password
   part dans le sidecar age (`sip_trunk_password`), **jamais** dans
   le TOML.
4. Vérifier le contrat : présentation CLI garantie ? TLS/SRTP ?
   Combien de canaux simultanés ? CDR et enregistrement légaux ?
   Conditions d'usage automatisé (certains CGV interdisent les
   robots d'appel — les lire avant de payer).

## Installation pas à pas

### 1. Asterisk sur le VPS (paquet + configs builder)

Le builder rend les configs (`config_root/asterisk/`) et les units
(`serge-asterisk`, `serge-voice-bridge`). Seul prérequis hôte :

```sh
sudo apt update && sudo apt install -y asterisk
```

Asterisk tourne en user-space (`asterisk -f -C ...`, pas de root,
pas de `/etc/asterisk`). SIP lié en loopback (`127.0.0.1:5061`,
registration sortante vers le trunk) ; RTP `10000-10100/udp` à
ouvrir en entrée (restreindre aux IP du trunk si possible). Le CLI
est verrouillé au NPV dans le dialplan, l'enregistrement systématique
(`state/voice/records/`).

Tester sans Serge d'abord : softphone (Linphone, sur le VPS)
enregistré comme `serge-agent` (même secret que le trunk, loopback
uniquement), appel entrant vers le DID (ça sonne ?), appel sortant
vers son propre mobile (le CLI affiché est bien le NPV ?).

### 2. L'agent Serge (cible : speech-to-speech ; livré : repli tour-par-tour)

Cible rework (matrice C, point P5) : **speech-to-speech temps réel** —
mêmes providers que la voix Mission Control (xAI Realtime en primary,
OpenAI Realtime en rollback), compté comme point LLM avec déclaration,
guards et repli. Le dialogue temps réel (barge-in, latence, naturel)
est supérieur au tour-par-tour pour la prospection vocale.

En attendant, le kit livre un **repli robuste** : un script AGI
(`serge/voice/turn.py`, AGI `turn.py`), pas un client SIP :

```
appel → Asterisk → AGI → Record 6 s → STT Whisper (openai_api_key)
→ chat OpenRouter → TTS → Playback → … (4 tours max)
→ menu DTMF « 1 = rappel » → répondeur 30-45 s → CDR
```

- Clés sidecar (inchangées, servent aussi au realtime) :
  `openai_api_key`, `xai_api_key`, `openrouter_api_key` (dialogue).
  Pas de nouvelle clé.
- Sans clé temps réel / échec mid-call : repli propre — `greeting.wav`
  owner si présent, sinon bip + répondeur. Jamais de silence,
  jamais de crash d'appel, jamais de raccrochage sec.
- Enregistrement + CDR + transcriptions + métadonnées par appel
  (`state/voice/`) : preuve, coaching, litiges, écoute owner via
  Mission Control. Rétention à fixer au mandat.
- Le tour-par-tour reste le plancher NPV-compatible (message
  préenregistré + enregistrement) : si le temps réel est indisponible,
  l'appel dégrade, il ne meurt pas.

### 3. Garde-fous commerciaux (livrés dans `serge/voice/`)

La voix sortante est une mutation externe, refus par défaut :

- [x] `sandbox` : **aucun** appel sortant (mandat + broker).
- [x] Live : lun–ven 10h–13h / 14h–20h heure de Paris hors fériés FR,
  max 4 tentatives / 30 j / destinataire, base consentement/contrat
  obligatoire (`serge/voice/bridge.py consent-grant`), révocation immédiate.
- [x] Blocklist (Bloctel, « ne plus appeler ») : refus avant
  composition (`serge/voice/bridge.py block-add`).
- [x] CLI verrouillé au NPV (broker + dialplan). Aucun paramètre
  d'appel ne peut le changer.
- [x] Kill-switch (fichier `KILL_SWITCH`) + `external_actions_enabled`
  : stoppe tout sortant. Idempotence par `request_id`.
- [ ] Enregistrement annoncé (« cet appel peut être enregistré… »)
  selon les obligations applicables + rétention bornée — **à écrire
  dans le message d'accueil par l'owner**.
- [ ] Plafond €/jour chez le fournisseur — **à configurer côté trunk**,
  en plus du `max_calls_per_day` côté Serge.

### 4. Et la SIM dans tout ça ? (5 min)

Rien ne change à l'Option A : elle continue de recevoir les OTP et
porte le relationnel humain. Deux règles de routage à écrire et à
afficher dans le kit :

1. **Prospect inconnu → NPV.** Jamais le 06.
2. **Client connu qui rappelle / conversation en cours → 06.**
   Le 06 rappelle un humain, le NPV appelle un fichier.

Les deux numéros sont dans le TOML `[identity]` (champs non
secrets `phone_sms_number`, `phone_voice_number`, schématisés) pour
que les logs, le broker et le dialplan sachent qui est qui.

## Vérification de fin

1. Inbound DID → agent décroche, parle, transcrit, enregistre.
2. Outbound vers son propre mobile → CLI = NPV, audio propre dans
   les deux sens, MixMonitor présent.
3. OTP vers la SIM → toujours reçu (non-régression Option A).
4. Hors plage horaire → sortant refusé avec log explicite.
5. Kill-switch → file sortante vidée en < 60 s.
6. Facture trunk du mois test : conforme au plafond, CDR cohérents
   avec les logs Serge.

## Dépannage

| Symptôme | Cause probable | Fix |
| --- | --- | --- |
| Registration trunk perdue | Mot de passe, IP allowlistée, TLS mal négocié | Logs Asterisk `pjsip show registrations`, requalifier le trunk, fallback UDP temporaire pour isoler TLS. |
| Audio un seul sens | NAT/RTP, ports 10000+ fermés | `rtp.conf` + firewall, `external_media_address` / `external_signaling_address` sur le VPS. |
| CLI affiché ≠ NPV | Trunk qui réécrit ou refuse la présentation | Support fournisseur + vérifier la délégation du numéro. Ne pas « essayer » d'autres CLI. |
| Agent muet puis timeout | Realtime/STT lent ou clé HS | Tester la feature `voice` hors appel, timeouts + message de repli. |
| Correspondants « je n'ai rien compris » | TTS trop rapide / pas de tour de parole | Ralentir, phrases courtes, barge-in, proposer le DTMF. |
| Facture anormale | Boucle de composition / retry agressif | Plafonds, backoff, alerte €/jour. Couper le trunk avant de debugger. |

## Coûts et limites assumées

- DID + minutes : prévoir 5–15 €/mois en usage calme, plus en
  campagne. Le poste qui explose, c'est les minutes, pas le DID.
- Taux de décroché NPV < 06 : assumé, légal, non contourné.
- Pas d'OTP sur le DID, pas d'urgence fiable, pas de « un seul
  numéro qui fait tout ».
- La SIM reste un point de fragilité physique (voir Option A).
  Le trunk est un point de fragilité contractuelle (CGV, KYC,
  suspension). Les deux sont monitorés, aucun n'est critique seul :
  sans trunk, Serge reçoit encore les OTP ; sans SIM, Serge appelle
  encore (mais ne crée plus de comptes).

## Encore à faire (hors kit)

- Monitoring runtime : heartbeat SMS (« silence radio »), alerte
  registration trunk perdue, €/jour vs CDR.
- Annonce légale d'enregistrement dans les messages d'accueil.
- Speech-to-speech temps réel (cible rework, point P5 de la matrice C —
  providers xAI/OpenAI Realtime comme la voix Mission Control). Le
  tour-par-tour livré devient le repli dégradé.
- `request_voice_call` dans l'ActionBroker central (aujourd'hui :
  broker voix dédié, même pattern que `SmsInbox`).
