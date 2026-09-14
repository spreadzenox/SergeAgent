#!/usr/bin/env python3
"""Asterisk render: locked CLI, loopback bind, password only in pjsip."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kit.asterisk import (  # noqa: E402
    AsteriskError,
    config_filenames,
    render_asterisk,
)


def _loaded(**overrides):
    payload = {
        'features': {'phone_voice': True},
        'paths': {
            'home': '/home/owner',
            'system_root': '/home/owner/serge-system',
            'config_root': '/home/owner/.config/serge',
        },
        'identity': {'phone_voice_number': '+33162000001'},
        'phone_voice': {
            'sip_server': 'sip.example.com',
            'sip_username': 'trunk',
            'sip_transport': 'tls',
            'max_calls_per_day': 50,
        },
    }
    payload.update(overrides)
    return payload


class AsteriskRenderTests(unittest.TestCase):
    def test_renders_five_files_with_modes(self) -> None:
        rendered = render_asterisk(
            _loaded(),
            {'user': 'owner', 'uid': '1000'},
            {'sip_trunk_password': 's3cret'},
        )
        self.assertEqual(set(rendered), set(config_filenames()))
        self.assertEqual(rendered['pjsip.conf'][1], 0o600)
        self.assertEqual(rendered['extensions.conf'][1], 0o644)

    def test_cli_locked_and_loopback(self) -> None:
        rendered = render_asterisk(
            _loaded(),
            {'user': 'owner', 'uid': '1000'},
            {'sip_trunk_password': 's3cret'},
        )
        extensions = rendered['extensions.conf'][0]
        self.assertIn('Set(CALLERID(num)=+33162000001)', extensions)
        self.assertIn('[serge-dial]', extensions)
        self.assertIn('[serge-pai]', extensions)
        self.assertIn(
            'P-Asserted-Identity)=<sip:+33162000001@sip.example.com>',
            extensions,
        )
        self.assertIn('b(serge-pai^add^1)', extensions)
        self.assertIn('U(serge-s2s^${EXTEN})', extensions)
        self.assertIn('[serge-s2s]', extensions)
        self.assertIn('serge-campaign', extensions)
        self.assertIn('Wait(180)', extensions)
        self.assertIn(
            'AudioSocket(aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee,127.0.0.1:8792)',
            extensions,
        )
        self.assertIn('AGI(turn.py,', extensions)
        self.assertGreater(
            extensions.index('AudioSocket('),
            extensions.index('Answer()'),
        )
        self.assertGreater(
            extensions.index('AGI(turn.py,'),
            extensions.index('AudioSocket('),
        )
        self.assertNotIn('serge_voice_turn.py', extensions)
        pjsip = rendered['pjsip.conf'][0]
        self.assertIn('bind = 0.0.0.0:5061', pjsip)
        self.assertIn('server_uri = sip:sip.example.com:5061', pjsip)
        self.assertIn('verify_server = no', pjsip)
        self.assertIn('allow_wildcard_certs = yes', pjsip)
        self.assertIn('type = identify', pjsip)
        self.assertIn('media_encryption = sdes', pjsip)
        self.assertIn('callerid = +33162000001', pjsip)
        self.assertIn('from_domain = sip.example.com', pjsip)
        self.assertIn('send_pai = yes', pjsip)
        self.assertIn('qualify_frequency = 0', pjsip)
        self.assertNotIn('bind = 127.0.0.1', pjsip)

    def test_udp_trunk_uses_5060_without_tls_knobs(self) -> None:
        rendered = render_asterisk(
            _loaded(
                phone_voice={
                    'sip_server': 'sip.example.com',
                    'sip_username': 'trunk',
                    'sip_transport': 'udp',
                    'max_calls_per_day': 50,
                }
            ),
            {'user': 'owner', 'uid': '1000'},
            {'sip_trunk_password': 's3cret'},
        )
        pjsip = rendered['pjsip.conf'][0]
        self.assertIn('bind = 0.0.0.0:5060', pjsip)
        self.assertIn('server_uri = sip:sip.example.com:5060', pjsip)
        self.assertNotIn('verify_server', pjsip)
        self.assertNotIn('media_encryption', pjsip)

    def test_password_only_in_pjsip(self) -> None:
        rendered = render_asterisk(
            _loaded(),
            {'user': 'owner', 'uid': '1000'},
            {'sip_trunk_password': 's3cret-unique'},
        )
        self.assertIn('s3cret-unique', rendered['pjsip.conf'][0])
        for name in (
            'asterisk.conf',
            'extensions.conf',
            'rtp.conf',
            'modules.conf',
        ):
            self.assertNotIn('s3cret-unique', rendered[name][0], name)

    def test_paths_are_instance_derived(self) -> None:
        rendered = render_asterisk(
            _loaded(),
            {'user': 'owner', 'uid': '1000'},
            {'sip_trunk_password': 's3cret'},
        )
        asterisk_conf = rendered['asterisk.conf'][0]
        self.assertIn('[directories]', asterisk_conf)
        self.assertNotIn('[directories](!)', asterisk_conf)
        self.assertIn('astdatadir => /var/lib/asterisk', asterisk_conf)
        self.assertIn(
            'astspooldir => /home/owner/.config/serge/asterisk/var/spool',
            asterisk_conf,
        )
        self.assertIn(
            'astcachedir => /run/user/1000/serge-asterisk/cache',
            asterisk_conf,
        )
        self.assertIn('/home/owner/.config/serge/asterisk', asterisk_conf)
        self.assertIn('serge/voice', asterisk_conf)
        self.assertIn('/run/user/1000/serge-asterisk', asterisk_conf)
        self.assertNotIn('/home/serge', asterisk_conf)
        self.assertNotIn('/run/user/1002', asterisk_conf)

    def test_refuses_without_feature_or_trunk(self) -> None:
        with self.assertRaises(AsteriskError):
            render_asterisk(
                _loaded(features={'phone_voice': False}),
                {'user': 'owner', 'uid': '1000'},
                {'sip_trunk_password': 's3cret'},
            )
        with self.assertRaises(AsteriskError):
            render_asterisk(
                _loaded(),
                {'user': 'owner', 'uid': '1000'},
                {},
            )


if __name__ == '__main__':
    unittest.main()
