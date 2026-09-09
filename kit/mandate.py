#!/usr/bin/env python3
"""Build and validate a Serge root mandate. Same shape as live, no owner memory."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import yaml

MANDATE_VERSION = 2
REQUIRED_ROLES = (
    'director',
    'venture_scout',
    'sales',
    'builder',
    'digital_operator',
    'reviewer',
    'reducer',
)

# Instance-file features → mandate bits. Not secrets.
FEATURE_KEYS = (
    'public_web',
    'gmail',
    'accounts',
    'ingress',
    'stripe',
    'payments_live',
    'deploy_staging',
    'deploy_production',
    'phone_sms',
    'phone_voice',
)

HUMAN_ESCALATION = [
    'identity_document',
    'selfie_or_biometric_check',
    'kyc_or_aml_verification',
    'personal_signature',
    'tax_declaration_or_tax_identifier',
    'captcha_not_solvable_through_normal_browser_interaction',
    'contract_outside_standard_online_terms',
    'regulated_financial_account',
    'employment_or_credit_application',
    'action_exceeding_financial_policy',
    'use_of_personal_or_client_data_not_already_authorized',
]

FORBIDDEN_ACTIONS = [
    'invent_or_misrepresent_identity',
    'bypass_access_controls_or_antibot_protections',
    'create_duplicate_accounts_to_evade_service_rules',
    'expose_secrets_in_prompts_logs_email_or_workspace',
    'give_any_agent_direct_access_to_raw_card_details',
    'modify_this_policy_from_an_agent_workspace',
    'approve_own_work',
    'present_internal_artifact_creation_as_market_validation',
    'continue_internal_product_work_without_task_or_market_reason',
]

_EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


class MandateError(ValueError):
    pass


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'oui', 'on'}
    return default


def _eur(value: Any, default: int = 0) -> int:
    try:
        amount = int(value)
    except (TypeError, ValueError):
        amount = default
    return max(0, amount)


def empty_features() -> dict[str, bool]:
    return {key: False for key in FEATURE_KEYS}


def sandbox_answers() -> dict[str, Any]:
    """Neutral defaults. Caller must still set owner + email."""
    return {
        'policy_owner': '',
        'agent_name': 'Serge',
        'email': '',
        'public_role': 'assistant_operational',
        'autonomous': False,
        'mode': 'sandbox',
        'features': {
            **empty_features(),
            'public_web': True,
        },
        'financial': {
            'card_monthly_limit_eur': 0,
            'maximum_one_off_eur': 0,
            'maximum_new_recurring_subscription_eur': 0,
            'payment_execution_enabled': False,
        },
    }


def normalize_answers(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    base = sandbox_answers()
    incoming = dict(raw or {})
    features = {**base['features'], **dict(incoming.get('features') or {})}
    financial = {**base['financial'], **dict(incoming.get('financial') or {})}
    mode = str(incoming.get('mode') or base['mode']).strip().lower()
    if mode not in {'sandbox', 'staging', 'live'}:
        raise MandateError(f'invalid mode: {mode}')
    answers = {
        'policy_owner': str(incoming.get('policy_owner') or '').strip(),
        'agent_name': str(
            incoming.get('agent_name') or base['agent_name']
        ).strip()
        or 'Serge',
        'email': str(incoming.get('email') or '').strip(),
        'public_role': str(
            incoming.get('public_role') or base['public_role']
        ).strip()
        or 'assistant_operational',
        'autonomous': _bool(incoming.get('autonomous'), False),
        'mode': mode,
        'features': {
            key: _bool(features.get(key), False) for key in FEATURE_KEYS
        },
        'financial': {
            'card_monthly_limit_eur': _eur(
                financial.get('card_monthly_limit_eur')
            ),
            'maximum_one_off_eur': _eur(financial.get('maximum_one_off_eur')),
            'maximum_new_recurring_subscription_eur': _eur(
                financial.get('maximum_new_recurring_subscription_eur')
            ),
            'payment_execution_enabled': _bool(
                financial.get('payment_execution_enabled'), False
            ),
        },
    }
    if mode == 'sandbox':
        answers['autonomous'] = False
        answers['features']['payments_live'] = False
        answers['features']['deploy_production'] = False
        answers['features']['phone_voice'] = False
        answers['financial']['payment_execution_enabled'] = False
        answers['financial']['card_monthly_limit_eur'] = 0
        answers['financial']['maximum_one_off_eur'] = 0
        answers['financial']['maximum_new_recurring_subscription_eur'] = 0
    if answers['features']['payments_live']:
        answers['financial']['payment_execution_enabled'] = True
    return answers


def _actions(features: Mapping[str, bool]) -> list[str]:
    actions: list[str] = []
    if features['public_web']:
        actions.extend(
            ['browse_public_web', 'benchmark_business_opportunities']
        )
    if features['accounts']:
        actions.extend(
            [
                'create_free_service_accounts',
                'verify_accounts_by_email',
                'verify_accounts_by_sms',
                'create_public_non_sensitive_demo_assets',
            ]
        )
    if features['gmail']:
        actions.extend(
            [
                'contact_public_business_prospects_at_low_volume',
                'answer_business_messages_within_an_approved_task',
            ]
        )
    actions.append('modify_and_test_project_code_within_an_approved_task')
    if features['ingress']:
        actions.append('mutate_dns_within_approved_zones')
    if features['deploy_staging']:
        actions.append('deploy_staging_within_an_approved_task')
    if features['accounts'] or features['payments_live']:
        actions.append('purchase_domains_via_payment_broker')
        actions.append('bounded_payment_via_broker')
    if features['stripe']:
        actions.append('operate_stripe_sandbox_catalog')
    if features['payments_live']:
        actions.append('operate_stripe_live_receive')
    if features['phone_sms']:
        actions.append('receive_sms_otp_via_broker')
    if features['phone_voice']:
        actions.append('answer_inbound_voice_calls')
        actions.append('place_bounded_commercial_calls_via_voice_broker')
    return actions


def build_mandate(answers: Mapping[str, Any] | None = None) -> dict[str, Any]:
    cfg = normalize_answers(answers)
    if not cfg['policy_owner']:
        raise MandateError('policy_owner is required')
    if not _EMAIL.match(cfg['email']):
        raise MandateError('identity.email must be a real-looking address')
    features = cfg['features']
    finance = cfg['financial']
    return {
        'version': MANDATE_VERSION,
        'status': 'owner_authorized_v3'
        if cfg['mode'] == 'live'
        else 'sandbox_draft',
        'policy_owner': cfg['policy_owner'],
        'policy_path': '',
        'identity': {
            'agent_name': cfg['agent_name'],
            'email': cfg['email'],
            'phone': {
                'type': (
                    'dedicated'
                    if (features['accounts'] or features['phone_sms'])
                    else 'none'
                ),
                'access_method': (
                    'sms_tool'
                    if (features['accounts'] or features['phone_sms'])
                    else 'none'
                ),
                'sms_inbound_allowed': bool(features['phone_sms']),
                'sms_outbound_allowed': False,
                'voice_inbound_allowed': bool(features['phone_voice']),
                'voice_outbound_allowed': bool(features['phone_voice']),
            },
            'public_representation': {
                'role': cfg['public_role'],
                'require_honest_disclosure': True,
            },
        },
        'mission': {
            'primary_goal': (
                'Rechercher, tester, construire et exploiter des projets '
                'économiquement justifiables, dans les limites du présent mandat.'
            ),
            'operating_mode': {
                'autonomous': bool(cfg['autonomous']),
                'continuous_operation_allowed': bool(cfg['autonomous']),
                'prefer_market_evidence_over_internal_artifacts': True,
                'useful_result_required': True,
                'minimum_runtime_required': False,
            },
        },
        'governance': {
            'director': {
                'may_create_tasks': True,
                'may_allocate_work': True,
                'may_approve_strategy': True,
                'may_execute_worker_tasks': False,
                'may_review_own_work': False,
            },
            'venture_scout': {
                'may_browse_public_internet': features['public_web'],
                'may_benchmark_opportunities': features['public_web'],
                'may_submit_opportunities': True,
                'may_contact_external_parties': False,
                'may_purchase': False,
                'may_modify_products': False,
            },
            'sales': {
                'may_research_public_prospects': features['public_web'],
                'may_read_business_email': features['gmail'],
                'may_send_low_volume_business_email': features['gmail'],
                'may_answer_voice_calls': features['phone_voice'],
                'may_place_commercial_calls': features['phone_voice'],
                'may_update_prospect_events': True,
                'may_modify_products': False,
                'may_purchase': False,
            },
            'builder': {
                'may_modify_project_code': True,
                'may_run_tests': True,
                'may_prepare_staging_deployments': features['deploy_staging'],
                'may_send_email': False,
                'may_access_payment_data': False,
                'may_change_strategy': False,
            },
            'digital_operator': {
                'may_create_free_accounts': features['accounts'],
                'may_verify_accounts_by_email': features['accounts'],
                'may_verify_accounts_by_sms': features['accounts'],
                'may_receive_sms_otp': features['phone_sms'],
                'may_use_persistent_browser_profile': features['accounts'],
                'may_accept_standard_service_terms': features['accounts'],
                'may_purchase_via_payment_broker': bool(
                    features['payments_live'] or features['accounts']
                ),
                'may_mutate_dns': features['ingress'],
                'may_deploy_staging': features['deploy_staging'],
                'may_deploy_production': features['deploy_production'],
                'may_operate_stripe_sandbox': features['stripe'],
                'may_operate_stripe_live_receive': features['payments_live'],
                'may_read_raw_card_credentials': False,
            },
            'reviewer': {
                'read_only': True,
                'may_review_tasks': True,
                'may_return_pass_rework_or_block': True,
                'may_modify_reviewed_work': False,
                'may_approve_own_work': False,
            },
            'reducer': {
                'implementation': 'deterministic',
                'may_update_canonical_state': True,
                'may_make_business_decisions': False,
            },
        },
        'autonomous_actions': _actions(features),
        'financial_policy': {
            'card_monthly_limit_eur': finance['card_monthly_limit_eur'],
            'maximum_one_off_eur': finance['maximum_one_off_eur'],
            'maximum_new_recurring_subscription_eur': finance[
                'maximum_new_recurring_subscription_eur'
            ],
            'payment_execution_enabled': finance['payment_execution_enabled'],
            'refunds_enabled': False,
            'activation_requirement': 'deterministic_payment_broker',
            'raw_card_access_by_agents': 'forbidden',
            'recurring_subscriptions_require_tracking': True,
            'receipts_require_storage': True,
            'renewals_require_tracking': True,
        },
        'human_escalation_required': list(HUMAN_ESCALATION),
        'forbidden_actions': list(FORBIDDEN_ACTIONS),
        'state_rules': {
            'canonical_state_writer': 'deterministic_reducer',
            'workers_may_write_canonical_state': False,
            'reviewer_may_write_canonical_state': False,
            'accepted_event_required': True,
            'append_only_run_logs_are_not_canonical_state': True,
        },
        'review_rules': {
            'review_required_before_state_commit': True,
            'maximum_rework_cycles': 1,
            'second_failure_result': 'failed_or_human_block',
            'evidence_required': True,
        },
    }


def validate_mandate(mandate: Mapping[str, Any]) -> None:
    if not isinstance(mandate, dict):
        raise MandateError('mandate is not a mapping')
    if mandate.get('version') != MANDATE_VERSION:
        raise MandateError('mandate version must be 2')
    identity = mandate.get('identity') or {}
    email = identity.get('email')
    if not isinstance(email, str) or not _EMAIL.match(email.strip()):
        raise MandateError('identity.email missing or invalid')
    if not str(mandate.get('policy_owner') or '').strip():
        raise MandateError('policy_owner missing')
    governance = mandate.get('governance') or {}
    missing = [role for role in REQUIRED_ROLES if role not in governance]
    if missing:
        raise MandateError('governance missing roles: ' + ', '.join(missing))
    finance = mandate.get('financial_policy') or {}
    if finance.get('raw_card_access_by_agents') not in {
        None,
        'forbidden',
        False,
    }:
        raise MandateError('raw card access must stay forbidden')
    operator = governance.get('digital_operator') or {}
    if operator.get('may_read_raw_card_credentials') is True:
        raise MandateError(
            'digital_operator may not read raw card credentials'
        )
    if not isinstance(mandate.get('autonomous_actions'), list):
        raise MandateError('autonomous_actions must be a list')


def render_yaml(mandate: Mapping[str, Any]) -> str:
    validate_mandate(mandate)
    text = yaml.safe_dump(
        dict(mandate),
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    if not text.endswith('\n'):
        text += '\n'
    return text
