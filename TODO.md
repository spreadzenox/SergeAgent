# À faire — Mission Control / Serge

Liste vivante. Julien enrichit au fil des reviews. Pas un changelog.

**Dépendances.** Si A a besoin d’un B déjà dans cette liste, on l’écrit
sur A (`dépend de : …`). Pas de feature orpheline qui suppose un autre
chantier « évident ».

## Ouvert

### Machine d’écoute (première étape, lancée à la main)

- [ ] **Onglet Mission Control « Écoute ».** Lancer des campagnes d’écoute : input = niches en texte libre, interprétées par les invocations LLM d’écoute. Table dédiée (pas `campaigns` outreach). C’est le démarreur de la machine.

- [ ] **Invocation LLM pré-prospection lite (sans compte).** Sniffer le web public : Reddit, forums spécialisés, articles, tout ce qui est lisible sans login. Ça s’ajoute au collecteur RSS déterministe déjà là (`listen.collect`) — ça ne le remplace pas.

- [ ] **Invocation LLM pré-prospection lourde (avec compte).** Retrieval sur les plateformes qui exigent un login (LinkedIn, Facebook, Instagram, etc.). Lit les comptes dans `accounts_standing`, n’en invente pas.

- [ ] **Pages vraiment lues en base.** Miroir live de ce que les campagnes d’écoute ramassent vraiment (pas 2 flux RSS de démo). Si ce n’est pas encore collecté, le dire clairement plutôt que de feindre.

### Comptes et identité

- [ ] **Brancher `accounts_standing` (table déjà en base).** Pas de seconde table. Writer production (aujourd’hui : semence démo / tests seulement) + tous les agents / invocations qui ont besoin d’un compte lisent et mettent à jour cette table (rôle, `profile_path`, `last_login_at`, cooldown, capital).

- [ ] **Tool agent « créer un compte ».** Mobilisable à la main dans MC et appelable par les invocations LLM qui ont ce tool. 2FA **100 % autonome** (Serge lit mail/SMS lui-même). Captcha = stream humain (opérateur MC). *Dépend de : tools web ; stream captcha MC ; tool boîte mail/SMS ; `accounts_standing` ; identity basique.*

- [ ] **Identity basique (tool + page MC).** Pas de table : source = `[identity]` + `[mailbox]` + secrets. Lecteur unique `identite_serge()` — interdit d’ouvrir le TOML ou d’inventer un from dans un prompt. Champs : email, prénom, nom, pseudo (défaut ; le handle par plateforme reste `accounts_standing`), n° 2FA (06/07, SMS seulement), n° DID (appels clients), SIRET. Page MC dédiée = miroir de cette source (édition = réécrit l’instance, pas une copie). Token MC = confiance absolue (proches, pas de 2e facteur). Jonction explicite sur les points qui créent un compte / parlent / encaissent — pas « tous les LLM ». *Dépend de : rien d’autre dans cette liste (l’instance a déjà les deux tél + le mail). « Créer un compte », boîte mail/SMS et LinkedIn en dépendent.*

- [ ] **Identity advanced (tool `prevu` + même page, volet à part).** Basique + IBAN + adresse de facturation. Personne ne l’appelle tant qu’un acte n’est pas nommé. `montre_partout=0`. **Pas de PAN/CVV en clair.** Plus tard : intermédiaire type PayPal / Google Pay (token, pas les credentials). Même page MC, même confiance token. *Dépend de : identity basique (même source, mêmes champs de tête).*

### Tools web (remplacent le stub unique `navigateur`)

- [ ] **Tool web ultra-light Chromium.**
- [ ] **Tool web medium Selenium.**
- [ ] **Tool web heavy Brave** (clé déjà sur le VPS). Un contrat commun, trois implémentations. Le stub `navigateur` (`etat: prevu`) disparaît quand le premier des trois est branché — pas un quatrième tool.

### Prospection avec compte

- [ ] **Invocation LLM prospection avec compte.** Sortie typée (qui, quel acte, quel texte) — le writer est l’adaptateur du canal, pas le LLM. Digestion en base (`contacts`, `touches`). Un canal = écriture vers un **tiers** (pas Julien). Email et voix sont déjà au catalogue (`canaux` + `brique_canaux`, v11). Discord owner n’en est pas un.

### Canaux manquants (théâtre déjà là, writer absent)

Chaque canal fini = semence `serge/canaux.py` + jonctions n-n + `code_path` du writer + kind worker + guards + SHA (`catalogue_lock.py`) + fiche MC. Pas de jauge / quota / îlot sans writer (R7). Ordre = priorité (le plus menti d’abord).

- [ ] **1. LinkedIn.** Le plus de théâtre. Déjà là sans writer : quotas `linkedin_connect_per_day` / `linkedin_inmail_per_month` (`config/policy.yaml` + UI Policy), jauge En direct qui compte des `touches` `channel='linkedin'` (personne n’en écrit), commentaire « phase 2 » dans `config/sequences.yaml`, archi funnel (invites / InMail / accepts), ticket `PUBLICATION` qui cite LinkedIn. Les guards (`KNOWN_CHANNELS`) ne connaissent que `email` / `sms` / `voice` : un `linkedin.send` explose aujourd’hui. À faire : adaptateur déterministe (compte `accounts_standing`, tool web, cooldown / capital), kind `linkedin.send`, étendre les guards, écrire de vraies `touches`, brancher le catalogue. Jugement = l’invocation prospection (ci-dessus), pas le clic. *Dépend de : tools web ; `accounts_standing` ; stream captcha ; tool boîte mail/SMS (2FA compte) ; identity basique.*

