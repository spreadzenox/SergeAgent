#!/usr/bin/env python3
"""Load and validate serge.instance.toml + secrets sidecar. No secret values logged."""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from kit.mailbox_config import MailboxError, resolve_mailbox
from serge.e164 import E164_RE

FEATURE_KEYS = (
    'ingress',
    'stripe',
    'voice',
    'metagrok',
    'gmail',
    'mailbox',
    'discord',
    'openclaw',
    'owner_ui',
    'payments_live',
    'phone_sms',
    'phone_voice',
)
# Token-backed surfaces. metagrok has no sidecar key and is host-local.
HOST_ONLY_FEATURES = frozenset({'metagrok'})

# Telephony doctrine: Option B (voice) = Option A (SMS SIM) + SIP trunk.
# A commercial voice-only Serge is not a valid instance.
PHONE_VOICE_TRANSPORTS = frozenset({'udp', 'tcp', 'tls'})
PHONE_VOICE_DEFAULT_TRANSPORT = 'tls'
PHONE_VOICE_DEFAULT_MAX_CALLS_PER_DAY = 50
DISCORD_SNOWFLAKE_RE = re.compile(r'^[0-9]{5,25}$')
DISCORD_ID_KEYS = (
    'guild_id',
    'forum_channel_id',
    'urgent_channel_id',
    'digest_channel_id',
    'owner_user_id',
)
SMS_RECEIVER_UPSTREAM = '127.0.0.1:8787'
SMS_VENTURE_ID = 'serge-phone-sms'


def default_features() -> dict[str, bool]:
    """Serge is all-or-nothing: every token feature on, Meta-Grok off."""
    return {key: key not in HOST_ONLY_FEATURES for key in FEATURE_KEYS}


ALWAYS_REQUIRED_SECRETS = ('openrouter_api_key',)
MODES = frozenset({'live', 'staging', 'sandbox'})
SERGECTL_BOOT_COMMANDS = frozenset(
    {
        'run-once',
        'doctor',
        'activate',
        'shadow-run',
        'live-preflight',
        'burn-in',
        'monitor',
        'owner-console',
        'owner-console-discord',
        'web-ingress',
    }
)
ORCHESTRATOR_REQUIRES_INSTANCE = True


class InstanceError(ValueError):
    pass


def as_table(value: Any) -> dict[str, Any]:
    """Narrow an untrusted TOML node to a dict ({} when absent/wrong type)."""
    return value if isinstance(value, dict) else {}


def _repo_root() -> Path:
    env = os.environ.get('SERGE_SYSTEM_ROOT', '').strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[1]


def load_toml(path: Path) -> dict[str, Any]:
    try:
        data = tomllib.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise InstanceError(f'SERGE_INSTANCE_FILE missing: {path}') from exc
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise InstanceError(f'SERGE_INSTANCE_FILE unreadable: {path}') from exc
    if not isinstance(data, dict):
        raise InstanceError('instance file is not a table')
    return data


