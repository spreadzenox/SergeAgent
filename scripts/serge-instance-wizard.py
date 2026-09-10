#!/usr/bin/env python3
"""Interactive assistant to build serge.instance.toml + secrets sidecar."""

from __future__ import annotations

import argparse
import getpass
import json
import secrets
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kit.guide import Guide  # noqa: E402
from kit.instance_file import (  # noqa: E402
    FEATURE_KEYS,
    multiline_secret_names,
)
from kit.instance_wizard import (  # noqa: E402
    SECRET_LABELS,
    WizardError,
    default_answers,
    required_secret_prompts,
    write_couple,
)
from kit.openrouter import (  # noqa: E402
    RECOMMENDED_TIERS,
    TIER_LABELS,
    OpenRouterError,
    fetch_models,
    format_model_line,
    search_models,
)

HELP_WORDS = frozenset({'?', 'aide', 'help', 'h'})


def _prompt(label: str, default: str = '') -> str:
    suffix = f' [{default}]' if default else ''
    value = input(f'{label}{suffix}: ').strip()
    return value or default


def _yesno(label: str, default: bool = False) -> bool:
    hint = 'O/n' if default else 'o/N'
    value = input(f'{label} ({hint}): ').strip().lower()
    if not value:
        return default
    return value in {'o', 'oui', 'y', 'yes', '1'}


def _ask_guide(guide: Guide, topic: str) -> None:
    question = input('Ta question (vide pour annuler) : ').strip()
    if not question:
        return
    print()
    print(guide.ask(question, topic))
    print()


def _prompt_guided(
    label: str,
    default: str = '',
    guide: Guide | None = None,
    topic: str = '',
) -> str:
    suffix = f' [{default}]' if default else ''
    while True:
        raw = input(f'{label}{suffix}: ').strip()
        if guide is not None and raw.lower() in HELP_WORDS:
            _ask_guide(guide, topic)
            continue
        return raw or default


def _yesno_guided(
    label: str,
    default: bool = False,
    guide: Guide | None = None,
    topic: str = '',
) -> bool:
    hint = 'O/n' if default else 'o/N'
    while True:
        value = input(f'{label} ({hint}): ').strip().lower()
        if guide is not None and value in HELP_WORDS:
            _ask_guide(guide, topic)
            continue
        if not value:
            return default
        return value in {'o', 'oui', 'y', 'yes', '1'}


def _choose_model(
    tier: str,
    models: list[dict] | None,
    guide: Guide | None,
) -> str:
    label = TIER_LABELS[tier]
    default = RECOMMENDED_TIERS[tier]
    print(f'{label} — recommandé : {default}')
    if not models:
        print('(catalogue indisponible — saisie manuelle)')
        return _prompt_guided(label, default, guide, 'modeles')
    ids = {str(item['id']) for item in models}
    while True:
        raw = _prompt_guided(
            f'{label} (Entrée=garder, texte=rechercher)',
            default,
            guide,
            'modeles',
        )
        if raw in ids:
            return raw
        matches = search_models(models, raw)
        if not matches:
            print('Aucun modèle trouvé — réessaie (? pour le guide).')
            continue
        for index, item in enumerate(matches, 1):
            print(f'  {index}. {format_model_line(item)}')
        pick = input(
            'Numéro, id exact, ou nouvelle recherche (vide=annuler) : '
        ).strip()
        if not pick:
            continue
        if pick.isdigit() and 1 <= int(pick) <= len(matches):
            return str(matches[int(pick) - 1]['id'])
        if pick in ids:
            return pick
        print('Choix non reconnu — nouvelle recherche ci-dessous.')


def _read_multiline_secret(label: str) -> str:
    print(f'{label} (multiligne — ligne vide pour terminer) :')
    chunks = []
    while True:
        chunk = getpass.getpass('> ').replace('\r', '')
        if not chunk.strip():
            break
        chunks.append(chunk)
    return '\n'.join(chunks).strip()


