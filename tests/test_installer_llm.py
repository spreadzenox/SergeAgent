#!/usr/bin/env python3
"""Installer LLM-first: catalog, guide, slots, unified install paths."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kit.guide import Guide  # noqa: E402
from kit.instance_wizard import (  # noqa: E402
    default_answers,
    normalize_answers,
    render_toml,
    write_couple,
)
from kit.llm_slots import slots_from_llm, write_llm_slots  # noqa: E402
from kit.mandate import build_mandate, render_yaml  # noqa: E402
from kit.openrouter import (  # noqa: E402
    RECOMMENDED_TIERS,
    OpenRouterError,
    chat_completion,
    fetch_models,
    format_model_line,
    search_models,
)

LIVE_TIERS = {
    't1': 'xiaomi/mimo-v2.5',
    't2': 'deepseek/deepseek-v4-flash-0731',
    't3': 'z-ai/glm-5.3-flash',
}

MODELS_PAYLOAD = {
    'data': [
        {
            'id': 'xiaomi/mimo-v2.5',
            'name': 'Xiaomi: MiMo-V2.5',
            'context_length': 1050000,
            'pricing': {'prompt': '0.00000014', 'completion': '0.00000028'},
        },
        {
            'id': 'some/other-model',
            'name': 'Other',
            'context_length': 32000,
            'pricing': {'prompt': '0.000001', 'completion': '0.000002'},
        },
        {'id': '', 'name': 'Broken'},
    ]
}


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode('utf-8')

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _answers(tmp: Path) -> dict:
    home = tmp / 'home'
    answers = default_answers()
    answers['instance_id'] = 'alice-laptop'
    answers['paths'] = {
        'home': str(home),
        'system_root': str(tmp / 'dest'),
        'policy': str(home / '.config/serge/mandate.yaml'),
        'config_root': str(home / '.config/serge'),
        'secrets_age': 'serge.secrets',
    }
    answers['features'] = {key: False for key in answers['features']}
    answers['secrets'] = {'openrouter_api_key': 'test-openrouter'}
    answers['mandate'] = {
        'policy_owner': 'alice',
        'email': 'alice@example.com',
    }
    return answers


def _seed_repo(path: Path) -> str:
    path.mkdir(parents=True)
    (path / 'README').write_text('seed\n', encoding='utf-8')
    subprocess.run(['git', 'init'], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ['git', 'add', '.'], cwd=path, check=True, capture_output=True
    )
    subprocess.run(
        [
            'git',
            '-c',
            'user.email=t@example.com',
            '-c',
            'user.name=T',
            'commit',
            '-m',
            'seed',
        ],
        cwd=path,
        check=True,
        capture_output=True,
    )
    out = subprocess.run(
        ['git', 'rev-parse', 'HEAD'],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


class OpenRouterTests(unittest.TestCase):
    def test_recommended_tiers_match_live(self) -> None:
        self.assertEqual(RECOMMENDED_TIERS, LIVE_TIERS)

    def test_fetch_models_parses_and_sorts(self) -> None:
        with mock.patch(
            'urllib.request.urlopen',
            return_value=_FakeResponse(MODELS_PAYLOAD),
        ):
            models = fetch_models('dummy-key')
        self.assertEqual(len(models), 2)
        self.assertEqual(models[0]['id'], 'xiaomi/mimo-v2.5')
        self.assertAlmostEqual(models[0]['prompt_usd'], 0.14)
        self.assertAlmostEqual(models[0]['completion_usd'], 0.28)

    def test_fetch_models_failure_raises(self) -> None:
        with mock.patch(
            'urllib.request.urlopen',
            side_effect=urllib.error.URLError('down'),
        ):
            with self.assertRaises(OpenRouterError):
                fetch_models('dummy-key')

    def test_search_and_format(self) -> None:
        with mock.patch(
            'urllib.request.urlopen',
            return_value=_FakeResponse(MODELS_PAYLOAD),
        ):
            models = fetch_models()
        hits = search_models(models, 'mimo')
        self.assertEqual([item['id'] for item in hits], ['xiaomi/mimo-v2.5'])
        line = format_model_line(models[0])
        self.assertIn('xiaomi/mimo-v2.5', line)
        self.assertIn('$0.14', line)

    def test_chat_completion_returns_text(self) -> None:
        payload = {'choices': [{'message': {'content': '  Bonjour  '}}]}
        with mock.patch(
            'urllib.request.urlopen', return_value=_FakeResponse(payload)
        ):
            text = chat_completion(
                'k', 'm', [{'role': 'user', 'content': 'q'}]
            )
        self.assertEqual(text, 'Bonjour')

    def test_chat_completion_empty_raises(self) -> None:
        payload = {'choices': [{'message': {'content': '  '}}]}
        with mock.patch(
            'urllib.request.urlopen', return_value=_FakeResponse(payload)
        ):
            with self.assertRaises(OpenRouterError):
                chat_completion('k', 'm', [{'role': 'user', 'content': 'q'}])


class GuideTests(unittest.TestCase):
    def test_offline_returns_static_hint(self) -> None:
        guide = Guide()
        self.assertFalse(guide.ready)
        answer = guide.ask('c’est quoi T1 ?', 'modeles')
        self.assertIn('T1', answer)

    def test_live_failure_falls_back(self) -> None:
        guide = Guide('k', 'm')
        self.assertTrue(guide.ready)
        with mock.patch(
            'urllib.request.urlopen',
            side_effect=urllib.error.URLError('down'),
        ):
            answer = guide.ask('c’est quoi T1 ?', 'modeles')
        self.assertIn('T1', answer)
        self.assertIn('locale', answer)

    def test_live_answer_passthrough(self) -> None:
        guide = Guide('k', 'm')
        payload = {'choices': [{'message': {'content': 'Réponse live'}}]}
        with mock.patch(
            'urllib.request.urlopen', return_value=_FakeResponse(payload)
        ):
            self.assertEqual(guide.ask('q ?', 'phone'), 'Réponse live')


class LlmWizardTests(unittest.TestCase):
    def test_defaults_carry_live_models(self) -> None:
        llm = default_answers()['llm']
        self.assertEqual(llm['t1_model'], LIVE_TIERS['t1'])
        self.assertEqual(llm['t2_model'], LIVE_TIERS['t2'])
        self.assertEqual(llm['t3_model'], LIVE_TIERS['t3'])
        self.assertEqual(llm['guide_model'], LIVE_TIERS['t2'])

    def test_old_answers_without_models_get_defaults(self) -> None:
        raw = default_answers()
        raw['llm'] = {'provider': 'openrouter', 'referer': ''}
        llm = normalize_answers(raw)['llm']
        self.assertEqual(llm['t1_model'], LIVE_TIERS['t1'])
        self.assertEqual(llm['guide_model'], LIVE_TIERS['t2'])

    def test_toml_renders_llm_models(self) -> None:
        answers = default_answers()
        answers['discord'] = {
            key: '123456789012345678' for key in answers['discord']
        }
        text = render_toml(answers)
        self.assertIn('[llm]', text)
        self.assertIn('t1_model = "xiaomi/mimo-v2.5"', text)
        self.assertIn('t2_model = "deepseek/deepseek-v4-flash-0731"', text)
        self.assertIn('t3_model = "z-ai/glm-5.3-flash"', text)
        self.assertIn('guide_model = "deepseek/deepseek-v4-flash-0731"', text)

    def test_slots_mapping_and_fallback(self) -> None:
        slots = slots_from_llm(default_answers()['llm'])
        self.assertEqual(
            slots['slots']['CHEAP']['openrouter_id'], LIVE_TIERS['t1']
        )
        self.assertEqual(
            slots['slots']['DEFAULT']['model_ref'],
            f'openrouter/{LIVE_TIERS["t2"]}',
        )
        self.assertEqual(
            slots['slots']['SMART']['openrouter_id'], LIVE_TIERS['t3']
        )
        self.assertFalse(slots['secret_values_included'])
        fallback = slots_from_llm({})
        self.assertEqual(
            fallback['slots']['DEFAULT']['openrouter_id'], LIVE_TIERS['t2']
        )

    def test_write_slots_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            config = Path(raw)
            dest = write_llm_slots(config, default_answers()['llm'])
            self.assertEqual(dest, config / 'llm/slots.json')
            self.assertEqual(oct(dest.stat().st_mode & 0o777), '0o644')
            payload = json.loads(dest.read_text(encoding='utf-8'))
            self.assertEqual(
                payload['slots']['CHEAP']['openrouter_id'], LIVE_TIERS['t1']
            )


class InstallerTests(unittest.TestCase):
    def _load_installer(self):  # noqa: ANN202
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            'serge_installer', str(ROOT / 'scripts' / 'serge-install.py')
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_existing_couple_builds_with_slots(self) -> None:
        installer = self._load_installer()
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            sha = _seed_repo(tmp / 'source')
            couple = tmp / 'couple'
            write_couple(_answers(tmp), couple, allow_plaintext=True)
            mandate = tmp / 'mandate.yaml'
            mandate.write_text(
                render_yaml(
                    build_mandate(
                        {
                            'policy_owner': 'alice',
                            'email': 'alice@example.com',
                            'mode': 'sandbox',
                        }
                    )
                ),
                encoding='utf-8',
            )
            out = io.StringIO()
            with mock.patch.object(sys, 'stdout', out):
                code = installer.main(
                    [
                        '--instance-file',
                        str(couple / 'serge.instance.toml'),
                        '--mandate',
                        str(mandate),
                        '--source-repo',
                        str(tmp / 'source'),
                        '--git-sha',
                        sha,
                        '--systemd-user-dir',
                        str(tmp / 'systemd'),
                        '--no-enable-units',
                    ]
                )
            self.assertEqual(code, 0)
            slots = tmp / 'home/.config/serge/llm/slots.json'
            self.assertTrue(slots.is_file())
            payload = json.loads(slots.read_text(encoding='utf-8'))
            self.assertEqual(
                payload['slots']['SMART']['openrouter_id'], LIVE_TIERS['t3']
            )
            self.assertIn('llm_slots', out.getvalue())

    def test_answers_path_generates_then_builds(self) -> None:
        installer = self._load_installer()
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            sha = _seed_repo(tmp / 'source')
            answers_file = tmp / 'answers.json'
            answers_file.write_text(
                json.dumps(_answers(tmp)), encoding='utf-8'
            )
            out = io.StringIO()
            with mock.patch.object(sys, 'stdout', out):
                code = installer.main(
                    [
                        '--answers',
                        str(answers_file),
                        '--out-dir',
                        str(tmp / 'couple'),
                        '--allow-plaintext-secrets',
                        '--also-mandate',
                        '--mandate-out',
                        str(tmp / 'mandate.yaml'),
                        '--source-repo',
                        str(tmp / 'source'),
                        '--git-sha',
                        sha,
                        '--systemd-user-dir',
                        str(tmp / 'systemd'),
                        '--no-enable-units',
                    ]
                )
            self.assertEqual(code, 0)
            self.assertTrue((tmp / 'couple/serge.instance.toml').is_file())
            self.assertIn('Instance construite', out.getvalue())

    def test_existing_couple_requires_mandate_and_repo(self) -> None:
        installer = self._load_installer()
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            couple = tmp / 'couple'
            write_couple(_answers(tmp), couple, allow_plaintext=True)
            err = io.StringIO()
            with (
                mock.patch.object(sys, 'stdout', io.StringIO()),
                mock.patch.object(sys, 'stderr', err),
            ):
                code = installer.main(
                    ['--instance-file', str(couple / 'serge.instance.toml')]
                )
            self.assertEqual(code, 2)
            self.assertIn('--mandate', err.getvalue())


if __name__ == '__main__':
    unittest.main()
