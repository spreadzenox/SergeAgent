#!/usr/bin/env python3
"""Build a virgin serge.instance.toml + secrets sidecar. No owner memory."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from kit.instance_file import (
    ALWAYS_REQUIRED_SECRETS,
    FEATURE_KEYS,
    InstanceError,
    assert_secrets_complete,
    default_features,
    load_manifest,
    validate_toml,
)
from kit.mandate import (
    MandateError,
    build_mandate,
    render_yaml,
    sandbox_answers,
)
from kit.openrouter import RECOMMENDED_TIERS

INSTANCE_ID_RE = re.compile(r'^[a-z0-9][a-z0-9._-]{0,63}$')
SECRET_LABELS = {
    'openrouter_api_key': 'OpenRouter API key',
    'owner_dashboard_token': 'Owner dashboard token',
    'xai_api_key': 'xAI API key (voice)',
    'openai_api_key': 'OpenAI API key (voice, if no xAI)',
    'stripe_test_key': 'Stripe test secret key',
    'stripe_webhook_test_key': 'Stripe test webhook secret',
    'stripe_live_key': 'Stripe live secret key',
    'stripe_webhook_live_key': 'Stripe live webhook secret',
    'discord_bot_token': 'Discord bot token',
    'browserbase_key': 'Browserbase key (OpenClaw)',
    'cloudflare_infra_key': 'Cloudflare infra key',
    'cloudflare_registrar_key': 'Cloudflare registrar key',
    'credential_vault_key': 'Credential vault key',
    'payment_card_enc': 'Payment card ciphertext blob',
    'gog_env': 'Gmail provider env blob',
    'sms_gateway_token': 'SMS gateway webhook secret (generated if empty)',
    'sip_trunk_password': 'SIP trunk password',
}


class WizardError(ValueError):
    pass


def empty_features() -> dict[str, bool]:
    return {key: False for key in FEATURE_KEYS}


def default_answers() -> dict[str, Any]:
    return {
        'instance_id': 'example-sandbox',
        'mode': 'sandbox',
        'identity': {
            'hostname': 'localhost',
            'public_hostname': 'serge.example.net',
            'phone_sms_number': '+33600000001',
            'phone_voice_number': '+33162000001',
        },
        'paths': {
            'home': '/home/owner',
            'system_root': '/home/owner/serge-system',
            'policy': '/home/owner/.config/serge/mandate.yaml',
            'config_root': '/home/owner/.config/serge',
            'secrets_age': 'serge.secrets.age',
        },
        'features': default_features(),
        'llm': {
            'provider': 'openrouter',
            'referer': '',
            't1_model': RECOMMENDED_TIERS['t1'],
            't2_model': RECOMMENDED_TIERS['t2'],
            't3_model': RECOMMENDED_TIERS['t3'],
            'guide_model': RECOMMENDED_TIERS['t2'],
        },
        'ingress': {'listen': 'loopback', 'aliases': []},
        'phone_voice': {
            'sip_server': 'sip.example.com',
            'sip_username': 'example-trunk',
            'sip_transport': 'tls',
            'max_calls_per_day': 50,
        },
        'discord': {
            'guild_id': '',
            'forum_channel_id': '',
            'urgent_channel_id': '',
            'digest_channel_id': '',
            'owner_user_id': '',
        },
        'testing': {
            'n_smoke_min': 30,
            'n_smoke_max': 50,
            'n_full_min': 150,
            'n_full_target': 200,
            'kill_max_positives': 1,
            'scale_min_positives': 5,
            'scale_min_meetings': 2,
            'extend_max': 1,
        },
        'secrets': {},
        'age_recipients': [],
        'mandate': {},
    }


def normalize_answers(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    base = default_answers()
    incoming = dict(raw or {})
    paths = {**base['paths'], **dict(incoming.get('paths') or {})}
    features = {**base['features'], **dict(incoming.get('features') or {})}
    identity = {**base['identity'], **dict(incoming.get('identity') or {})}
    llm = {**base['llm'], **dict(incoming.get('llm') or {})}
    ingress = {**base['ingress'], **dict(incoming.get('ingress') or {})}
    phone_voice = {
        **base['phone_voice'],
        **dict(incoming.get('phone_voice') or {}),
    }
    discord = {
        **base['discord'],
        **dict(incoming.get('discord') or {}),
    }
    testing = {
        **base['testing'],
        **dict(incoming.get('testing') or {}),
    }
    instance_id = str(
        incoming.get('instance_id') or base['instance_id']
    ).strip()
    if not INSTANCE_ID_RE.match(instance_id):
        raise WizardError('instance_id must match [a-z0-9][a-z0-9._-]{0,63}')
    mode = str(incoming.get('mode') or base['mode']).strip()
    if mode not in {'live', 'staging', 'sandbox'}:
        raise WizardError('mode must be live|staging|sandbox')
    listen = str(ingress.get('listen') or 'loopback')
    if listen not in {'loopback', 'privileged'}:
        raise WizardError('ingress.listen must be loopback|privileged')
    aliases = ingress.get('aliases') or []
    if not isinstance(aliases, list):
        raise WizardError('ingress.aliases must be a list')
    sip_transport = (
        str(phone_voice.get('sip_transport') or 'tls').strip().lower()
    )
    if sip_transport not in {'udp', 'tcp', 'tls'}:
        raise WizardError('phone_voice.sip_transport must be udp|tcp|tls')
    try:
        max_calls = int(phone_voice.get('max_calls_per_day', 50))
    except (TypeError, ValueError):
        raise WizardError('phone_voice.max_calls_per_day must be an integer')
    if max_calls < 1:
        raise WizardError('phone_voice.max_calls_per_day must be >= 1')
    secrets = {
        str(key): str(value).strip()
        for key, value in dict(incoming.get('secrets') or {}).items()
        if str(value).strip()
    }
    recipients = [
        str(item).strip()
        for item in (incoming.get('age_recipients') or [])
        if str(item).strip()
    ]
    return {
        'instance_id': instance_id,
        'mode': mode,
        'identity': {
            'hostname': str(identity.get('hostname') or 'localhost').strip()
            or 'localhost',
            'public_hostname': str(
                identity.get('public_hostname') or ''
            ).strip(),
            'phone_sms_number': str(
                identity.get('phone_sms_number') or ''
            ).strip(),
            'phone_voice_number': str(
                identity.get('phone_voice_number') or ''
            ).strip(),
        },
        'paths': {
            'home': str(paths.get('home') or '').strip(),
            'system_root': str(paths.get('system_root') or '').strip(),
            'policy': str(paths.get('policy') or '').strip(),
            'config_root': str(paths.get('config_root') or '').strip(),
            'secrets_age': str(
                paths.get('secrets_age') or 'serge.secrets.age'
            ).strip(),
        },
        'features': {key: bool(features.get(key)) for key in FEATURE_KEYS},
        'llm': {
            'provider': str(llm.get('provider') or 'openrouter').strip()
            or 'openrouter',
            'referer': str(llm.get('referer') or '').strip(),
            't1_model': str(
                llm.get('t1_model') or RECOMMENDED_TIERS['t1']
            ).strip()
            or RECOMMENDED_TIERS['t1'],
            't2_model': str(
                llm.get('t2_model') or RECOMMENDED_TIERS['t2']
            ).strip()
            or RECOMMENDED_TIERS['t2'],
            't3_model': str(
                llm.get('t3_model') or RECOMMENDED_TIERS['t3']
            ).strip()
            or RECOMMENDED_TIERS['t3'],
            'guide_model': str(
                llm.get('guide_model')
                or llm.get('t2_model')
                or RECOMMENDED_TIERS['t2']
            ).strip()
            or RECOMMENDED_TIERS['t2'],
        },
        'ingress': {
            'listen': listen,
            'aliases': [
                str(item).strip() for item in aliases if str(item).strip()
            ],
        },
        'phone_voice': {
            'sip_server': str(phone_voice.get('sip_server') or '').strip(),
            'sip_username': str(phone_voice.get('sip_username') or '').strip(),
            'sip_transport': sip_transport,
            'max_calls_per_day': max_calls,
        },
        'discord': {
            key: str(discord.get(key) or '').strip() for key in base['discord']
        },
        'testing': {
            key: testing.get(key, base['testing'][key])
            for key in base['testing']
        },
        'secrets': secrets,
        'age_recipients': recipients,
        'mandate': dict(incoming.get('mandate') or {}),
    }


def toml_payload(answers: Mapping[str, Any]) -> dict[str, Any]:
    normalized = normalize_answers(answers)
    return {
        'schema_version': 1,
        'instance_id': normalized['instance_id'],
        'mode': normalized['mode'],
        'identity': normalized['identity'],
        'paths': normalized['paths'],
        'features': normalized['features'],
        'llm': normalized['llm'],
        'ingress': normalized['ingress'],
        'phone_voice': normalized['phone_voice'],
        'discord': normalized['discord'],
        'testing': normalized['testing'],
    }


def _toml_str(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _toml_bool(value: bool) -> str:
    return 'true' if value else 'false'


def render_toml(answers: Mapping[str, Any]) -> str:
    data = validate_toml(toml_payload(answers))
    aliases = data.get('ingress', {}).get('aliases') or []
    alias_items = ', '.join(_toml_str(item) for item in aliases)
    lines = [
        '# Generated by serge-instance-wizard. No secrets.',
        '',
        'schema_version = 1',
        f'instance_id = {_toml_str(data["instance_id"])}',
        f'mode = {_toml_str(data["mode"])}',
        '',
        '[identity]',
        f'hostname = {_toml_str(str(data["identity"].get("hostname") or ""))}',
        f'public_hostname = {_toml_str(str(data["identity"].get("public_hostname") or ""))}',
        f'phone_sms_number = {_toml_str(str(data["identity"].get("phone_sms_number") or ""))}',
        f'phone_voice_number = {_toml_str(str(data["identity"].get("phone_voice_number") or ""))}',
        '',
        '[paths]',
        f'home = {_toml_str(data["paths"]["home"])}',
        f'system_root = {_toml_str(data["paths"]["system_root"])}',
        f'policy = {_toml_str(data["paths"]["policy"])}',
        f'config_root = {_toml_str(data["paths"]["config_root"])}',
        f'secrets_age = {_toml_str(data["paths"]["secrets_age"])}',
        '',
        '[features]',
    ]
    for key in FEATURE_KEYS:
        lines.append(f'{key} = {_toml_bool(bool(data["features"].get(key)))}')
    lines.extend(
        [
            '',
            '[llm]',
            f'provider = {_toml_str(str(data["llm"].get("provider") or "openrouter"))}',
            f'referer = {_toml_str(str(data["llm"].get("referer") or ""))}',
            f't1_model = {_toml_str(str(data["llm"].get("t1_model") or ""))}',
            f't2_model = {_toml_str(str(data["llm"].get("t2_model") or ""))}',
            f't3_model = {_toml_str(str(data["llm"].get("t3_model") or ""))}',
            f'guide_model = {_toml_str(str(data["llm"].get("guide_model") or ""))}',
            '',
            '[ingress]',
            f'listen = {_toml_str(str(data["ingress"].get("listen") or "loopback"))}',
            f'aliases = [{alias_items}]',
            '',
            '[phone_voice]',
            f'sip_server = {_toml_str(str(data["phone_voice"].get("sip_server") or ""))}',
            f'sip_username = {_toml_str(str(data["phone_voice"].get("sip_username") or ""))}',
            f'sip_transport = {_toml_str(str(data["phone_voice"].get("sip_transport") or "tls"))}',
            f'max_calls_per_day = {int(data["phone_voice"].get("max_calls_per_day") or 50)}',
            '',
            '[discord]',
            f'guild_id = {_toml_str(str(data["discord"].get("guild_id") or ""))}',
            f'forum_channel_id = {_toml_str(str(data["discord"].get("forum_channel_id") or ""))}',
            f'urgent_channel_id = {_toml_str(str(data["discord"].get("urgent_channel_id") or ""))}',
            f'digest_channel_id = {_toml_str(str(data["discord"].get("digest_channel_id") or ""))}',
            f'owner_user_id = {_toml_str(str(data["discord"].get("owner_user_id") or ""))}',
            '',
            '[testing]',
            f'n_smoke_min = {int(data["testing"].get("n_smoke_min") or 30)}',
            f'n_smoke_max = {int(data["testing"].get("n_smoke_max") or 50)}',
            f'n_full_min = {int(data["testing"].get("n_full_min") or 150)}',
            f'n_full_target = {int(data["testing"].get("n_full_target") or 200)}',
            f'kill_max_positives = {int(data["testing"].get("kill_max_positives") or 1)}',
            f'scale_min_positives = {int(data["testing"].get("scale_min_positives") or 5)}',
            f'scale_min_meetings = {int(data["testing"].get("scale_min_meetings") or 2)}',
            f'extend_max = {int(data["testing"].get("extend_max") or 1)}',
            '',
        ]
    )
    return '\n'.join(lines)


def render_dotenv(secrets: Mapping[str, str]) -> str:
    lines = []
    for key in sorted(secrets):
        value = str(secrets[key]).replace('\n', '').replace('\r', '')
        lines.append(f'{key}={value}')
    return '\n'.join(lines) + '\n'


def required_secret_prompts(features: Mapping[str, bool]) -> list[str]:
    names = list(ALWAYS_REQUIRED_SECRETS)
    manifest = load_manifest()
    for item in manifest.get('keys') or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or '')
        feature = str(item.get('required_when_feature') or '')
        if not name or name in names:
            continue
        if feature == 'llm':
            continue
        if feature == 'voice':
            continue
        if feature and features.get(feature):
            names.append(name)
    if features.get('voice'):
        names.extend(['xai_api_key', 'openai_api_key'])
    return list(dict.fromkeys(names))


def validate_secrets(
    features: Mapping[str, bool], secrets: Mapping[str, str]
) -> None:
    try:
        assert_secrets_complete(features, secrets)
    except InstanceError as exc:
        raise WizardError(str(exc)) from exc


def encrypt_age(plaintext: str, recipients: list[str], dest: Path) -> None:
    if not recipients:
        raise WizardError('age recipients required to write serge.secrets.age')
    command = ['age', '-o', str(dest)]
    for recipient in recipients:
        command.extend(['-r', recipient])
    try:
        completed = subprocess.run(
            command,
            input=plaintext,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise WizardError('age binary not found') from exc
    if completed.returncode != 0:
        raise WizardError('failed to encrypt serge.secrets.age')


def mandate_answers_from_instance(
    answers: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = normalize_answers(answers)
    extra = dict(normalized.get('mandate') or {})
    merged = sandbox_answers()
    merged.update(extra)
    merged['mode'] = normalized['mode']
    features = dict(merged.get('features') or sandbox_answers()['features'])
    for key in (
        'gmail',
        'ingress',
        'stripe',
        'payments_live',
        'phone_sms',
        'phone_voice',
    ):
        features[key] = bool(normalized['features'].get(key))
    merged['features'] = features
    return merged


def write_couple(
    answers: Mapping[str, Any],
    dest_dir: Path,
    *,
    allow_plaintext: bool = False,
    also_mandate: bool = False,
    mandate_out: Path | None = None,
) -> dict[str, str]:
    normalized = normalize_answers(answers)
    try:
        validate_toml(toml_payload(normalized))
    except InstanceError as exc:
        raise WizardError(str(exc)) from exc
    validate_secrets(normalized['features'], normalized['secrets'])
    dest_dir.mkdir(parents=True, exist_ok=True)
    toml_path = dest_dir / 'serge.instance.toml'
    written: dict[str, str] = {}
    text = render_toml(normalized)
    for marker in (
        'sk_live_',
        'sk_test_',
        'whsec_',
        'openrouter_api_key=',
        'sms_gateway_token=',
        'sip_trunk_password=',
    ):
        if marker in text:
            raise WizardError('refusing to write secrets into TOML')
    dotenv = render_dotenv(normalized['secrets'])
    if allow_plaintext:
        sidecar = dest_dir / 'serge.secrets'
        sidecar.write_text(dotenv, encoding='utf-8')
        sidecar.chmod(0o600)
        normalized['paths']['secrets_age'] = sidecar.name
        text = render_toml(normalized)
        written['secrets'] = str(sidecar)
    else:
        sidecar = dest_dir / Path(normalized['paths']['secrets_age']).name
        encrypt_age(dotenv, normalized['age_recipients'], sidecar)
        sidecar.chmod(0o600)
        written['secrets'] = str(sidecar)
    toml_path.write_text(text, encoding='utf-8')
    written['instance'] = str(toml_path)
    if also_mandate:
        target = mandate_out or Path(normalized['paths']['policy'])
        try:
            mandate = build_mandate(mandate_answers_from_instance(normalized))
        except MandateError as exc:
            toml_path.unlink(missing_ok=True)
            Path(written['secrets']).unlink(missing_ok=True)
            raise WizardError(str(exc)) from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_yaml(mandate), encoding='utf-8')
        target.chmod(0o600)
        written['mandate'] = str(target)
    return written
