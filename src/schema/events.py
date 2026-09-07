"""
src/schema/events.py
Observability audit event data structures.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone


class AuditEvent(BaseModel):
    event_id: str
    session_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_type: str  # DISCOVERY_START, STEP_ATTEMPT, LOCATOR_FALLBACK, CHECKPOINT_EVAL, HITL_REQUEST, REPLAY_COMPLETE
    level: str = "INFO"
    capability_id: Optional[str] = None
    step_id: Optional[str] = None
    message: str
    payload: Dict[str, Any] = Field(default_factory=dict)
