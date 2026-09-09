#!/usr/bin/env python3
"""Installeur Serge unique: couple existant OU génération guidée, puis build."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kit.builder import BuilderError, build_instance  # noqa: E402
from kit.instance_file import InstanceError  # noqa: E402
from kit.instance_wizard import WizardError, write_couple  # noqa: E402


def _load_wizard() -> Any:
    """Importe le wizard interactif (clé API + modèles + guide en premier)."""
    spec = importlib.util.spec_from_file_location(
        'serge_instance_wizard',
        str(ROOT / 'scripts' / 'serge-instance-wizard.py'),
    )
    if spec is None or spec.loader is None:
        raise WizardError('wizard introuvable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def _require_interactive(non_interactive: bool) -> None:
    if non_interactive or not sys.stdin.isatty():
        raise WizardError(
            'mode non-interactif : passe --instance-file + --mandate '
            '+ --source-repo, ou --answers + --source-repo'
        )


def _build(args: argparse.Namespace, instance: Path, mandate: Path) -> dict:
    """Construit l'instance et affiche le résumé. Retourne le receipt."""
    receipt = build_instance(
        instance_file=instance,
        mandate=mandate,
        source_repo=args.source_repo,
        git_sha=args.git_sha,
        systemd_user_dir=args.systemd_user_dir,
        enable=not args.no_enable_units,
        confirm_live_id=args.confirm_live_instance_id,
        kit_root=ROOT,
    )
    print()
    print('=== Instance construite ===')
    print(f'instance : {receipt["instance_id"]} ({receipt["mode"]})')
    print(f'racine   : {receipt["system_root"]}')
    print(f'fichier  : {receipt["instance_file"]}')
    print(
        f'units    : {len(receipt["units_written"])} écrites, '
        f'{len(receipt["units_enabled"])} activées'
    )
    if receipt.get('sms_route'):
        print(f'route SMS: {receipt["sms_route"]}')
    if receipt.get('llm_slots'):
        print(f'modèles  : {receipt["llm_slots"]}')
    print()
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return receipt


def _build_from_existing(args: argparse.Namespace) -> int:
    """Chemin 1 : couple + mandat déjà prêts, build direct."""
    if not args.mandate or not args.source_repo:
        raise WizardError('--instance-file exige --mandate et --source-repo')
    _build(args, args.instance_file, args.mandate)
    return 0


