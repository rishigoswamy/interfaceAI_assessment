"""
src/schema/results.py
Execution result contracts distinguishing Success, Business Outcome, Recoverable Retries, and Hard Failures.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    BUSINESS_OUTCOME = "BUSINESS_OUTCOME"
    RECOVERED = "RECOVERED"
    ESCALATED_HITL = "ESCALATED_HITL"
    HARD_FAILURE = "HARD_FAILURE"
    POLICY_VIOLATION = "POLICY_VIOLATION"


class StepExecutionRecord(BaseModel):
    step_id: str
    step_name: str
    action_type: str
    strategy_used: Optional[str] = None
    target_resolved: Optional[str] = None
    duration_ms: float
    status: str
    error_message: Optional[str] = None
    checkpoint_passed: bool = True
    screenshot_path: Optional[str] = None


class ExecutionResult(BaseModel):
    """The formal contract returned to the calling AI agent or system."""
    status: ExecutionStatus
    capability_id: str
    session_id: str
    duration_total_ms: float
    outputs: Dict[str, Any] = Field(default_factory=dict)
    business_outcome_code: Optional[str] = None
    business_outcome_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    step_records: List[StepExecutionRecord] = Field(default_factory=list)
    hitl_intervention_needed: bool = False
    hitl_context: Optional[Dict[str, Any]] = None
