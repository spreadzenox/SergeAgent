#!/usr/bin/env python3
"""Voice bridge: health refused without instance, originate validation."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.voice import VoiceBrokerDenied  # noqa: E402
from serge.voice import bridge as voice_bridge  # noqa: E402


class VoiceBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = {
            key: os.environ.get(key)
            for key in (
                'SERGE_INSTANCE_FILE',
                'SERGE_SYSTEM_ROOT',
                'SERGE_MANDATE_PATH',
            )
        }

    def tearDown(self) -> None:
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_health_refused_without_instance_file(self) -> None:
        os.environ.pop('SERGE_INSTANCE_FILE', None)
        info = voice_bridge.health()
        self.assertEqual(info['status'], 'refused')

    def test_originate_validates_inputs_before_broker(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            toml = tmp / 'serge.instance.toml'
            toml.write_text(
                'schema_version = 1\ninstance_id = "t"\nmode = "live"\n'
                '[paths]\nhome = "/tmp/x"\nsystem_root = "/tmp/x"\n'
                'policy = "/tmp/x/m.yaml"\n'
                '[features]\nphone_voice = true\n'
                '[identity]\nphone_voice_number = "+33162000001"\n',
                encoding='utf-8',
            )
            os.environ['SERGE_INSTANCE_FILE'] = str(toml)
            os.environ['SERGE_SYSTEM_ROOT'] = str(tmp)
            with self.assertRaises(VoiceBrokerDenied):
                voice_bridge.originate(
                    request_id='x',
                    to_e164='+33612345678',
                    purpose='contract',
                )
            with self.assertRaises(VoiceBrokerDenied):
                voice_bridge.originate(
                    request_id='req_ok_1',
                    to_e164='bad',
                    purpose='contract',
                )

    def test_trunk_status_reports_missing_binary(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            toml = tmp / 'serge.instance.toml'
            toml.write_text(
                'schema_version = 1\ninstance_id = "t"\nmode = "live"\n'
                '[paths]\nhome = "/tmp/nonexistent-home-xyz"\n'
                'system_root = "/tmp/x"\npolicy = "/tmp/x/m.yaml"\n',
                encoding='utf-8',
            )
            os.environ['SERGE_INSTANCE_FILE'] = str(toml)
            with mock.patch.object(
                voice_bridge,
                'ASTERISK_BIN',
                Path('/nonexistent/asterisk'),
            ):
                status = voice_bridge.trunk_status()
        self.assertFalse(status['asterisk_binary'])
        self.assertFalse(status['registered'])

    def test_originate_dials_local_serge_dial_not_trunk(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            toml = tmp / 'serge.instance.toml'
            toml.write_text(
                'schema_version = 1\ninstance_id = "t"\nmode = "live"\n'
                '[paths]\nhome = "/tmp/x"\nsystem_root = "/tmp/x"\n'
                'policy = "/tmp/x/m.yaml"\n'
                '[features]\nphone_voice = true\n'
                '[identity]\nphone_voice_number = "+33162000001"\n',
                encoding='utf-8',
            )
            os.environ['SERGE_INSTANCE_FILE'] = str(toml)
            os.environ['SERGE_SYSTEM_ROOT'] = str(tmp)
            ledger = mock.Mock()
            ledger.request_call.return_value = {
                'decision': 'allowed',
                'reason': 'allowed',
                'cdr_id': 'cdr_test',
                'request_id': 'req_cli_1',
                'duplicate': False,
            }
            seen: list[tuple[str, ...]] = []

            def fake_cli(*command: str, timeout: float = 10.0):
                seen.append(command)
                return 0, 'ok'

            with (
                mock.patch.object(
                    voice_bridge, 'resolve_policy', return_value=mock.Mock()
                ),
                mock.patch.object(
                    voice_bridge,
                    'trunk_status',
                    return_value={'registered': True},
                ),
                mock.patch.object(voice_bridge, 'asterisk_cli', fake_cli),
            ):
                result = voice_bridge.originate(
                    request_id='req_cli_1',
                    to_e164='+33612345678',
                    purpose='test',
                    ledger=ledger,
                )
        self.assertTrue(result.get('originated'))
        self.assertEqual(seen[0][1], 'Local/+33612345678@serge-dial')
        self.assertNotIn('PJSIP/+33612345678@trunk', seen[0])


if __name__ == '__main__':
    unittest.main()