def validate_toml(data: Mapping[str, Any]) -> dict[str, Any]:
    if data.get('schema_version') != 1:
        raise InstanceError('schema_version must be 1')
    instance_id = str(data.get('instance_id') or '').strip()
    if not instance_id:
        raise InstanceError('instance_id is required')
    mode = str(data.get('mode') or '').strip()
    if mode not in MODES:
        raise InstanceError('mode must be live|staging|sandbox')
    paths = as_table(data.get('paths'))
    for key in ('home', 'system_root', 'policy'):
        if not str(paths.get(key) or '').strip():
            raise InstanceError(f'paths.{key} is required')
    features = as_table(data.get('features'))
    normalized = {key: bool(features.get(key)) for key in FEATURE_KEYS}
    identity = as_table(data.get('identity'))
    public_hostname = str(identity.get('public_hostname') or '').strip()
    phone_sms_number = str(identity.get('phone_sms_number') or '').strip()
    phone_voice_number = str(identity.get('phone_voice_number') or '').strip()
    raw_phone = as_table(data.get('phone_voice'))
    sip_server = str(raw_phone.get('sip_server') or '').strip()
    sip_username = str(raw_phone.get('sip_username') or '').strip()
    sip_transport = (
        str(raw_phone.get('sip_transport') or PHONE_VOICE_DEFAULT_TRANSPORT)
        .strip()
        .lower()
    )
    try:
        max_calls = int(
            raw_phone.get(
                'max_calls_per_day',
                PHONE_VOICE_DEFAULT_MAX_CALLS_PER_DAY,
            )
        )
    except (TypeError, ValueError):
        raise InstanceError('phone_voice.max_calls_per_day must be an integer')
    if normalized.get('phone_voice') and not normalized.get('phone_sms'):
        raise InstanceError(
            'features.phone_voice requires features.phone_sms '
            '(Option B = SIM SMS + trunk SIP, never VoIP-only)'
        )
    if normalized.get('phone_voice') and not normalized.get('voice'):
        raise InstanceError(
            'features.phone_voice requires features.voice (realtime voice keys)'
        )
    if normalized.get('phone_sms') and not normalized.get('ingress'):
        raise InstanceError(
            'features.phone_sms requires features.ingress (webhook HTTPS)'
        )
    if normalized.get('phone_sms') and not public_hostname:
        raise InstanceError(
            'identity.public_hostname is required when features.phone_sms '
            'is true (sms.<domaine> webhook)'
        )
    if normalized.get('phone_sms') and not E164_RE.match(phone_sms_number):
        raise InstanceError(
            'identity.phone_sms_number must be E.164 (+336...) '
            'when features.phone_sms is true'
        )
    if normalized.get('phone_voice') and not E164_RE.match(phone_voice_number):
        raise InstanceError(
            'identity.phone_voice_number must be E.164 (+33162...) '
            'when features.phone_voice is true'
        )
    if sip_transport not in PHONE_VOICE_TRANSPORTS:
        raise InstanceError('phone_voice.sip_transport must be udp|tcp|tls')
    if max_calls < 1:
        raise InstanceError('phone_voice.max_calls_per_day must be >= 1')
    if normalized.get('phone_voice') and (not sip_server or not sip_username):
        raise InstanceError(
            'phone_voice.sip_server and phone_voice.sip_username are required '
            'when features.phone_voice is true'
        )
    raw_discord = as_table(data.get('discord'))
    discord = {
        key: str(raw_discord.get(key) or '').strip() for key in DISCORD_ID_KEYS
    }
    if normalized.get('discord'):
        for key in DISCORD_ID_KEYS:
            if not DISCORD_SNOWFLAKE_RE.match(discord[key]):
                raise InstanceError(
                    f'discord.{key} must be a Discord snowflake id '
                    'when features.discord is true'
                )
    mailbox = as_table(data.get('mailbox'))
    if normalized.get('mailbox'):
        try:
            resolve_mailbox(mailbox)
        except MailboxError as exc:
            raise InstanceError(f'mailbox invalide : {exc}') from exc
    testing = _validate_testing(as_table(data.get('testing')))
    return {
        'schema_version': 1,
        'instance_id': instance_id,
        'mode': mode,
        'identity': {
            'hostname': str(identity.get('hostname') or '').strip(),
            'public_hostname': public_hostname,
            'phone_sms_number': phone_sms_number,
            'phone_voice_number': phone_voice_number,
        },
        'paths': {
            'home': str(paths['home']).strip(),
            'system_root': str(paths['system_root']).strip(),
            'policy': str(paths['policy']).strip(),
            'config_root': str(paths.get('config_root') or '').strip(),
            'secrets_age': str(
                paths.get('secrets_age') or 'serge.secrets.age'
            ).strip(),
        },
        'features': normalized,
        'llm': as_table(data.get('llm')),
        'ingress': as_table(data.get('ingress')),
        'phone_voice': {
            'sip_server': sip_server,
            'sip_username': sip_username,
            'sip_transport': sip_transport,
            'max_calls_per_day': max_calls,
        },
        'discord': discord,
        'mailbox': mailbox,
        'testing': testing,
    }


