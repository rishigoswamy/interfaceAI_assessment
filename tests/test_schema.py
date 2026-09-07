"""
tests/test_schema.py
Unit tests for CapabilityArtifact schemas and validation rules.
"""

import pytest
from pydantic import ValidationError

from src.discovery.compiler import CapabilityCompiler
from src.schema.artifact import (
    ActionStep,
    ActionType,
    CapabilityArtifact,
    CapabilityMetadata,
    CheckpointAssertion,
    CheckpointRule,
    LocatorStrategy,
    ParameterSchema,
    ParameterType,
    RiskLevel,
    TargetLocator,
)


def test_valid_capability_artifact_serialization():
    artifact = CapabilityCompiler.build_member_lookup_capability("http://localhost:8000")
    json_str = artifact.model_dump_json()
    assert "cap_member_lookup_v1" in json_str
    assert "High-Yield Savings" in json_str or "savings_balance" in json_str

    # Test round-trip deserialization
    deserialized = CapabilityArtifact.model_validate_json(json_str)
    assert deserialized.metadata.id == "cap_member_lookup_v1"
    assert len(deserialized.steps) == 3
    assert deserialized.inputs[0].name == "member_id"


def test_schema_validation_rejection():
    # Empty metadata should fail validation
    with pytest.raises(ValidationError):
        CapabilityArtifact.model_validate({"metadata": {}})


def test_action_step_locator_strategies():
    step = ActionStep(
        step_id="step_test",
        name="Test Click",
        action_type=ActionType.CLICK,
        locators=[
            TargetLocator(strategy=LocatorStrategy.ROLE_NAME, value="Submit", role="button"),
            TargetLocator(strategy=LocatorStrategy.CSS, value="#submit-btn"),
            TargetLocator(strategy=LocatorStrategy.COORDINATES, value="coords", coordinates={"x": 50, "y": 50})
        ],
        checkpoint=CheckpointRule(assertion=CheckpointAssertion.URL_CONTAINS, target="/dashboard")
    )
    assert len(step.locators) == 3
    assert step.checkpoint.assertion == CheckpointAssertion.URL_CONTAINS
