"""
src/observability/logger.py
Structured execution logger emitting timestamped JSON events and diagnostic snapshots.
"""

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from src.guardrails.redaction import DataRedactor
from src.schema.events import AuditEvent


class ExecutionLogger:
    """Structured JSON audit logger with sensitive data redaction and snapshot storage."""

    def __init__(self, session_id: str, log_dir: str = "evidence/logs"):
        self.session_id = session_id
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, f"session_{session_id}.jsonl")
        self.events = []

    def log(
        self,
        event_type: str,
        message: str,
        level: str = "INFO",
        capability_id: Optional[str] = None,
        step_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=f"evt_{int(time.time()*1000)}_{len(self.events)}",
            session_id=self.session_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            level=level,
            capability_id=capability_id,
            step_id=step_id,
            message=DataRedactor.redact_text(message),
            payload=DataRedactor.redact_data(payload or {})
        )
        self.events.append(event)

        # Append to log file
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")

        return event

    def save_snapshot(self, name: str, content: str, extension: str = "txt") -> str:
        """Saves a diagnostic DOM or text snapshot."""
        filename = f"{self.session_id}_{name}.{extension}"
        filepath = os.path.join(self.log_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(DataRedactor.redact_text(content))
        return filepath
