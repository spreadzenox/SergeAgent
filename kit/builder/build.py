#!/usr/bin/env python3
"""Builder entry: load inputs, assemble the virgin instance, write receipt."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kit.builder.guards import (
    assert_instance_paths_safe,
    assert_metagrok_ok,
    assert_not_live_path,
)
from kit.builder.install import (
    can_enable_in_session,
    enable_units,
    install_couple,
    install_mandate,
    write_units,
)
from kit.builder.secrets import inject_secrets
from kit.builder.seed import (
    create_empty_canon,
    ensure_writable_tree,
    git_archive_into,
    resolve_git_sha,
    scrub_live_memory,
)
from kit.builder.telephony import (
    seed_sms_route,
    write_asterisk,
    write_voice_readme,
)
from kit.instance_file import (
    assert_secrets_complete,
    load_secret_map,
    load_toml,
    sidecar_path,
    validate_toml,
)
from kit.llm_slots import write_llm_slots
from kit.units import host_facts_from_instance


def load_build_inputs(
    instance_file: Path,
) -> tuple[dict[str, Any], dict[str, str]]:
    data = validate_toml(load_toml(instance_file))
    sidecar = sidecar_path(instance_file, data)
    secrets = load_secret_map(sidecar)
    assert_secrets_complete(data['features'], secrets)
    home = Path(data['paths']['home'])
    config_root = Path(
        data['paths']['config_root'] or (home / '.config/serge')
    )
    loaded = {
        'instance_file': str(instance_file.resolve()),
        'instance_id': data['instance_id'],
        'mode': data['mode'],
        'paths': {
            **data['paths'],
            'config_root': str(config_root),
            'secrets_age': str(sidecar),
        },
        'features': data['features'],
        'identity': data['identity'],
        'ingress': data.get('ingress') or {},
        'phone_voice': data.get('phone_voice') or {},
        'llm': data.get('llm') or {},
        'secret_values_included': False,
    }
    return loaded, secrets


def build_instance(
    *,
    instance_file: Path,
    mandate: Path,
    source_repo: Path,
    git_sha: str = 'HEAD',
    systemd_user_dir: Path | None = None,
    enable: bool = True,
    confirm_live_id: str = '',
    kit_root: Path | None = None,
    uid: int | None = None,
) -> dict[str, Any]:
    loaded, secrets = load_build_inputs(instance_file)
    assert_instance_paths_safe(loaded, confirm_live_id=confirm_live_id)
    assert_metagrok_ok(loaded['features'])
    system_root = Path(loaded['paths']['system_root'])
    home = Path(loaded['paths']['home'])
    config_root = Path(loaded['paths']['config_root'])
    policy = Path(loaded['paths']['policy'])
    user_systemd = systemd_user_dir or (home / '.config/systemd/user')
    assert_not_live_path(
        user_systemd,
        confirm_live=confirm_live_id == 'julien-vps'
        and loaded['instance_id'] == 'julien-vps',
    )
    sha = resolve_git_sha(source_repo, git_sha)
    git_archive_into(source_repo, sha, system_root)
    removed = scrub_live_memory(system_root, kit_root)
    ensure_writable_tree(system_root)
    canon = create_empty_canon(system_root)
    install_mandate(mandate, policy, instance_id=loaded['instance_id'])
    installed_toml = install_couple(instance_file, loaded, config_root)
    loaded = dict(loaded)
    loaded['instance_file'] = str(installed_toml.resolve())
    secret_names = inject_secrets(
        secrets,
        loaded['features'],
        home=home,
        config_root=config_root,
    )
    facts = host_facts_from_instance(loaded, uid=uid)
    llm_slots_path = write_llm_slots(config_root, loaded.get('llm') or {})
    asterisk_files: list[str] = []
    sms_route = ''
    if loaded['features'].get('phone_voice'):
        asterisk_files = write_asterisk(loaded, secrets, config_root, facts)
        write_voice_readme(config_root)
    if loaded['features'].get('phone_sms'):
        sms_route = seed_sms_route(
            system_root,
            installed_toml,
            str(loaded['identity'].get('public_hostname') or ''),
        )
    units = write_units(loaded, user_systemd, facts=facts, kit_root=kit_root)
    enabled: list[str] = []
    enable_skipped = ''
    if enable:
        if can_enable_in_session(user_systemd):
            enabled = enable_units(list(units['enable']))['enabled']
        else:
            enable_skipped = 'systemd_user_dir is not this user session'
    receipt = {
        'status': 'built',
        'instance_id': loaded['instance_id'],
        'mode': loaded['mode'],
        'git_sha': sha,
        'system_root': str(system_root),
        'instance_file': loaded['instance_file'],
        'canon': canon,
        'secret_names_written': secret_names,
        'secret_values_included': False,
        'asterisk_files_written': asterisk_files,
        'sms_route': sms_route,
        'llm_slots': str(llm_slots_path),
        'units_written': sorted(units['files']),
        'units_enable': units['enable'],
        'units_enabled': enabled,
        'units_enable_skipped': enable_skipped,
        'metagrok_units_included': False,
        'scrubbed': removed,
        'live_host': False,
        'built_at': datetime.now(UTC).isoformat(),
    }
    receipt_path = system_root / 'state/instance-build.json'
    receipt_path.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8',
    )
    return receipt
