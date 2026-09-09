#!/usr/bin/env python3
"""Mandate wizard produces a valid empty-owner mandate, never Julien's live file."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kit.mandate import (  # noqa: E402
    MandateError,
    build_mandate,
    render_yaml,
    sandbox_answers,
    validate_mandate,
)


def _load_mandate_file(path: Path) -> dict:
    """Read a mandate YAML file (local helper, no legacy resolver)."""
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise MandateError('mandate file is not a mapping')
    return data


LIVE_SENTINELS = (
    'live-owner',
    'live-owner.example.net',
    'live-owner@example.com',
    '999988887777666001',
)


class MandateWizardTests(unittest.TestCase):
    def _sandbox(self, **overrides):
        answers = sandbox_answers()
        answers['policy_owner'] = 'alice'
        answers['email'] = 'alice@example.com'
        answers.update(overrides)
        return answers

    def test_sandbox_mandate_valid_and_neutral(self):
        mandate = build_mandate(self._sandbox())
        validate_mandate(mandate)
        self.assertEqual(mandate['version'], 2)
        self.assertEqual(mandate['status'], 'sandbox_draft')
        self.assertFalse(mandate['mission']['operating_mode']['autonomous'])
        self.assertFalse(
            mandate['financial_policy']['payment_execution_enabled']
        )
        self.assertEqual(
            mandate['financial_policy']['card_monthly_limit_eur'], 0
        )
        self.assertNotIn(
            'operate_stripe_live_receive', mandate['autonomous_actions']
        )
        self.assertFalse(
            mandate['governance']['digital_operator'][
                'may_operate_stripe_live_receive'
            ]
        )
        text = render_yaml(mandate)
        for marker in LIVE_SENTINELS:
            self.assertNotIn(marker, text)

    def test_sandbox_mode_strips_live_money_even_if_asked(self):
        answers = self._sandbox()
        answers['features']['payments_live'] = True
        answers['financial']['payment_execution_enabled'] = True
        answers['financial']['card_monthly_limit_eur'] = 50
        mandate = build_mandate(answers)
        self.assertFalse(
            mandate['governance']['digital_operator'][
                'may_operate_stripe_live_receive'
            ]
        )
        self.assertEqual(
            mandate['financial_policy']['card_monthly_limit_eur'], 0
        )

    def test_sandbox_mode_strips_voice_outbound_but_keeps_sms_inbound(self):
        answers = self._sandbox()
        answers['features']['phone_sms'] = True
        answers['features']['phone_voice'] = True
        mandate = build_mandate(answers)
        sales = mandate['governance']['sales']
        self.assertFalse(sales['may_place_commercial_calls'])
        self.assertFalse(sales['may_answer_voice_calls'])
        self.assertNotIn(
            'place_bounded_commercial_calls_via_voice_broker',
            mandate['autonomous_actions'],
        )
        self.assertIn(
            'receive_sms_otp_via_broker',
            mandate['autonomous_actions'],
        )
        self.assertTrue(
            mandate['governance']['digital_operator']['may_receive_sms_otp']
        )
        phone = mandate['identity']['phone']
        self.assertTrue(phone['sms_inbound_allowed'])
        self.assertFalse(phone['voice_outbound_allowed'])
        self.assertFalse(phone['sms_outbound_allowed'])

    def test_live_voice_enables_sales_calling(self):
        answers = self._sandbox()
        answers['mode'] = 'live'
        answers['features']['phone_sms'] = True
        answers['features']['phone_voice'] = True
        mandate = build_mandate(answers)
        sales = mandate['governance']['sales']
        self.assertTrue(sales['may_place_commercial_calls'])
        self.assertTrue(sales['may_answer_voice_calls'])
        self.assertIn(
            'place_bounded_commercial_calls_via_voice_broker',
            mandate['autonomous_actions'],
        )
        self.assertIn(
            'answer_inbound_voice_calls',
            mandate['autonomous_actions'],
        )

    def test_live_payments_require_live_mode(self):
        answers = self._sandbox()
        answers['mode'] = 'live'
        answers['autonomous'] = True
        answers['features'] = {
            **answers['features'],
            'stripe': True,
            'payments_live': True,
        }
        answers['financial'] = {
            'card_monthly_limit_eur': 50,
            'maximum_one_off_eur': 30,
            'maximum_new_recurring_subscription_eur': 30,
            'payment_execution_enabled': True,
        }
        mandate = build_mandate(answers)
        self.assertEqual(mandate['status'], 'owner_authorized_v3')
        self.assertIn(
            'operate_stripe_live_receive', mandate['autonomous_actions']
        )
        self.assertTrue(
            mandate['financial_policy']['payment_execution_enabled']
        )

    def test_missing_email_or_owner_fails(self):
        with self.assertRaises(MandateError):
            build_mandate(sandbox_answers())
        answers = self._sandbox()
        answers['email'] = 'not-an-email'
        with self.assertRaises(MandateError):
            build_mandate(answers)

    def test_resolver_accepts_generated_file(self):
        mandate = build_mandate(self._sandbox())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'mandate.yaml'
            path.write_text(render_yaml(mandate), encoding='utf-8')
            loaded = _load_mandate_file(path)
            validate_mandate(loaded)
            self.assertEqual(loaded['identity']['email'], 'alice@example.com')

    def test_wizard_cli_writes_file(self):
        script = ROOT / 'scripts' / 'serge-mandate-wizard.py'
        with tempfile.TemporaryDirectory() as folder:
            answers = Path(folder) / 'answers.json'
            out = Path(folder) / 'mandate.yaml'
            answers.write_text(json.dumps(self._sandbox()), encoding='utf-8')
            import subprocess

            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    '--answers',
                    str(answers),
                    '--out',
                    str(out),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(out.is_file())
            loaded = _load_mandate_file(out)
            validate_mandate(loaded)
            self.assertEqual(loaded['policy_owner'], 'alice')

    def test_example_sandbox_file_validates(self):
        example = ROOT / 'policy-reference' / 'mandate.sandbox.example.yaml'
        loaded = _load_mandate_file(example)
        validate_mandate(loaded)
        text = example.read_text(encoding='utf-8')
        for marker in LIVE_SENTINELS:
            self.assertNotIn(marker, text)


if __name__ == '__main__':
    unittest.main()
