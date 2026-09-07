"""
src/schema/artifact.py
Typed definitions for the Capability Artifact contract.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class ActionType(str, Enum):
    NAVIGATE = "NAVIGATE"
    CLICK = "CLICK"
    TYPE = "TYPE"
    SELECT = "SELECT"
    WAIT_FOR = "WAIT_FOR"
    ASSERT = "ASSERT"
    EXTRACT = "EXTRACT"
    PRESS_KEY = "PRESS_KEY"
    SOLVE_SECURITY_OVERRIDE = "SOLVE_SECURITY_OVERRIDE"


class LocatorStrategy(str, Enum):
    ROLE_NAME = "ROLE_NAME"      # Accessibility tree: role="button", name="Search"
    TEXT_ANCHOR = "TEXT_ANCHOR"  # Visible text content: text="Account Summary"
    CSS = "CSS"                  # CSS selector: #search-input, .btn-primary
    XPATH = "XPATH"              # XPath selector: //table[@id='ledger']//tr[1]
    COORDINATES = "COORDINATES"  # Fallback coordinates: {"x": 120, "y": 340}


class TargetLocator(BaseModel):
    """Multi-tier locator definition prioritizing semantic / accessibility locators over fragile DOM selectors."""
    strategy: LocatorStrategy
    value: str
    description: Optional[str] = None
    role: Optional[str] = None
    name: Optional[str] = None
    frame_selector: Optional[str] = None  # In case element is inside an iframe
    coordinates: Optional[Dict[str, int]] = None  # e.g. {"x": 100, "y": 200}
    is_fuzzy: bool = False


class ParameterType(str, Enum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ENUM = "enum"


class ParameterSchema(BaseModel):
    """Schema definition for a capability input parameter."""
    name: str
    type: ParameterType = ParameterType.STRING
    description: str
    required: bool = True
    default: Optional[Any] = None
    allowed_values: Optional[List[str]] = None
    validation_regex: Optional[str] = None
    sensitive: bool = False  # If true, redact from logs and artifacts


class OutputSchema(BaseModel):
    """Schema definition for a capability output extraction."""
    name: str
    type: ParameterType = ParameterType.STRING
    description: str
    extractor_strategy: LocatorStrategy = LocatorStrategy.CSS
    selector: str
    attribute: Optional[str] = None  # None means innerText
    regex_pattern: Optional[str] = None  # Optional regex to extract portion of text
    frame_selector: Optional[str] = None


class CheckpointAssertion(str, Enum):
    URL_CONTAINS = "URL_CONTAINS"
    ELEMENT_VISIBLE = "ELEMENT_VISIBLE"
    TEXT_PRESENT = "TEXT_PRESENT"
    ELEMENT_VALUE_EQUALS = "ELEMENT_VALUE_EQUALS"


class CheckpointRule(BaseModel):
    """State assertion to verify transition success before proceeding to next action."""
    assertion: CheckpointAssertion
    target: str  # URL snippet, selector, or expected text
    expected_value: Optional[str] = None
    timeout_ms: int = 5000
    description: Optional[str] = None


class BusinessOutcomeBranch(BaseModel):
    """Defines an expected business outcome detection (e.g. Member Not Found, Insufficient Funds)."""
    outcome_code: str
    description: str
    condition_type: CheckpointAssertion = CheckpointAssertion.TEXT_PRESENT
    target: str
    expected_text: Optional[str] = None
    output_payload: Optional[Dict[str, Any]] = None


class RecoveryRule(BaseModel):
    """Defines automated handling for known transient states (e.g. dismiss interstitial popup, retry on loading spinner)."""
    trigger_selector: str
    trigger_text: Optional[str] = None
    resolution_action: ActionType = ActionType.CLICK
    resolution_target: Optional[str] = None
    max_retries: int = 2
    description: Optional[str] = None


class RiskLevel(str, Enum):
    SAFE_READ = "SAFE_READ"                  # Idempotent read-only (balance check, search)
    REVERSIBLE_WRITE = "REVERSIBLE_WRITE"    # Modifiable/reversible (draft form, update note)
    IRREVERSIBLE = "IRREVERSIBLE"            # Risky/permanent (funds transfer, account closure, lock override)


class ActionStep(BaseModel):
    """Single discrete step in the deterministic automation flow."""
    step_id: str
    name: str
    action_type: ActionType
    locators: List[TargetLocator] = Field(default_factory=list)
    value_template: Optional[str] = None  # Jinja-style parameter template: "{{member_id}}"
    checkpoint: Optional[CheckpointRule] = None
    business_outcomes: List[BusinessOutcomeBranch] = Field(default_factory=list)
    recovery_rules: List[RecoveryRule] = Field(default_factory=list)
    requires_confirmation: bool = False
    timeout_ms: int = 8000
    optional: bool = False


class CapabilityMetadata(BaseModel):
    id: str
    name: str
    version: str = "1.0.0"
    app_name: str = "OmniCore Banking"
    tenant_id: Optional[str] = "default"
    description: str
    author: str = "computer-use-agent"
    created_at: str
    risk_level: RiskLevel = RiskLevel.SAFE_READ
    tags: List[str] = Field(default_factory=list)


class CapabilityArtifact(BaseModel):
    """The complete, typed, agent-invocable capability specification."""
    metadata: CapabilityMetadata
    entry_point_url: str
    inputs: List[ParameterSchema] = Field(default_factory=list)
    outputs: List[OutputSchema] = Field(default_factory=list)
    steps: List[ActionStep] = Field(default_factory=list)
    global_recovery_rules: List[RecoveryRule] = Field(default_factory=list)
    allowed_domains: List[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])
