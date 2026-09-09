#!/usr/bin/env python3
"""Interactive assistant to build a Serge mandate.yaml (not Julien's live file)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kit.mandate import (  # noqa: E402
    FEATURE_KEYS,
    MandateError,
    build_mandate,
    render_yaml,
    sandbox_answers,
)


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


def ask_interactive() -> dict[str, Any]:
    print('Assistant mandat Serge. Aucun secret. Pas le mandat du VPS Julien.')
    print(
        'mode=sandbox coupe paiements live, deploy prod, et l’autonomie continue.'
    )
    answers = sandbox_answers()
    answers['policy_owner'] = _prompt('Identifiant owner (ex. alice)', '')
    answers['agent_name'] = _prompt('Nom de l’agent', answers['agent_name'])
    answers['email'] = _prompt('Email d’identité publique de l’instance', '')
    answers['public_role'] = _prompt(
        'Rôle public (une ligne)',
        answers['public_role'],
    )
    mode = _prompt('Mode (sandbox|staging|live)', 'sandbox').lower()
    answers['mode'] = (
        mode if mode in {'sandbox', 'staging', 'live'} else 'sandbox'
    )
    answers['autonomous'] = _yesno(
        'Fonctionnement autonome continu ?',
        False,
    )
    print('Capabilities (off = absentes du mandat, pas « on verra ») :')
    labels = {
        'public_web': 'Recherche web publique (scout)',
        'gmail': 'Email business (lire / envoyer borné)',
        'accounts': 'Comptes web, browser, vérif email/SMS',
        'ingress': 'DNS / ingress',
        'stripe': 'Stripe sandbox',
        'payments_live': 'Paiements live / Stripe live receive',
        'deploy_staging': 'Déploiement staging',
        'deploy_production': 'Déploiement production',
        'phone_sms': 'Réception SMS / OTP (SIM + Android)',
        'phone_voice': 'Voix commerciale SIP (coupée en sandbox)',
    }
    features = dict(answers['features'])
    for key in FEATURE_KEYS:
        features[key] = _yesno(labels[key], bool(features.get(key)))
    answers['features'] = features
    if answers['mode'] != 'sandbox' and answers['features']['payments_live']:
        answers['financial']['payment_execution_enabled'] = True
        answers['financial']['card_monthly_limit_eur'] = int(
            _prompt('Plafond carte € / mois', '50') or '50'
        )
        answers['financial']['maximum_one_off_eur'] = int(
            _prompt('Maximum un paiement €', '30') or '30'
        )
        answers['financial']['maximum_new_recurring_subscription_eur'] = int(
            _prompt('Maximum nouvel abo €', '30') or '30'
        )
    return answers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Génère un mandat Serge vierge (YAML). Aucune valeur secrète.',
    )
    parser.add_argument(
        '--answers',
        type=Path,
        help='JSON de réponses (non interactif).',
    )
    parser.add_argument(
        '--out',
        type=Path,
        default=Path('mandate.yaml'),
        help='Fichier de sortie (défaut: ./mandate.yaml).',
    )
    parser.add_argument(
        '--print',
        action='store_true',
        dest='print_only',
        help='Écrire sur stdout, ne pas créer de fichier.',
    )
    args = parser.parse_args(argv)
    try:
        if args.answers:
            payload = json.loads(args.answers.read_text(encoding='utf-8'))
            if not isinstance(payload, dict):
                raise MandateError('answers file must be a JSON object')
            answers = payload
        else:
            if not sys.stdin.isatty():
                raise MandateError('terminal required, or pass --answers')
            answers = ask_interactive()
        mandate = build_mandate(answers)
        text = render_yaml(mandate)
    except (MandateError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(f'erreur: {exc}', file=sys.stderr)
        return 2
    if args.print_only:
        sys.stdout.write(text)
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding='utf-8')
    args.out.chmod(0o600)
    print(f'écrit {args.out} (mode {mandate.get("status")})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