- [ ] **2. SMS sortant.** L’entrée existe (téléphone → `serge/sms/receiver.py` + inbox, OTP hashé). La sortie est **refusée exprès** (`outbound_sms_enabled: False` dans `serge/sms/inbox.py`). Pourtant ça fait déjà semblant : guards `sms`, séquenceur qui enfilerait `sms.send` (pas de worker), quotas `sms_per_sender_per_min` / `sms_global_per_min`, opt-in policy, îlot Système « SMS » qui compte des envois. À faire : writer réel ou retirer le théâtre (quotas / îlot / kind fantôme) jusqu’au writer. Canal catalogue seulement quand ça sort vers un tiers.

- [ ] **3. WhatsApp.** Une case opt-in (`consent.opt_in_channels` + UI Policy) et un paragraphe d’archi (collé au SMS : template, STOP, opt-out). Zéro client, zéro kind, zéro touche. À faire : adaptateur (API / outil web selon le choix) + opt-in vraiment lu à l’envoi + catalogue. Ne pas inventer une jauge avant le writer. *Dépend de : tools web et/ou tool boîte mail/SMS si le compte se crée tout seul ; `accounts_standing` si session web.*

- [ ] **4. Ads (Google / Meta / LinkedIn / Reddit).** `campaigns.family = 'ads'` existe, `ouvrir_essai` peut créer une campagne ads. L’archi décrit impressions / clics / budget. Pas d’API, pas de dépense, pas de créa. C’est un canal (écrire une créa vers la plateforme, donc vers des tiers). À faire : un adaptateur par régie ou un contrat commun + `code_path`, ledger de dépense relié à `transactions` / budget campagne, semence catalogue. Une `family` sans writer = théâtre : soit on branche, soit on documente `prevu` sans jauge live.

- [ ] **5. Publication lieu (Reddit / forums / SEO).** Ticket `PUBLICATION` (« drafts Reddit/LinkedIn/forums »), famille campagne `place`, comptes démo `venue='reddit'` (`accounts_standing`). Rien ne poste. L’écoute RSS Reddit est de la **lecture** (`listen.collect`), pas un canal. À faire : writer de publication (ticket approuvé → post réel), compte + cooldown, catalogue (reddit / forum, pas un fourre-tout). Insta / Facebook : aucun câble, on ne les invente pas ici. *Dépend de : tools web ; `accounts_standing` ; stream captcha si le lieu challenge.*

### Captcha (humain) et boîte Serge (autonome)

- [ ] **Tool stream captcha → Mission Control.** Le navigateur déjà ouvert streame son écran (pas un second browser). Ticket `GUICHET` Discord avec `lien_stream` = URL MC (pas la vidéo dans Discord : pas de PII sur Discord). Keepalive auto jusqu’à expiration du ticket. Accessible **téléphone et ordinateur** pour tout opérateur qui a le token MC **et** Discord. Pause de la tâche jusqu’à « c’est fait » / abandon / expiry. *Dépend de : tools web (Chromium / Selenium / Brave) — le stream n’a rien à filmer sinon.*

- [ ] **Tool boîte mail / SMS (brut + historique).** Un tool catalogue, lecture. Pour chaque message : corps **brut**, heure, expéditeur, destinataire, et l’historique si besoin. 2FA : Serge lit le code **tout seul** (pas de GUICHET). Aujourd’hui le broker SMS (`serge/sms/inbox.py`) **jette** le corps et l’expéditeur, ne garde que hash + OTP extrait — c’était une minimisation PII d’install, **plus la règle produit**. Il faut inverser : stocker le brut (ledger SMS + mail déjà pollé). Le 06/07 reste la ligne OTP ; le DID voix reste la prospection. *Dépend de : rien d’autre dans cette liste (receiver SMS + `email.poll` existent). « Créer un compte » et LinkedIn en dépendent.*

### Ponts entre étapes (manuel d’abord, auto ensuite)

Un seul mécanisme pour tous les passages (écoute → contacts, contacts → séquence, essai → scale, etc.). Pas un pont bricolé par étape.

- [ ] **Bouton MC « passer à la suite ».** L’opérateur déclenche à la main le pont : l’étape N a produit des résultats, on les verse dans l’étape N+1. C’est le mode par défaut. Rien ne s’enchaîne tout seul tant que personne n’a pressé.

- [ ] **Kill switch « passage automatique ».** OFF = manuel seulement. ON = un tick runner régulier écoute si l’étape précédente a de **nouveaux** résultats et déclenche le même pont que le bouton, tout seul. Le bouton manuel reste toujours là (force un passage tout de suite). Coupe-circuit : si l’étape cible ou le kind est déjà coupé, le tick ne passe pas.

- [ ] **Tick runner des ponts.** Un kind dédié (pas un cron hors catalogue). Idempotent : un résultat déjà versé n’est pas rejoué. Visible dans En direct comme les autres kinds.

### Déjà ouvert, pas encore recouvert par la machine ci-dessus

- [ ] **Outils que le jugement peut vraiment presser (hors web).** Chercher dans la mémoire (`memory_search` existe, pas enchaîné aux jugements). Demander une nouvelle capacité plutôt qu’inventer (`demande_capacite` encore `prevu`).

## Plus tard

_(idées proposées, pas encore validées par Julien)_
