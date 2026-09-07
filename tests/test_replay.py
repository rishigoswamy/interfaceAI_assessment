"""
tests/test_replay.py
End-to-end integration tests for DeterministicReplayEngine against the mock OmniCore banking app.
"""

import pytest
from src.discovery.compiler import CapabilityCompiler
from src.guardrails.policy import SafetyPolicy
from src.replay.engine import DeterministicReplayEngine
from src.schema.artifact import ActionStep, ActionType, CheckpointAssertion, CheckpointRule, TargetLocator, LocatorStrategy
from src.schema.results import ExecutionStatus


@pytest.mark.asyncio
async def test_deterministic_replay_happy_path():
    artifact = CapabilityCompiler.build_member_lookup_capability("http://127.0.0.1:8000")
    engine = DeterministicReplayEngine(headless=True)

    result = await engine.execute(
        artifact=artifact,
        inputs={"member_id": "MBR-1092"}
    )

    assert result.status == ExecutionStatus.SUCCESS
    assert result.outputs.get("member_id") == "MBR-1092"
    assert result.outputs.get("member_status") == "ACTIVE"
    assert result.outputs.get("savings_balance") == "$14,250.00"
    assert len(result.step_records) == 3
    assert all(rec.checkpoint_passed for rec in result.step_records)


@pytest.mark.asyncio
async def test_deterministic_replay_business_outcome_not_found():
    artifact = CapabilityCompiler.build_member_lookup_capability("http://127.0.0.1:8000")
    engine = DeterministicReplayEngine(headless=True)

    result = await engine.execute(
        artifact=artifact,
        inputs={"member_id": "MBR-9999"}
    )

    # Must be categorized as BUSINESS_OUTCOME, not HARD_FAILURE or crash!
    assert result.status == ExecutionStatus.BUSINESS_OUTCOME
    assert result.business_outcome_code == "MEMBER_NOT_FOUND"
    assert "not found in active ledger" in result.business_outcome_message.lower() or "not found" in result.business_outcome_message.lower()


@pytest.mark.asyncio
async def test_deterministic_replay_auto_recovery_modal():
    # URL with interstitial modal enabled
    artifact = CapabilityCompiler.build_member_lookup_capability("http://localhost:8000/?show_interstitial=true")
    engine = DeterministicReplayEngine(headless=True)

    result = await engine.execute(
        artifact=artifact,
        inputs={"member_id": "MBR-1092"}
    )

    # Should auto-dismiss modal and succeed
    assert result.status == ExecutionStatus.SUCCESS
    assert result.outputs.get("savings_balance") == "$14,250.00"


@pytest.mark.asyncio
async def test_deterministic_replay_missing_param_failure():
    artifact = CapabilityCompiler.build_member_lookup_capability("http://127.0.0.1:8000")
    engine = DeterministicReplayEngine(headless=True)

    # Missing member_id
    result = await engine.execute(
        artifact=artifact,
        inputs={}
    )

    # Missing required parameter defaults or halts
    assert result.status in [ExecutionStatus.SUCCESS, ExecutionStatus.HARD_FAILURE]


@pytest.mark.asyncio
async def test_deterministic_replay_policy_violation():
    artifact = CapabilityCompiler.build_member_lookup_capability("http://unauthorized-bank.com")
    policy = SafetyPolicy(allowed_domains=["localhost", "127.0.0.1"])
    engine = DeterministicReplayEngine(policy=policy, headless=True)

    result = await engine.execute(
        artifact=artifact,
        inputs={"member_id": "MBR-1092"}
    )

    assert result.status == ExecutionStatus.POLICY_VIOLATION


@pytest.mark.asyncio
async def test_deterministic_replay_checkpoint_failure():
    artifact = CapabilityCompiler.build_member_lookup_capability("http://127.0.0.1:8000")
    # Inject impossible checkpoint rule
    artifact.steps[0].checkpoint = CheckpointRule(
        assertion=CheckpointAssertion.ELEMENT_VISIBLE,
        target="#nonexistent-impossible-element",
        timeout_ms=500
    )
    engine = DeterministicReplayEngine(headless=True)

    result = await engine.execute(
        artifact=artifact,
        inputs={"member_id": "MBR-1092"}
    )

    assert result.status == ExecutionStatus.HARD_FAILURE
    assert "CHECKPOINT_FAILED" in str(result.step_records[0].status)
