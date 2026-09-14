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

- [ ] **Invocation LLM prospection avec compte.** Un canal parmi LinkedIn / Reddit / forum / WhatsApp / Google Ads. Formats de sortie typés + digestion en base (contacts, touches, pas du texte libre).

### Déjà ouvert, pas encore recouvert par la machine ci-dessus

- [ ] **Outils que le jugement peut vraiment presser (hors web).** Chercher dans la mémoire (`memory_search` existe, pas enchaîné aux jugements). Demander une nouvelle capacité plutôt qu’inventer (`demande_capacite` encore `prevu`).

## Plus tard

_(idées proposées, pas encore validées par Julien)_
