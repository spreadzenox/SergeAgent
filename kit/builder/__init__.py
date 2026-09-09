#!/usr/bin/env python3
"""Instantiate a virgin Serge from git archive + instance couple. Does not touch live VPS."""

from __future__ import annotations

from kit.builder.build import build_instance, load_build_inputs
from kit.builder.guards import (
    LIVE_PREFIXES,
    METAGROK_MARKERS,
    BuilderError,
    assert_instance_paths_safe,
    assert_metagrok_ok,
    assert_not_live_path,
    live_mandate_markers,
)
from kit.builder.install import (
    can_enable_in_session,
    enable_units,
    install_couple,
    install_mandate,
    session_systemd_user_dir,
    write_units,
)
from kit.builder.secrets import (
    inject_secrets,
    secret_destination,
    secret_file_body,
)
from kit.builder.seed import (
    WRITABLE_DIRS,
    create_empty_canon,
    dest_is_empty,
    ensure_writable_tree,
    exclusions_payload,
    git_archive_into,
    resolve_git_sha,
    scrub_live_memory,
)
from kit.builder.telephony import (
    VOICE_README,
    seed_sms_route,
    write_asterisk,
    write_voice_readme,
)

__all__ = [
    'BuilderError',
    'LIVE_PREFIXES',
    'METAGROK_MARKERS',
    'VOICE_README',
    'WRITABLE_DIRS',
    'assert_instance_paths_safe',
    'assert_metagrok_ok',
    'assert_not_live_path',
    'build_instance',
    'can_enable_in_session',
    'create_empty_canon',
    'dest_is_empty',
    'enable_units',
    'ensure_writable_tree',
    'exclusions_payload',
    'git_archive_into',
    'inject_secrets',
    'install_couple',
    'install_mandate',
    'live_mandate_markers',
    'load_build_inputs',
    'resolve_git_sha',
    'scrub_live_memory',
    'secret_destination',
    'secret_file_body',
    'seed_sms_route',
    'session_systemd_user_dir',
    'write_asterisk',
    'write_units',
    'write_voice_readme',
]