def _validate_testing(raw: dict[str, Any]) -> dict[str, int]:
    """Topologie à froid des market tests (B4) : N + seuils kill/scale.

    Absente = défauts validés en A. Modifiable via Mission Control
    uniquement à froid (0 campagne RUNNING) — lock ailleurs.
    """
    defaults = {
        'n_smoke_min': 30,
        'n_smoke_max': 50,
        'n_full_min': 150,
        'n_full_target': 200,
        'kill_max_positives': 1,
        'scale_min_positives': 5,
        'scale_min_meetings': 2,
        'extend_max': 1,
    }
    values: dict[str, int] = {}
    for key, default in defaults.items():
        try:
            values[key] = int(raw.get(key, default))
        except (TypeError, ValueError):
            raise InstanceError(f'testing.{key} must be an integer') from None
    if not 0 < values['n_smoke_min'] <= values['n_smoke_max']:
        raise InstanceError('testing needs 0 < n_smoke_min <= n_smoke_max')
    if not 0 < values['n_full_min'] <= values['n_full_target']:
        raise InstanceError('testing needs 0 < n_full_min <= n_full_target')
    if not values['kill_max_positives'] < values['scale_min_positives']:
        raise InstanceError(
            'testing needs kill_max_positives < scale_min_positives'
        )
    if values['scale_min_meetings'] < 1 or values['extend_max'] < 1:
        raise InstanceError('testing scale/extend bounds must be >= 1')
    return values


def sidecar_path(toml_path: Path, data: Mapping[str, Any]) -> Path:
    raw = str(
        (data.get('paths') or {}).get('secrets_age') or 'serge.secrets.age'
    )
    target = Path(raw)
    if not target.is_absolute():
        target = toml_path.parent / target
    return target


def load_manifest(system_root: Path | None = None) -> dict[str, Any]:
    path = (
        system_root or _repo_root()
    ) / 'schemas/serge.secrets.manifest.yaml'
    try:
        payload = yaml.safe_load(path.read_text(encoding='utf-8'))
    except (OSError, yaml.YAMLError) as exc:
        raise InstanceError(f'secrets manifest unreadable: {path}') from exc
    if not isinstance(payload, dict):
        raise InstanceError('secrets manifest invalid')
    return payload


def required_secret_names(
    features: Mapping[str, bool],
    manifest: Mapping[str, Any] | None = None,
) -> list[str]:
    payload = manifest or load_manifest()
    needed: list[str] = list(ALWAYS_REQUIRED_SECRETS)
    for item in payload.get('keys') or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or '')
        feature = str(item.get('required_when_feature') or '')
        if feature == 'llm' or name in ALWAYS_REQUIRED_SECRETS:
            continue
        if feature == 'voice':
            continue
        if feature and features.get(feature):
            needed.append(name)
    return list(dict.fromkeys(needed))


def multiline_secret_names(
    features: Mapping[str, bool],
    manifest: Mapping[str, Any] | None = None,
) -> list[str]:
    """Secrets marqués multiline au manifeste (feature on).

    Args:
        features: Features activées.
        manifest: Manifeste (défaut : chargé du repo).

    Returns:
        Noms à saisir/injecter sur plusieurs lignes (ex. gog_env).
    """
    payload = manifest or load_manifest()
    names: list[str] = []
    for item in payload.get('keys') or []:
        if not isinstance(item, dict) or not item.get('multiline'):
            continue
        feature = str(item.get('required_when_feature') or '')
        name = str(item.get('name') or '')
        if feature and name and features.get(feature):
            names.append(name)
    return names


SIDECAR_V2_MARKER = '# serge-sidecar v2 (multiline \\n-escaped)'
_UNESCAPE_RE = re.compile(r'\\\\|\\n')


def escape_sidecar_value(value: str) -> str:
    """Échappe une valeur sidecar (\\ puis \n, \r supprimés).

    Args:
        value: Valeur brute (mono ou multiligne).

    Returns:
        Valeur sûre sur une ligne dotenv (round-trip via parse_dotenv).
    """
    return value.replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '')


