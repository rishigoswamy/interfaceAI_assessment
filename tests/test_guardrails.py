"""
tests/test_guardrails.py
Unit tests for Safety Policies, Allowlisting, and PII Redaction.
"""

import pytest
from src.guardrails.policy import SafetyPolicy, PolicyViolationError
from src.guardrails.redaction import DataRedactor
from src.schema.artifact import ActionType, RiskLevel


def test_domain_allowlist_enforcement():
    policy = SafetyPolicy(allowed_domains=["localhost", "127.0.0.1", "secure.internalbank.com"])

    # Permitted URLs
    assert policy.validate_url("http://localhost:8000/inquiry") is True
    assert policy.validate_url("https://secure.internalbank.com/console") is True

    # Blocked external domains
    with pytest.raises(PolicyViolationError) as exc_info:
        policy.validate_url("https://malicious-external-site.com/steal-data")
    assert exc_info.value.rule == "DOMAIN_ALLOWLIST"


def test_action_risk_enforcement():
    policy = SafetyPolicy(block_irreversible_actions=True)

    # Safe read allowed
    assert policy.validate_action(ActionType.CLICK, RiskLevel.SAFE_READ) is True

    # Blocked irreversible action
    with pytest.raises(PolicyViolationError) as exc_info:
        policy.validate_action(ActionType.CLICK, RiskLevel.IRREVERSIBLE)
    assert exc_info.value.rule == "IRREVERSIBLE_ACTION_BLOCKED"


def test_pii_and_token_redaction():
    raw_text = "Member John Doe with SSN 123-45-6789 and Bearer secret_token_xyz987 logged in."
    redacted = DataRedactor.redact_text(raw_text)
    assert "123-45-6789" not in redacted
    assert "[REDACTED_SSN]" in redacted
    assert "[REDACTED_TOKEN]" in redacted

    raw_dict = {
        "user": "Alice",
        "ssn": "987-65-4321",
        "nested": {
            "password": "SuperSecretPassword123!",
            "credit_card": "4532015012345678"
        }
    }
    cleaned = DataRedactor.redact_data(raw_dict)
    assert cleaned["ssn"] == "[REDACTED_SECRET]"
    assert cleaned["nested"]["password"] == "[REDACTED_SECRET]"
    assert "4532015012345678" not in str(cleaned)