def ask_interactive() -> dict[str, Any]:
    print(
        'Assistant fichier d’instance Serge. Secrets seulement dans le sidecar.'
    )
    print('Serge est tout ou rien : les features à token sont on par défaut.')
    print('Meta-Grok reste off (pas de token, pont hôte seulement).')
    print('Tape ? à tout moment pour demander de l’aide au guide.')
    answers = default_answers()
    print()
    print('=== Étape 1/3 : LLM (clé OpenRouter + modèles T1/T2/T3) ===')
    print('La clé sert au guide pendant l’installation, puis part dans le')
    print('sidecar chiffré. Elle n’est jamais affichée ni écrite en clair.')
    openrouter_key = ''
    while not openrouter_key:
        openrouter_key = getpass.getpass('Clé API OpenRouter : ').strip()
        if not openrouter_key:
            print('La clé OpenRouter est obligatoire (moteur LLM de Serge).')
    print('Récupération du catalogue de modèles...')
    try:
        models = fetch_models(openrouter_key)
        print(f'{len(models)} modèles disponibles.')
    except OpenRouterError as exc:
        print(f'Catalogue indisponible ({exc}) — saisie manuelle.')
        models = None
    print()
    print('Choisis un modèle par tier (Entrée = recommandation live).')
    t1 = _choose_model('t1', models, None)
    t2 = _choose_model('t2', models, None)
    t3 = _choose_model('t3', models, None)
    answers['llm']['t1_model'] = t1
    answers['llm']['t2_model'] = t2
    answers['llm']['t3_model'] = t3
    answers['llm']['guide_model'] = t2
    referer = _prompt('Référent LLM affiché (optionnel, URL)', '')
    answers['llm']['referer'] = referer
    guide_enabled = _yesno('Activer le guide interactif ?', True)
    guide = Guide(openrouter_key, t2, referer, guide_enabled)
    if guide.ready:
        print(f'Guide activé ({t2}). Tape ? à tout moment pour poser une')
        print('question sur l’étape en cours.')
    else:
        print('Guide désactivé — aide locale uniquement (tape ? quand même).')
    print()
    print('=== Étape 2/3 : instance ===')
    instance_id = _prompt_guided(
        'instance_id (ex. alice-laptop)', '', guide, 'instance'
    )
    if instance_id:
        answers['instance_id'] = instance_id
    mode = _prompt_guided(
        'Mode (sandbox|staging|live)', 'sandbox', guide, 'instance'
    ).lower()
    answers['mode'] = (
        mode if mode in {'sandbox', 'staging', 'live'} else 'sandbox'
    )
    home = _prompt_guided(
        'Unix home', answers['paths']['home'], guide, 'paths'
    )
    answers['paths']['home'] = home
    answers['paths']['system_root'] = _prompt_guided(
        'system_root',
        f'{home.rstrip("/")}/serge-system',
        guide,
        'paths',
    )
    answers['paths']['config_root'] = _prompt_guided(
        'config_root',
        f'{home.rstrip("/")}/.config/serge',
        guide,
        'paths',
    )
    answers['paths']['policy'] = _prompt_guided(
        'mandat (paths.policy)',
        f'{answers["paths"]["config_root"].rstrip("/")}/mandate.yaml',
        guide,
        'mandat',
    )
    answers['identity']['hostname'] = _prompt_guided(
        'hostname', 'localhost', guide, 'instance'
    )
    print('Features (off = absentes de l’instance, pas « on verra ») :')
    labels = {
        'ingress': 'Ingress / Caddy',
        'stripe': 'Stripe sandbox',
        'voice': 'Voix temps réel (xAI ou OpenAI)',
        'metagrok': 'Pont Meta-Grok déjà présent sur cet hôte',
        'gmail': 'Gmail provider',
        'mailbox': 'Boîte email SMTP/IMAP (confiance)',
        'discord': 'Discord owner console',
        'openclaw': 'Adaptateur OpenClaw',
        'owner_ui': 'Dashboard owner / Mission Control',
        'payments_live': 'Paiements live',
        'phone_sms': 'Téléphonie SMS (SIM + Android, OTP)',
        'phone_voice': 'Voix commerciale SIP (trunk NPV)',
    }
    features = dict(answers['features'])
    for key in FEATURE_KEYS:
        topic = 'phone' if key in {'phone_sms', 'phone_voice'} else 'features'
        features[key] = _yesno_guided(
            labels[key], bool(features.get(key)), guide, topic
        )
    if features['phone_voice'] and not features['phone_sms']:
        print('phone_voice exige phone_sms (Option B = SIM SMS + trunk SIP).')
        features['phone_sms'] = True
    if features['phone_voice'] and not features['voice']:
        print('phone_voice exige voice (clés voix temps réel).')
        features['voice'] = True
    if features['phone_sms'] and not features['ingress']:
        print('phone_sms exige ingress (webhook HTTPS).')
        features['ingress'] = True
    answers['features'] = features
    if features['ingress']:
        listen = _prompt_guided(
            'ingress.listen (loopback|privileged)',
            'loopback',
            guide,
            'features',
        )
        answers['ingress']['listen'] = (
            listen if listen in {'loopback', 'privileged'} else 'loopback'
        )
    if features['phone_sms']:
        answers['identity']['public_hostname'] = _prompt_guided(
            'Domaine public (webhook sms.<domaine>)',
            answers['identity']['public_hostname'],
            guide,
            'phone',
        )
        answers['identity']['phone_sms_number'] = _prompt_guided(
            'Numéro SIM SMS (E.164, ex. +33612345678)',
            answers['identity']['phone_sms_number'],
            guide,
            'phone',
        )
    if features['phone_voice']:
        answers['identity']['phone_voice_number'] = _prompt_guided(
            'Numéro voix NPV (E.164, ex. +33162123456)',
            answers['identity']['phone_voice_number'],
            guide,
            'phone',
        )
        answers['phone_voice']['sip_server'] = _prompt_guided(
            'Serveur SIP (ex. sip.fournisseur.fr)',
            answers['phone_voice']['sip_server'],
            guide,
            'phone',
        )
        answers['phone_voice']['sip_username'] = _prompt_guided(
            'Identifiant SIP',
            answers['phone_voice']['sip_username'],
            guide,
            'phone',
        )
        transport = _prompt_guided(
            'Transport SIP (udp|tcp|tls)',
            answers['phone_voice']['sip_transport'],
            guide,
            'phone',
        ).lower()
        answers['phone_voice']['sip_transport'] = (
            transport if transport in {'udp', 'tcp', 'tls'} else 'tls'
        )
    if features['discord']:
        for key, label in (
            ('guild_id', 'ID du serveur Discord'),
            ('forum_channel_id', 'ID du forum tickets'),
            ('urgent_channel_id', 'ID du canal urgent'),
            ('digest_channel_id', 'ID du canal digest'),
            ('owner_user_id', 'ID de ton compte owner'),
        ):
            answers['discord'][key] = _prompt_guided(
                f'{label} (clic droit → copier l’identifiant)',
                answers['discord'][key],
                guide,
                'discord',
            )
    if features['mailbox']:
        preset = _prompt_guided(
            'Preset mailbox (infomaniak|gmail|fastmail|custom)',
            answers['mailbox']['preset'],
            guide,
            'mailbox',
        ).lower()
        answers['mailbox']['preset'] = (
            preset
            if preset in {'infomaniak', 'gmail', 'fastmail', 'custom'}
            else 'infomaniak'
        )
        answers['mailbox']['login'] = _prompt_guided(
            'Login boîte (adresse complète)',
            answers['mailbox']['login'],
            guide,
            'mailbox',
        )
        if answers['mailbox']['preset'] == 'custom':
            for key, label in (
                ('smtp_host', 'Serveur SMTP'),
                ('smtp_port', 'Port SMTP (587 ou 465)'),
                ('imap_host', 'Serveur IMAP'),
                ('imap_port', 'Port IMAP (993 ou 143)'),
            ):
                answers['mailbox'][key] = _prompt_guided(
                    label,
                    str(answers['mailbox'][key] or ''),
                    guide,
                    'mailbox',
                )
    print()
    print('=== Étape 3/3 : secrets (non affichés, jamais dans le TOML) ===')
    print('Clé OpenRouter déjà saisie à l’étape 1 — non redemandée.')
    collected: dict[str, str] = {'openrouter_api_key': openrouter_key}
    multiline = set(multiline_secret_names(features))
    for name in required_secret_prompts(features):
        if name == 'openrouter_api_key':
            continue
        label = SECRET_LABELS.get(name, name)
        optional = name == 'openai_api_key' and features.get('voice')
        suffix = ' (optionnel si xAI déjà fourni)' if optional else ''
        generated = ''
        if name == 'sms_gateway_token':
            suffix = ' (vide = générer)'
        if name in multiline:
            value = _read_multiline_secret(label)
        else:
            value = getpass.getpass(f'{label}{suffix}: ').strip()
        if not value and name == 'sms_gateway_token':
            generated = secrets.token_hex(32)
            print(
                'Secret webhook généré (à coller dans l’app Android) : '
                f'{generated}'
            )
            value = generated
        if value:
            collected[name] = value
    answers['secrets'] = collected
    if _yesno('Chiffrer le sidecar avec age maintenant ?', True):
        recipients: list[str] = []
        while True:
            recipient = _prompt('Destinataire age (vide pour terminer)', '')
            if not recipient:
                break
            recipients.append(recipient)
        answers['age_recipients'] = recipients
    return answers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            'Génère serge.instance.toml + sidecar secrets. '
            'Refuse un couple incomplet.'
        ),
    )
    parser.add_argument('--answers', type=Path, help='JSON de réponses.')
    parser.add_argument(
        '--out-dir',
        type=Path,
        default=Path('.'),
        help='Dossier de sortie (défaut: cwd).',
    )
    parser.add_argument(
        '--allow-plaintext-secrets',
        action='store_true',
        help='Écrire serge.secrets en dotenv (tests / sandbox local uniquement).',
    )
    parser.add_argument(
        '--also-mandate',
        action='store_true',
        help='Enchaîner le wizard mandat (même mode, features qui se recoupent).',
    )
    parser.add_argument('--mandate-out', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.answers:
            payload = json.loads(args.answers.read_text(encoding='utf-8'))
            if not isinstance(payload, dict):
                raise WizardError('answers file must be a JSON object')
            answers = payload
        else:
            if not sys.stdin.isatty():
                raise WizardError('terminal required, or pass --answers')
            answers = ask_interactive()
        written = write_couple(
            answers,
            args.out_dir,
            allow_plaintext=args.allow_plaintext_secrets,
            also_mandate=args.also_mandate,
            mandate_out=args.mandate_out,
        )
    except (WizardError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(f'erreur: {exc}', file=sys.stderr)
        return 2
    for key, path in written.items():
        print(f'écrit {key}: {path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
