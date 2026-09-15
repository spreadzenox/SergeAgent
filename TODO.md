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

- [x] **Pages vraiment lues en base.** Projecteur `listen_docs` : vide = « Aucune page en base ». `mc-demo.py` peut semer, le runtime non. LLM écoute lite/lourde = archi.

### Comptes et identité

- [x] **Brancher `accounts_standing` (table déjà en base).** Pas de seconde table. Writer `enregistrer_compte` (v13 : `login` / `password` en clair). Ce sont des comptes créés par Serge, sans valeur hors de Serge. `secret_ref` n’est plus le coffre.

- [ ] **Dossier de session par compte.** La colonne `profile_path` pointe un dossier navigateur (cookies, etc.), rangé et unique par ligne. Quand deux usages du même compte se suivent de près, on réouvre ce dossier : c’est le geste le plus proche d’un humain qui n’a pas fermé son onglet. Ce n’est pas un keepalive permanent (ça, c’est un comportement de bot). Les trois tools web doivent accepter ce dossier. *Dépend de : tools web ; brancher `accounts_standing`.*

- [x] **Santé du compte, appliquée, pas affichée pour décorer.** Garde `serge/comptes_sante.py` : `etat` (prévient) / `autoriser` (refuse par code : `inconnu`, `inactif`, `pause`, `capital`) / `consommer` (débit) / `recuperer` (crédit idle). Barème dans `policy.standing`. `last_used_at` (v14). Insister ne passe pas. Garde posée ; aucun adaptateur prod ne l’appelle encore (ticket ci-dessous).

- [ ] **Appelants de la garde de santé.** Aucun writer de compte (LinkedIn, publication lieu, tools web) n’existe encore, donc personne n’appelle `autoriser` / `consommer`. Le jour où un de ces writers part, le merge est refusé s’il n’appelle pas la garde. *Dépend de : santé du compte.*

- [ ] **Tool agent « créer un compte ».** Mobilisable à la main dans MC et appelable par les invocations LLM qui ont ce tool. 2FA **100 % autonome** (Serge lit mail/SMS lui-même). Captcha = stream humain (opérateur MC). À la création : login et mot de passe en clair dans `accounts_standing`, plus un dossier de session vide prêt à servir. *Dépend de : tools web ; stream captcha MC ; tool boîte mail/SMS ; `accounts_standing` ; dossier de session ; identity basique.*

- [x] **Identity basique (tool + page MC).** Lecteur `identite_serge()`, tool `identity_basique`, page `#/identite`, édition = `ecrire_identite` (réécrit l’instance). Jonction `voice_dialog` + `draft_price`.

- [x] **Identity advanced (tool `prevu` + même page, volet à part).** `identity_advanced` (`prevu`, `montre_partout=0`). IBAN + adresse sur la même page. Pas de PAN.

- [x] **Tool boîte mail / SMS (brut + historique).** Tool `boite_serge`. SMS inbox stocke sender + body. 2FA lisible sans GUICHET.

- [x] **Appelants de `upsert_trace`.** `create_contact` avec e-mail pose `venue=email` / `handle=email`. Observe / pont écoute restent à câbler quand ces flux créent un contact (ticket archi / pont).

- [x] **2. SMS sortant — théâtre retiré (pas de writer).** Le séquenceur n’enfile plus `sms.send`. L’îlot MC compte les **reçus**, pas des envois fantômes. Quotas policy restent pour le jour d’un writer. *Mise de côté : quel fournisseur pour un vrai envoi.*

### Tools web (remplacent le stub unique `navigateur`)

- [ ] **Tool web ultra-light Chromium.**
- [ ] **Tool web medium Selenium.**
- [ ] **Tool web heavy Browserbase** (la clé est déjà dans les secrets). Un contrat commun, trois implémentations. Le stub `navigateur` (`etat: prevu`) disparaît quand le premier des trois est branché — pas un quatrième tool. Chaque tool doit pouvoir ouvrir le `profile_path` du compte.

### Prospection avec compte

- [ ] **Invocation LLM prospection avec compte.** Sortie typée (qui, quel acte, quel texte) — le writer est l’adaptateur du canal, pas le LLM. Digestion en base (`contacts`, `touches`). Un canal = écriture vers un **tiers** (pas Julien). Email et voix sont déjà au catalogue (`canaux` + `brique_canaux`, v11). Discord owner n’en est pas un.

- [x] **Stockage des contacts par canal.** `upsert_trace` + colonnes `venue` / `handle` / `profile_url` (v12). Deux lieux, deux lignes. Pas de fusion automatique. `create_contact` avec e-mail pose la trace e-mail.

### Canaux manquants (théâtre déjà là, writer absent)

Chaque canal fini = semence `serge/canaux.py` + jonctions n-n + `code_path` du writer + kind worker + guards + SHA (`catalogue_lock.py`) + fiche MC. Pas de jauge / quota / îlot sans writer (R7). Ordre = priorité (le plus menti d’abord).

