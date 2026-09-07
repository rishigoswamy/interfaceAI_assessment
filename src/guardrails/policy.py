"""
src/guardrails/policy.py
Safety policies, domain allowlisting, and action risk classification.
"""

from enum import Enum
from typing import List, Optional, Set
from urllib.parse import urlparse
from pydantic import BaseModel, Field

from src.schema.artifact import ActionType, RiskLevel


class PolicyViolationError(Exception):
    """Raised when an automation action or target URL violates safety guardrails."""
    def __init__(self, message: str, rule: str, details: Optional[dict] = None):
        super().__init__(message)
        self.rule = rule
        self.details = details or {}


class SafetyPolicy(BaseModel):
    """Enforces strict domain allowlists, action limits, and risk governance."""
    allowed_domains: List[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1", "0.0.0.0"])
    allowed_action_types: List[ActionType] = Field(
        default_factory=lambda: [
            ActionType.NAVIGATE,
            ActionType.CLICK,
            ActionType.TYPE,
            ActionType.SELECT,
            ActionType.WAIT_FOR,
            ActionType.ASSERT,
            ActionType.EXTRACT,
            ActionType.PRESS_KEY,
            ActionType.SOLVE_SECURITY_OVERRIDE
        ]
    )
    max_steps_per_run: int = 50
    block_irreversible_actions: bool = False
    require_confirmation_for_risky: bool = True
    blocked_url_patterns: List[str] = Field(
        default_factory=lambda: ["admin/purge", "delete-all", "danger-zone", "format-system"]
    )

    def validate_url(self, url: str) -> bool:
        """Validates that a URL's hostname is in the allowed domain whitelist."""
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ""
            port = parsed.port
            # Match localhost variants
            if hostname in self.allowed_domains:
                return True
            for domain in self.allowed_domains:
                if domain in hostname:
                    return True
            raise PolicyViolationError(
                message=f"Access to domain '{hostname}' is not permitted by policy allowlist.",
                rule="DOMAIN_ALLOWLIST",
                details={"url": url, "allowed_domains": self.allowed_domains}
            )
        except Exception as e:
            if isinstance(e, PolicyViolationError):
                raise
            raise PolicyViolationError(
                message=f"Malformed URL: {url}",
                rule="URL_PARSE_ERROR",
                details={"error": str(e)}
            )

    def validate_action(self, action_type: ActionType, risk_level: RiskLevel = RiskLevel.SAFE_READ) -> bool:
        """Checks whether the given action type and risk level are permitted."""
        if action_type not in self.allowed_action_types:
            raise PolicyViolationError(
                message=f"Action type '{action_type}' is forbidden by execution policy.",
                rule="ACTION_TYPE_RESTRICTION",
                details={"action_type": action_type}
            )

        if risk_level == RiskLevel.IRREVERSIBLE and self.block_irreversible_actions:
            raise PolicyViolationError(
                message="Irreversible action blocked by strict zero-trust policy.",
                rule="IRREVERSIBLE_ACTION_BLOCKED",
                details={"risk_level": risk_level}
            )

        return True
