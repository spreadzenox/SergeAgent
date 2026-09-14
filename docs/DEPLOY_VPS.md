# Déploiement VPS (`julien-vps`)

Merge sur `main` → le runner **self-hosted** sur le VPS exécute
`scripts/serge-deploy.py`. Premier coup : install vierge. Ensuite :
overlay du SHA + restart des units déjà actives.

Les secrets restent **sur le VPS**, jamais dans GitHub (dépôt public).

Détail lint / tests / CI déterministe : [DEV_TOOLING.md](DEV_TOOLING.md).

## Ce que fait le job

Workflow : [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml).

- Déclenché **uniquement** par `push` sur `main` (jamais `pull_request`,
  jamais les forks).
- `runs-on: [self-hosted, linux, julien-vps]`.
- `permissions: contents: read`. Aucun secret Actions.
- Script : `python3 scripts/serge-deploy.py`.

Racine `system_root` **vide** →
`scripts/serge-install.py --non-interactive --no-enable-units
--confirm-live-instance-id julien-vps`, puis
`systemctl --user enable --now` **les units user** des features on
(pipeline, MC, Discord, SMS, Stripe, voix, Asterisk). Si
`ingress.listen = privileged` (ports 80/443), Caddy est une unit
**system** : le job fait `sudo -n cp` vers `/etc/systemd/system` puis
`sudo systemctl enable --now`. Pas de denylist.

Racine **déjà peuplée** → `kit/update.py` (git archive par-dessus,
`state/` / `queue/` / `logs/` / `reports/` / `evidence/` intacts, canon
non recréé), réécrit les units, `daemon-reload`, restart des units
déjà actives.

Pipeline : `scripts/serge-runner.py --once` derrière `flock` sur
`state/pipeline.lock`. Plus de `sergectl`, plus de daily-report, plus de
burn-in. Le digest reste Discord `📣-digest` + MC
(`tickets.digest_hour`).

Ingress : `serge/ingress/caddy.py` (inventaire + Caddyfile). Caddy est
le serveur.

## Variables sur le VPS (pas GitHub)

Le service runner doit exporter :

| Variable | Rôle |
|---|---|
| `SERGE_DEPLOY_INSTANCE_FILE` | Couple live (`…/serge.instance.toml`) |
| `SERGE_DEPLOY_MANDATE` | Mandat live (pas le mandat mort Julien) |
| `SERGE_AGE_IDENTITY` | Identité age pour `serge.secrets.age` |

Optionnel : `SERGE_DEPLOY_CONFIRM_LIVE_ID` (défaut `julien-vps`).

Fichier `.env` du runner, ou `Environment=` du unit systemd du runner.
Rien de tout ça dans Settings → Secrets du dépôt.

## Runner self-hosted

À faire **ensemble** sur le VPS (après merge du code, pas avant) :

1. User `serge`, Python ≥ 3.12, deps du repo (`PyYAML`, …).
2. Télécharger l’archive runner GitHub, `./config.sh` avec un token
   repo (Settings → Actions → Runners), labels **`linux`** et
   **`julien-vps`**.
3. `./svc.sh install && ./svc.sh start`. Le job attend Idle : si le
   runner n’est pas là, le deploy reste en file.

Le VPS est déjà sur Tailscale. Pas besoin d’ouvrir GitHub vers le net
public : le runner **sort** vers `github.com`.

Dépôt public + runner self-hosted : un workflow `pull_request` pourrait
faire tourner le code d’un fork **sur le VPS**. C’est pour ça que
`deploy.yml` n’écoute que `main`.

## Couple live (pas le couple WSL)

Le couple WSL (`instance_id=wsl`, chemins `/home/jpesquet/…`,
`mode=sandbox`) **ne se copie pas**. Le builder refuse une racine
non vide et les chemins live sans
`--confirm-live-instance-id julien-vps`.

À construire sur le VPS (ensemble) :

- `instance_id=julien-vps`, `mode=live`
- chemins `/home/serge/…`
- sidecar `serge.secrets.age` + identité age
- mandat kit vivant (pas un mandat mort)
- `/home/serge/serge-system` **vide** au premier install
- **canon vide** (ne pas copier la DB WSL)
- mêmes clés API que le WSL, TOML neuf
- Asterisk + Caddy si les features correspondantes sont on
  (Julien : tout allumer)

## Prérequis VPS encore manuels

Ce PR **n’installe pas** le runner, ne SSH pas, ne fabrique pas le
couple. Après le merge, on le fait à deux :

- [ ] runner enregistré, labels `linux` + `julien-vps`, Idle
- [ ] couple live + age + mandat
- [ ] `system_root` vide
- [ ] venv Python ≥ 3.12
- [ ] Asterisk / Caddy selon features
- [ ] linger user (`loginctl enable-linger serge`) pour les units
      `--user` après logout
- [ ] premier job deploy après merge (suivre le check `deploy julien-vps`)

Kill-switch : `state/KILL_SWITCH` ou
`orchestrator/runtime/KILL_SWITCH` → le pipeline ne part pas.
