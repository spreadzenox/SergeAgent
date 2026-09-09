# Traçabilité des réutilisations legacy (option C)

Règle : rien du legacy n'entre ici sauf par choix explicite de Julien,
tracé ci-dessous (source, quoi, pourquoi, ce qu'on a laissé).
Le legacy vit dans `/home/serge/serge-system` (prod) et le worktree
`/home/serge/serge-kit` (branche `serge-instance-kit`).

## Seed initial (2026-09-09, depuis serge-kit @1839523f)

Copié tel quel (verdict : code déjà sous charte, tests verts) :

| Fichiers | Source | Pourquoi |
|---|---|---|
| `kit/*.py` | serge-kit `kit/` | Installeur validé (TOML+age, wizards, builder, guide, slots) |
| `bin/serge-*` | serge-kit `bin/` | Shims CLI |
| `scripts/serge-*.py`, `scan-repo-secrets.py` | serge-kit `scripts/` | Installeur + wizards + scan |
| `schemas/serge.*` | serge-kit `schemas/` | Contrats instance/secrets/exclusions |
| `systemd/templates/` | serge-kit | Units paramétrés |
| `orchestrator/{sms_broker,sms_receiver,voice_broker,voice_bridge,voice_turn}.py` | serge-kit `orchestrator/` | Runtime phone neuf — déplacé phase 0 (C19) vers `serge/voice/` (`policy.py`, `ledger.py`, `agi.py`, `providers.py`, `turn.py`, `bridge.py`) et `serge/sms/` (`inbox.py`, `receiver.py`) ; `orchestrator/` supprimé |
| `docs/` design + install + phone + contrat | serge-kit `docs/` | Docs validées le 2026-09-09 |
| `tests/test_{installer_llm,instance_*,mandate_wizard,voice_broker,sms_receiver,asterisk_render,voice_bridge}.py` | serge-kit `tests/` | Suite kit/phone (adaptée : imports legacy retirés, voir ci-dessous) |
| `policy-reference/mandate.sandbox.example.yaml` | serge-kit | Fixture tests mandat |
| `pyproject.toml`, `.python-version`, `.pre-commit-config.yaml`, `uv.lock`, `.gitignore` | serge-kit | Outillage (B6 : ajouts à venir) |

Adaptations du seed (divergences assumées vs kit) :

| Fichier | Changement | Raison |
|---|---|---|
| `tests/test_instance_file.py` | Test `sergectl doctor` supprimé (legacy `orchestrator/sergectl.py` non porté) | B8/A delete-first |
| `tests/test_mandate_wizard.py` | `capability_resolution` remplacé par lecture YAML locale + `validate_mandate` | Idem |
| `tests/test_instance_builder.py` | Copie de `web_ingress.py` legacy remplacée par stub `STUB_WEB_INGRESS` (~30 lignes, même contrat CLI upsert) | Idem ; ingress neuf en phase 1 |
| `.gitignore` | Ajout `.env.test`, `config/*.local.yaml` | Secrets de test jamais commités |
| (nouveau) `README.md` | Réécrit pour serge-v2 | Le README kit décrivait le worktree |

## Cherry-picks envisagés (non faits, à valider un par un)

| Candidat | Source legacy | Usage prévu | Statut |
|---|---|---|---|
| Partage session navigateur + keepalive (pattern captcha-stream GUICHET) | `orchestrator/adapters/browserbase.py` (`connectUrl`), `managed_browser.py` (patterns session) | Tickets GUICHET (H) | À extraire en phase 1-2 |
| Patterns idempotence/ledger | `orchestrator/broker.py`, `payment_broker.py` | Store idempotence phase 0 | À extraire, simplifié |
| Patterns Stripe receive + sandbox | `adapters/stripe_*.py`, `stripe_*_policy.py` | Funnel collect phase 2 | À extraire, simplifié |
| Client CDP stdlib | `orchestrator/adapters/cdp_client.py` | `browser.py` (B2 screenshots/interaction) | À extraire + simplifier |
| Rendu Caddy minimal | `orchestrator/web_ingress.py` (concepts seulement) | Ingress neuf phase 1 | Concepts, pas le code (1,2 k lignes) |
| Calcul fériés FR / fenêtres voix | Déjà kit (`serge/voice/policy.py`) | Registre zones d'appel (F2) | Déplacer, pas dupliquer |

## Non porté, par décision

OpenClaw (gateway, CLI, conteneurs, `openclaw.json`, routage — B2/A),
occupancy/challengers/hystérésis/`role_slots` (B3/A), 132 tests legacy
(B8/A, suppression pure), `queue/` (P4, archive lecture seule),
`orchestrator.py` 20 k lignes et `portfolio_guard.py` 8 k lignes
(remplacés par `serge/`, jamais importés par le neuf).