def _unescape_sidecar(value: str) -> str:
    """Déséchappe une valeur sidecar v2 (\\n -> LF, \\\\ -> \\)."""
    return _UNESCAPE_RE.sub(
        lambda m: '\\' if m.group(0) == '\\\\' else '\n', value
    )


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse un sidecar dotenv (v2 si marqueur en tête, legacy sinon).

    Args:
        text: Contenu du sidecar (déchiffré ou clair).

    Returns:
        Noms → valeurs (multiligne restauré en v2, brut en legacy).
    """
    values: dict[str, str] = {}
    v2 = text.startswith(SIDECAR_V2_MARKER)
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        cleaned = value.strip().strip('"').strip("'")
        values[key.strip()] = _unescape_sidecar(cleaned) if v2 else cleaned
    return values


def load_secret_map(sidecar: Path) -> dict[str, str]:
    """Decrypt age when possible; tests may use a dotenv sidecar or SERGE_SECRETS_DOTENV."""
    override = os.environ.get('SERGE_SECRETS_DOTENV', '').strip()
    if override:
        path = Path(override)
        if not path.is_file():
            raise InstanceError(f'SERGE_SECRETS_DOTENV missing: {path}')
        return parse_dotenv(path.read_text(encoding='utf-8'))
    if not sidecar.is_file():
        raise InstanceError(f'secrets sidecar missing: {sidecar}')
    if sidecar.suffix == '.age':
        allow_plain = os.environ.get(
            'SERGE_INSTANCE_ALLOW_PLAINTEXT_SECRETS', ''
        ).strip() in {
            '1',
            'true',
            'TRUE',
            'yes',
        }
        plaintext = sidecar.with_suffix('')
        if allow_plain and plaintext.is_file():
            return parse_dotenv(plaintext.read_text(encoding='utf-8'))
        identity = os.environ.get('SERGE_AGE_IDENTITY', '').strip()
        if not identity:
            raise InstanceError(
                'serge.secrets.age present but SERGE_AGE_IDENTITY unset '
                '(or pass SERGE_SECRETS_DOTENV for tests)'
            )
        import subprocess

        completed = subprocess.run(
            ['age', '-d', '-i', identity, str(sidecar)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise InstanceError('failed to decrypt serge.secrets.age')
        return parse_dotenv(completed.stdout)
    return parse_dotenv(sidecar.read_text(encoding='utf-8'))


def assert_secrets_complete(
    features: Mapping[str, bool],
    secrets: Mapping[str, str],
    manifest: Mapping[str, Any] | None = None,
) -> list[str]:
    required = required_secret_names(features, manifest)
    missing = [
        name for name in required if not str(secrets.get(name) or '').strip()
    ]
    if features.get('voice'):
        xai = str(secrets.get('xai_api_key') or '').strip()
        openai = str(secrets.get('openai_api_key') or '').strip()
        if xai:
            required.append('xai_api_key')
        elif openai:
            required.append('openai_api_key')
        elif 'xai_api_key' not in missing:
            missing.append('xai_api_key')
    if missing:
        raise InstanceError(
            'secrets incomplete for enabled features: ' + ', '.join(missing)
        )
    return required


def load_instance(path: Path | None = None) -> dict[str, Any]:
    raw = os.environ.get('SERGE_INSTANCE_FILE', '').strip()
    selected = Path(path or raw)
    if not raw and path is None:
        raise InstanceError('SERGE_INSTANCE_FILE is required to boot')
    if not selected.is_file():
        raise InstanceError(f'SERGE_INSTANCE_FILE missing: {selected}')
    data = validate_toml(load_toml(selected))
    sidecar = sidecar_path(selected, data)
    system_root = Path(data['paths']['system_root'])
    manifest = load_manifest(
        system_root if (system_root / 'schemas').is_dir() else _repo_root()
    )
    secrets = load_secret_map(sidecar)
    present = assert_secrets_complete(data['features'], secrets, manifest)
    home = Path(data['paths']['home'])
    config_root = Path(
        data['paths']['config_root'] or (home / '.config/serge')
    )
    return {
        'instance_file': str(selected.resolve()),
        'instance_id': data['instance_id'],
        'mode': data['mode'],
        'paths': {
            **data['paths'],
            'config_root': str(config_root),
            'secrets_age': str(sidecar),
        },
        'features': data['features'],
        'identity': data['identity'],
        'phone_voice': data['phone_voice'],
        'secret_names_present': present,
        'secret_values_included': False,
    }


def apply_env(loaded: Mapping[str, Any]) -> dict[str, str]:
    paths = loaded['paths']
    exported = {
        'SERGE_INSTANCE_FILE': str(loaded['instance_file']),
        'SERGE_HOME': str(paths['home']),
        'SERGE_SYSTEM_ROOT': str(paths['system_root']),
        'SERGE_MANDATE_PATH': str(paths['policy']),
        'SERGE_POLICY_PATH': str(paths['policy']),
    }
    os.environ.update(exported)
    return exported


def command_requires_instance(command: str) -> bool:
    return command in SERGECTL_BOOT_COMMANDS


def require_instance() -> dict[str, Any]:
    loaded = load_instance()
    apply_env(loaded)
    return loaded
