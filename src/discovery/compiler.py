"""
src/discovery/compiler.py
Compiles observed execution trajectories and DOM metadata into a strongly-typed CapabilityArtifact.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from src.schema.artifact import (
    ActionStep,
    ActionType,
    BusinessOutcomeBranch,
    CapabilityArtifact,
    CapabilityMetadata,
    CheckpointAssertion,
    CheckpointRule,
    LocatorStrategy,
    OutputSchema,
    ParameterSchema,
    ParameterType,
    RecoveryRule,
    RiskLevel,
    TargetLocator,
)


class CapabilityCompiler:
    """Transforms discovered interaction traces into parameterized CapabilityArtifact instances."""

    @staticmethod
    def build_member_lookup_capability(entry_url: str = "http://localhost:8000") -> CapabilityArtifact:
        """Constructs a fully robust Member Lookup capability artifact."""
        metadata = CapabilityMetadata(
            id="cap_member_lookup_v1",
            name="Member Profile and Balance Lookup",
            version="1.0.0",
            app_name="OmniCore Banking",
            description="Searches member by ID, inspects account ledger, and retrieves current savings balance.",
            created_at=datetime.now(timezone.utc).isoformat(),
            risk_level=RiskLevel.SAFE_READ,
            tags=["member-services", "balance-inquiry", "ledger-read"]
        )

        inputs = [
            ParameterSchema(
                name="member_id",
                type=ParameterType.STRING,
                description="Unique identifier of the credit union member (e.g. MBR-1092).",
                required=True,
                default="MBR-1092",
                validation_regex=r"^MBR-[0-9A-Za-z_-]+$"
            )
        ]

        outputs = [
            OutputSchema(
                name="member_id",
                type=ParameterType.STRING,
                description="Verified member ID from active profile.",
                selector="#display-member-id"
            ),
            OutputSchema(
                name="member_status",
                type=ParameterType.STRING,
                description="Current status of the member record.",
                selector="#display-member-status"
            ),
            OutputSchema(
                name="savings_balance",
                type=ParameterType.STRING,
                description="Current balance of the Primary High-Yield Savings Account.",
                selector="#account-ledger-table tbody tr:last-child .account-balance-cell"
            )
        ]

        steps = [
            ActionStep(
                step_id="step_1_nav_lookup_tab",
                name="Switch to Member Inquiry Tab",
                action_type=ActionType.CLICK,
                locators=[
                    TargetLocator(
                        strategy=LocatorStrategy.ROLE_NAME,
                        value="Member Inquiry & Ledger",
                        role="tab",
                        name="Member Inquiry & Ledger"
                    ),
                    TargetLocator(
                        strategy=LocatorStrategy.TEXT_ANCHOR,
                        value="Member Inquiry & Ledger"
                    ),
                    TargetLocator(
                        strategy=LocatorStrategy.CSS,
                        value="#tab-member-lookup"
                    )
                ],
                checkpoint=CheckpointRule(
                    assertion=CheckpointAssertion.ELEMENT_VISIBLE,
                    target="#section-lookup",
                    description="Inquiry panel must become visible"
                )
            ),
            ActionStep(
                step_id="step_2_enter_member_id",
                name="Enter Member ID into Search Field",
                action_type=ActionType.TYPE,
                locators=[
                    TargetLocator(
                        strategy=LocatorStrategy.CSS,
                        value="#member-id-input",
                        description="Direct ID selector"
                    ),
                    TargetLocator(
                        strategy=LocatorStrategy.XPATH,
                        value="//input[@name='memberQuery']",
                        description="Semantic name fallback"
                    ),
                    TargetLocator(
                        strategy=LocatorStrategy.COORDINATES,
                        value="coordinates_fallback",
                        coordinates={"x": 300, "y": 210}
                    )
                ],
                value_template="{{inputs.member_id}}"
            ),
            ActionStep(
                step_id="step_3_click_search",
                name="Execute Member Search",
                action_type=ActionType.CLICK,
                locators=[
                    TargetLocator(
                        strategy=LocatorStrategy.ROLE_NAME,
                        value="Search Records",
                        role="button",
                        name="Search Records"
                    ),
                    TargetLocator(
                        strategy=LocatorStrategy.TEXT_ANCHOR,
                        value="Search Records"
                    ),
                    TargetLocator(
                        strategy=LocatorStrategy.CSS,
                        value="#btn-search-member"
                    ),
                    TargetLocator(
                        strategy=LocatorStrategy.XPATH,
                        value="//button[@type='submit']"
                    )
                ],
                checkpoint=CheckpointRule(
                    assertion=CheckpointAssertion.ELEMENT_VISIBLE,
                    target="#member-profile-card, #search-status-alert, #security-challenge-box",
                    description="Result card or status banner must appear",
                    timeout_ms=5000
                ),
                business_outcomes=[
                    BusinessOutcomeBranch(
                        outcome_code="MEMBER_NOT_FOUND",
                        description="The requested member record was not found in the active core banking ledger.",
                        condition_type=CheckpointAssertion.TEXT_PRESENT,
                        target="#search-status-alert",
                        expected_text="not found in active ledger",
                        output_payload={"found": False}
                    )
                ]
            )
        ]

        global_recovery_rules = [
            RecoveryRule(
                trigger_selector="#compliance-modal",
                trigger_text="Daily Security & Policy Notice",
                resolution_action=ActionType.CLICK,
                resolution_target="#btn-acknowledge-notice",
                description="Auto-dismiss daily compliance notice interstitial"
            )
        ]

        return CapabilityArtifact(
            metadata=metadata,
            entry_point_url=entry_url,
            inputs=inputs,
            outputs=outputs,
            steps=steps,
            global_recovery_rules=global_recovery_rules,
            allowed_domains=["localhost", "127.0.0.1", "0.0.0.0"]
        )
