# À faire — Mission Control / Serge

Liste vivante. Julien enrichit au fil des reviews. Pas un changelog.

## Ouvert

### Machine d’écoute (première étape, lancée à la main)

- [ ] **Onglet Mission Control « Écoute ».** Lancer des campagnes d’écoute : input = niches en texte libre, interprétées par les invocations LLM d’écoute. Table dédiée (pas `campaigns` outreach). C’est le démarreur de la machine.

- [ ] **Invocation LLM pré-prospection lite (sans compte).** Sniffer le web public : Reddit, forums spécialisés, articles, tout ce qui est lisible sans login. Ça s’ajoute au collecteur RSS déterministe déjà là (`listen.collect`) — ça ne le remplace pas.

- [ ] **Invocation LLM pré-prospection lourde (avec compte).** Retrieval sur les plateformes qui exigent un login (LinkedIn, Facebook, Instagram, etc.). Lit les comptes dans `accounts_standing`, n’en invente pas.

- [ ] **Pages vraiment lues en base.** Miroir live de ce que les campagnes d’écoute ramassent vraiment (pas 2 flux RSS de démo). Si ce n’est pas encore collecté, le dire clairement plutôt que de feindre.

### Comptes et identité

- [ ] **Brancher `accounts_standing` (table déjà en base).** Pas de seconde table. Writer production (aujourd’hui : semence démo / tests seulement) + tous les agents / invocations qui ont besoin d’un compte lisent et mettent à jour cette table (rôle, `profile_path`, `last_login_at`, cooldown, capital).

- [ ] **Tool agent « créer un compte ».** Mobilisable à la main dans MC et appelable par les invocations LLM qui ont ce tool. Accès aux tools web (chromium / selenium / Brave), au stream captcha, à la lecture email / SMS pour la 2FA, et à l’adresse mail + téléphone de Serge.

### Tools web (remplacent le stub unique `navigateur`)

- [ ] **Tool web ultra-light Chromium.**
- [ ] **Tool web medium Selenium.**
- [ ] **Tool web heavy Brave** (clé déjà sur le VPS). Un contrat commun, trois implémentations. Le stub `navigateur` (`etat: prevu`) disparaît quand le premier des trois est branché — pas un quatrième tool.

### Prospection avec compte

- [ ] **Invocation LLM prospection avec compte.** Sortie typée (qui, quel acte, quel texte) — le writer est l’adaptateur du canal, pas le LLM. Digestion en base (`contacts`, `touches`). Un canal = écriture vers un **tiers** (pas Julien). Email et voix sont déjà au catalogue (`canaux` + `brique_canaux`, v11). Discord owner n’en est pas un.

### Canaux manquants (théâtre déjà là, writer absent)

Chaque canal fini = semence `serge/canaux.py` + jonctions n-n + `code_path` du writer + kind worker + guards + SHA (`catalogue_lock.py`) + fiche MC. Pas de jauge / quota / îlot sans writer (R7). Ordre = priorité (le plus menti d’abord).

- [ ] **1. LinkedIn.** Le plus de théâtre. Déjà là sans writer : quotas `linkedin_connect_per_day` / `linkedin_inmail_per_month` (`config/policy.yaml` + UI Policy), jauge En direct qui compte des `touches` `channel='linkedin'` (personne n’en écrit), commentaire « phase 2 » dans `config/sequences.yaml`, archi funnel (invites / InMail / accepts), ticket `PUBLICATION` qui cite LinkedIn. Les guards (`KNOWN_CHANNELS`) ne connaissent que `email` / `sms` / `voice` : un `linkedin.send` explose aujourd’hui. À faire : adaptateur déterministe (compte `accounts_standing`, tool web, cooldown / capital), kind `linkedin.send`, étendre les guards, écrire de vraies `touches`, brancher le catalogue. Jugement = l’invocation prospection (ci-dessus), pas le clic.

- [ ] **2. SMS sortant.** L’entrée existe (téléphone → `serge/sms/receiver.py` + inbox, OTP hashé). La sortie est **refusée exprès** (`outbound_sms_enabled: False` dans `serge/sms/inbox.py`). Pourtant ça fait déjà semblant : guards `sms`, séquenceur qui enfilerait `sms.send` (pas de worker), quotas `sms_per_sender_per_min` / `sms_global_per_min`, opt-in policy, îlot Système « SMS » qui compte des envois. À faire : writer réel ou retirer le théâtre (quotas / îlot / kind fantôme) jusqu’au writer. Canal catalogue seulement quand ça sort vers un tiers.

- [ ] **3. WhatsApp.** Une case opt-in (`consent.opt_in_channels` + UI Policy) et un paragraphe d’archi (collé au SMS : template, STOP, opt-out). Zéro client, zéro kind, zéro touche. À faire : adaptateur (API / outil web selon le choix) + opt-in vraiment lu à l’envoi + catalogue. Ne pas inventer une jauge avant le writer.

- [ ] **4. Ads (Google / Meta / LinkedIn / Reddit).** `campaigns.family = 'ads'` existe, `ouvrir_essai` peut créer une campagne ads. L’archi décrit impressions / clics / budget. Pas d’API, pas de dépense, pas de créa. C’est un canal (écrire une créa vers la plateforme, donc vers des tiers). À faire : un adaptateur par régie ou un contrat commun + `code_path`, ledger de dépense relié à `transactions` / budget campagne, semence catalogue. Une `family` sans writer = théâtre : soit on branche, soit on documente `prevu` sans jauge live.

- [ ] **5. Publication lieu (Reddit / forums / SEO).** Ticket `PUBLICATION` (« drafts Reddit/LinkedIn/forums »), famille campagne `place`, comptes démo `venue='reddit'` (`accounts_standing`). Rien ne poste. L’écoute RSS Reddit est de la **lecture** (`listen.collect`), pas un canal. À faire : writer de publication (ticket approuvé → post réel), compte + cooldown, catalogue (reddit / forum, pas un fourre-tout). Insta / Facebook : aucun câble, on ne les invente pas ici.

### Ponts entre étapes (manuel d’abord, auto ensuite)

Un seul mécanisme pour tous les passages (écoute → contacts, contacts → séquence, essai → scale, etc.). Pas un pont bricolé par étape.

- [ ] **Bouton MC « passer à la suite ».** L’opérateur déclenche à la main le pont : l’étape N a produit des résultats, on les verse dans l’étape N+1. C’est le mode par défaut. Rien ne s’enchaîne tout seul tant que personne n’a pressé.

- [ ] **Kill switch « passage automatique ».** OFF = manuel seulement. ON = un tick runner régulier écoute si l’étape précédente a de **nouveaux** résultats et déclenche le même pont que le bouton, tout seul. Le bouton manuel reste toujours là (force un passage tout de suite). Coupe-circuit : si l’étape cible ou le kind est déjà coupé, le tick ne passe pas.

- [ ] **Tick runner des ponts.** Un kind dédié (pas un cron hors catalogue). Idempotent : un résultat déjà versé n’est pas rejoué. Visible dans En direct comme les autres kinds.

### Déjà ouvert, pas encore recouvert par la machine ci-dessus

- [ ] **Outils que le jugement peut vraiment presser (hors web).** Chercher dans la mémoire (`memory_search` existe, pas enchaîné aux jugements). Demander une nouvelle capacité plutôt qu’inventer (`demande_capacite` encore `prevu`).

## Plus tard

_(idées proposées, pas encore validées par Julien)_
