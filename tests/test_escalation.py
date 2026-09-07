"""
tests/test_escalation.py
Integration tests for Human-in-the-Loop (HITL) escalation and live session control transfer.
"""

import pytest
import threading
import time
from bank_app.server import run_server
from src.discovery.compiler import CapabilityCompiler
from src.escalation.handoff import HITLManager
from src.observability.logger import ExecutionLogger
from src.replay.engine import DeterministicReplayEngine
from src.schema.results import ExecutionStatus


@pytest.mark.asyncio
async def test_hitl_escalation_and_resume():
    artifact = CapabilityCompiler.build_member_lookup_capability("http://127.0.0.1:8000")
    logger = ExecutionLogger(session_id="test_hitl")
    hitl_mgr = HITLManager(logger=logger, interactive=False)
    engine = DeterministicReplayEngine(logger=logger, hitl_manager=hitl_mgr, headless=True)

    # Replay on security-locked member MBR-LOCKED with mock operator unlock token
    result = await engine.execute(
        artifact=artifact,
        inputs={"member_id": "MBR-LOCKED"},
        mock_operator_action="auto_unlock_pin"
    )

    # After human intervention, session is unlocked and ledger is read
    assert result.status == ExecutionStatus.SUCCESS
    assert result.outputs.get("member_id") == "MBR-LOCKED"
    assert result.outputs.get("member_status") == "ACTIVE (OVERRIDDEN)"
    assert "$52,000.00" in str(result.outputs.get("savings_balance"))
