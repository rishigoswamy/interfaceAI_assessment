"""
tests/test_discovery.py
Unit and integration tests for DiscoveryAgent and Prompts.
"""

import pytest
from src.discovery.agent import DiscoveryAgent
from src.discovery.prompts import DISCOVERY_SYSTEM_PROMPT
from src.guardrails.policy import SafetyPolicy
from src.observability.logger import ExecutionLogger


def test_discovery_prompts_content():
    assert "Computer-Use Discovery Agent" in DISCOVERY_SYSTEM_PROMPT
    assert "Observe" in DISCOVERY_SYSTEM_PROMPT or "observe" in DISCOVERY_SYSTEM_PROMPT.lower()


@pytest.mark.asyncio
async def test_discovery_agent_live_execution():
    logger = ExecutionLogger(session_id="test_discovery_live")
    policy = SafetyPolicy()
    agent = DiscoveryAgent(policy=policy, logger=logger, headless=True)

    artifact = await agent.discover(
        goal="Look up member MBR-1092 and read their current savings balance",
        entry_point_url="http://127.0.0.1:8000",
        output_file="evidence/test_discovered_artifact.json"
    )

    assert artifact.metadata.id == "cap_member_lookup_v1"
    assert len(artifact.steps) == 3
    assert artifact.inputs[0].name == "member_id"
