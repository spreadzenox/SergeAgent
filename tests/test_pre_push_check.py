#!/usr/bin/env python3
"""Pre-push : sans clé = refus ; secret jamais affiché."""

from __future__ import annotations

import importlib.util
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_script():
    path = ROOT / 'scripts' / 'pre-push-check.py'
    spec = importlib.util.spec_from_file_location('pre_push_check', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _SkipLive:
    def id(self) -> str:
        return 'test_live_llm.LiveLlmTests.test_classify_reel'


class PrePushCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.script = _load_script()

    def test_sans_cle_refuse(self) -> None:
        buf = io.StringIO()
        with mock.patch.object(
            self.script, 'resolve_openrouter_key', return_value=''
        ):
            with mock.patch.object(self.script.sys, 'stderr', buf):
                self.assertEqual(self.script.run_pre_push(), 1)
        text = buf.getvalue()
        self.assertIn('push refusé', text)
        self.assertNotIn('sk-', text)

    def test_cle_jamais_affichee(self) -> None:
        fake = 'cle-fictive-ne-pas-afficher'
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=False):
            with mock.patch.object(
                self.script, 'resolve_openrouter_key', return_value=fake
            ):
                with mock.patch.object(
                    self.script, 'run_gates', return_value=0
                ):
                    with mock.patch.object(
                        self.script, 'run_deterministic', return_value=0
                    ):
                        with mock.patch.object(
                            self.script,
                            'run_live_llm_tests',
                            return_value=0,
                        ) as live:
                            with mock.patch.object(
                                self.script.sys, 'stderr', buf
                            ):
                                self.assertEqual(self.script.run_pre_push(), 0)
                            live.assert_called_once_with(fake)
        self.assertNotIn(fake, buf.getvalue())

    def test_live_llm_skippe_refuse(self) -> None:
        result = unittest.TestResult()
        result.skipped.append((_SkipLive(), 'OPENROUTER_API_KEY requise'))
        self.assertTrue(self.script.live_llm_skipped(result))

    def test_hook_isole_le_depot_courant_des_installations(self) -> None:
        from tests.test_serge_update import _git_seed

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            pushed = root / 'pushed'
            _git_seed(pushed)
            index = (pushed / '.git/index').read_bytes()
            config = (pushed / '.git/config').read_bytes()

            def gates():
                self.assertNotIn('GIT_DIR', os.environ)
                self.assertNotIn('GIT_INDEX_FILE', os.environ)
                return 0

            def scenario():
                _git_seed(root / 'temporary-installation')
                return 0

            with (
                mock.patch.dict(
                    os.environ,
                    {
                        'GIT_DIR': str(pushed / '.git'),
                        'GIT_WORK_TREE': str(pushed),
                        'GIT_INDEX_FILE': str(pushed / '.git/index'),
                    },
                ),
                mock.patch.object(
                    self.script,
                    'resolve_openrouter_key',
                    return_value='factice',
                ),
                mock.patch.object(self.script, 'run_gates', side_effect=gates),
                mock.patch.object(
                    self.script, 'run_deterministic', side_effect=scenario
                ),
                mock.patch.object(
                    self.script, 'run_live_llm_tests', return_value=0
                ),
            ):
                self.assertEqual(self.script.run_pre_push(), 0)
            self.assertEqual((pushed / '.git/index').read_bytes(), index)
            self.assertEqual((pushed / '.git/config').read_bytes(), config)


if __name__ == '__main__':
    unittest.main()