def _build_from_answers(args: argparse.Namespace) -> int:
    """Chemin 2 : génère le couple depuis un JSON, puis build."""
    if not args.source_repo:
        raise WizardError('--answers exige --source-repo pour le build')
    payload = json.loads(args.answers.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise WizardError('answers file must be a JSON object')
    out_dir = args.out_dir
    mandate_out = args.mandate_out or (out_dir / 'mandate.yaml')
    written = write_couple(
        payload,
        out_dir,
        allow_plaintext=args.allow_plaintext_secrets,
        also_mandate=args.also_mandate,
        mandate_out=mandate_out,
    )
    for key, path in written.items():
        print(f'écrit {key}: {path}')
    mandate = Path(written['mandate']) if args.also_mandate else args.mandate
    if mandate is None:
        raise WizardError('--answers exige --mandate ou --also-mandate')
    _build(args, Path(written['instance']), mandate)
    return 0


def _interactive(args: argparse.Namespace) -> int:
    """Chemin 3 : tout au terminal, avec le guide LLM."""
    _require_interactive(args.non_interactive)
    print('Installation Serge — 2 chemins possibles :')
    print('  1. Tu as déjà serge.instance.toml + sidecar (+ mandat).')
    print('  2. Tu n’as rien : génération guidée puis build.')
    print()
    if _yesno('As-tu déjà un couple (TOML + sidecar) ?', False):
        instance = Path(
            _prompt('Fichier serge.instance.toml', '') or 'serge.instance.toml'
        )
        mandate = Path(_prompt('Fichier mandat', '') or 'mandate.yaml')
        args.source_repo = Path(_prompt('Dépôt source (git)', str(ROOT)))
        args.git_sha = _prompt('Révision git', args.git_sha or 'HEAD')
        user_dir = _prompt('Dossier systemd user (vide = défaut)', '')
        args.systemd_user_dir = Path(user_dir) if user_dir else None
        args.no_enable_units = not _yesno(
            'Activer les units (systemctl --user) ?', False
        )
        if _yesno('Instance julien-vps sur CE VPS (chemins live) ?', False):
            args.confirm_live_instance_id = 'julien-vps'
        args.instance_file, args.mandate = instance, mandate
        return _build_from_existing(args)
    wizard = _load_wizard()
    answers = wizard.ask_interactive()
    out_dir = Path(_prompt('Dossier de sortie du couple', 'couple'))
    plaintext = _yesno('Secrets en clair (test local uniquement) ?', False)
    also_mandate = _yesno('Générer aussi le mandat ?', True)
    mandate_out = out_dir / 'mandate.yaml'
    if also_mandate:
        answers['mandate'] = {
            'policy_owner': _prompt('Identifiant owner (ex. alice)', ''),
            'email': _prompt('Email d’identité publique', ''),
        }
        custom = _prompt('Fichier mandat', str(mandate_out))
        mandate_out = Path(custom)
    args.out_dir = out_dir
    args.allow_plaintext_secrets = plaintext
    args.also_mandate = also_mandate
    args.mandate_out = mandate_out
    args.source_repo = Path(_prompt('Dépôt source (git)', str(ROOT)))
    args.git_sha = _prompt('Révision git', args.git_sha or 'HEAD')
    user_dir = _prompt('Dossier systemd user (vide = défaut)', '')
    args.systemd_user_dir = Path(user_dir) if user_dir else None
    args.no_enable_units = not _yesno(
        'Activer les units (systemctl --user) ?', False
    )
    if _yesno('Instance julien-vps sur CE VPS (chemins live) ?', False):
        args.confirm_live_instance_id = 'julien-vps'
    written = write_couple(
        answers,
        out_dir,
        allow_plaintext=plaintext,
        also_mandate=also_mandate,
        mandate_out=mandate_out,
    )
    for key, path in written.items():
        print(f'écrit {key}: {path}')
    mandate = Path(written['mandate']) if also_mandate else None
    if mandate is None:
        mandate = Path(_prompt('Fichier mandat', ''))
    _build(args, Path(written['instance']), mandate)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Point d’entrée : existant, answers, ou interactif guidé.

    Args:
        argv: Arguments CLI (sys.argv par défaut).

    Returns:
        0 si l’instance est construite, 2 sinon.
    """
    parser = argparse.ArgumentParser(
        description=(
            'Installe Serge : réutilise un couple existant, ou génère le '
            'couple (clé API + modèles + guide, puis instance) et build.'
        ),
    )
    parser.add_argument('--instance-file', type=Path)
    parser.add_argument('--mandate', type=Path)
    parser.add_argument('--source-repo', type=Path)
    parser.add_argument('--git-sha', default='HEAD')
    parser.add_argument('--systemd-user-dir', type=Path)
    parser.add_argument('--no-enable-units', action='store_true')
    parser.add_argument('--confirm-live-instance-id', default='')
    parser.add_argument('--answers', type=Path, help='JSON wizard.')
    parser.add_argument('--out-dir', type=Path, default=Path('couple'))
    parser.add_argument('--allow-plaintext-secrets', action='store_true')
    parser.add_argument('--also-mandate', action='store_true')
    parser.add_argument('--mandate-out', type=Path)
    parser.add_argument(
        '--non-interactive',
        action='store_true',
        help='Refuse les prompts (CI) : tout par flags.',
    )
    args = parser.parse_args(argv)
    try:
        if args.instance_file:
            return _build_from_existing(args)
        if args.answers:
            return _build_from_answers(args)
        return _interactive(args)
    except (
        BuilderError,
        InstanceError,
        WizardError,
        OSError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        print(f'erreur: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