- [ ] **1. LinkedIn.** Le plus de théâtre. Déjà là sans writer : quotas `linkedin_connect_per_day` / `linkedin_inmail_per_month` (`config/policy.yaml` + UI Policy), jauge En direct qui compte des `touches` `channel='linkedin'` (personne n’en écrit), commentaire « phase 2 » dans `config/sequences.yaml`, archi funnel (invites / InMail / accepts), ticket `PUBLICATION` qui cite LinkedIn. Les guards (`KNOWN_CHANNELS`) ne connaissent que `email` / `sms` / `voice` : un `linkedin.send` explose aujourd’hui. À faire : adaptateur déterministe (compte `accounts_standing`, tool web, cooldown / capital), kind `linkedin.send`, étendre les guards, écrire de vraies `touches`, brancher le catalogue. Jugement = l’invocation prospection (ci-dessus), pas le clic. *Dépend de : tools web ; `accounts_standing` ; dossier de session ; santé du compte ; stream captcha ; tool boîte mail/SMS (2FA compte) ; identity basique ; stockage des contacts par canal.*

- [x] **2. SMS sortant.** Théâtre d’envoi retiré (séquenceur + îlot). Writer réel = attente fournisseur (section archi).

- [ ] **3. WhatsApp.** Une case opt-in (`consent.opt_in_channels` + UI Policy) et un paragraphe d’archi (collé au SMS : template, STOP, opt-out). Zéro client, zéro kind, zéro touche. À faire : adaptateur (API / outil web selon le choix) + opt-in vraiment lu à l’envoi + catalogue. Ne pas inventer une jauge avant le writer. *Dépend de : tools web et/ou tool boîte mail/SMS si le compte se crée tout seul ; `accounts_standing` si session web.*

- [x] **4. Ads (Google / Meta / LinkedIn / Reddit).** Documenté `prevu` : `family='ads'` sans writer ni jauge de dépense. Adaptateur / ledger = archi.

- [ ] **5. Publication lieu (Reddit / forums / SEO).** Ticket `PUBLICATION` (« drafts Reddit/LinkedIn/forums »), famille campagne `place`, comptes démo `venue='reddit'` (`accounts_standing`). Rien ne poste. L’écoute RSS Reddit est de la **lecture** (`listen.collect`), pas un canal. À faire : writer de publication (ticket approuvé → post réel), compte + cooldown, catalogue (reddit / forum, pas un fourre-tout). Insta / Facebook : aucun câble, on ne les invente pas ici. *Dépend de : tools web ; `accounts_standing` ; dossier de session ; santé du compte ; stream captcha si le lieu challenge ; stockage des contacts par canal.*

### Captcha (humain) et boîte Serge (autonome)

- [ ] **Tool stream captcha → Mission Control.** Le navigateur déjà ouvert streame son écran (pas un second browser). Ticket `GUICHET` Discord avec `lien_stream` = URL MC (pas la vidéo dans Discord : pas de PII sur Discord). Keepalive auto jusqu’à expiration du ticket. Accessible **téléphone et ordinateur** pour tout opérateur qui a le token MC **et** Discord. Pause de la tâche jusqu’à « c’est fait » / abandon / expiry. *Dépend de : tools web (Chromium / Selenium / Browserbase) — le stream n’a rien à filmer sinon.*

- [x] **Tool boîte mail / SMS (brut + historique).** `boite_serge` + inbox SMS en brut.

### Ponts entre étapes (manuel d’abord, auto ensuite)

Un seul mécanisme pour tous les passages (écoute → contacts, contacts → séquence, essai → scale, etc.). Pas un pont bricolé par étape.

- [ ] **Bouton MC « passer à la suite ».** L’opérateur déclenche à la main le pont : l’étape N a produit des résultats, on les verse dans l’étape N+1. C’est le mode par défaut. Rien ne s’enchaîne tout seul tant que personne n’a pressé.

- [ ] **Kill switch « passage automatique ».** OFF = manuel seulement. ON = un tick runner régulier écoute si l’étape précédente a de **nouveaux** résultats et déclenche le même pont que le bouton, tout seul. Le bouton manuel reste toujours là (force un passage tout de suite). Coupe-circuit : si l’étape cible ou le kind est déjà coupé, le tick ne passe pas.

- [ ] **Tick runner des ponts.** Un kind dédié (pas un cron hors catalogue). Idempotent : un résultat déjà versé n’est pas rejoué. Visible dans En direct comme les autres kinds.

### Déjà ouvert, pas encore recouvert par la machine ci-dessus

- [ ] **Outils que le jugement peut vraiment presser (hors web).** `memory_search` existe (jonction couche 5) mais `run_point` n’a pas de boucle d’outils — archi. `demande_capacite` encore `prevu`.

## En attente d’une décision d’architecture

Mis de côté (on n’invente pas le contrat) :

- Onglet Écoute + table dédiée (forme du sac de niches).
- LLM pré-prospection lite / lourde (nouveau point vs extension de `cluster_demand`).
- Tools web Chromium / Selenium / Browserbase (contrat commun d’API outil).
- Dossier de session, captcha stream, créer un compte (dépendent des tools web).
- LinkedIn / WhatsApp / publication lieu (fournisseur + writer).
- Ads writer / ledger de dépense (la family est documentée `prevu`).
- Ponts entre étapes (ce que « verser » veut dire pour chaque couple).
- SMS sortant writer (quel opérateur).
- `demande_capacite` runtime (que crée le ticket, quel kind).
- `memory_search` pressé par le jugement : boucle d’outils dans `chat()` / `run_point` (schéma JSON, tours, refus).

## Plus tard

_(idées proposées, pas encore validées par Julien)_
