"""
src/replay/engine.py
Deterministic Replay Engine.
Executes capability artifacts reliably without an LLM in the loop.
Implements robust locator resolution, checkpoint validation, 3-tier error classification,
auto-recovery from transient states, and live session human escalation.
"""

import os
import re
import time
import uuid
from typing import Any, Dict, Optional
from playwright.async_api import Page, async_playwright

from src.guardrails.policy import SafetyPolicy, PolicyViolationError
from src.observability.logger import ExecutionLogger
from src.escalation.handoff import HITLManager
from src.replay.locator import LocatorResolver
from src.schema.artifact import (
    ActionStep,
    ActionType,
    CapabilityArtifact,
    CheckpointAssertion,
    CheckpointRule,
    LocatorStrategy,
    RecoveryRule,
    RiskLevel,
)
from src.schema.results import ExecutionResult, ExecutionStatus, StepExecutionRecord


class DeterministicReplayEngine:
    """Executes a CapabilityArtifact deterministically given a set of input parameters."""

    def __init__(
        self,
        policy: Optional[SafetyPolicy] = None,
        logger: Optional[ExecutionLogger] = None,
        hitl_manager: Optional[HITLManager] = None,
        headless: bool = True
    ):
        self.policy = policy or SafetyPolicy()
        self.logger = logger
        self.hitl_manager = hitl_manager or HITLManager(logger=self.logger, interactive=True)
        self.headless = headless

    def _interpolate_template(self, template: Optional[str], params: Dict[str, Any]) -> str:
        """Substitutes {{variable}} placeholders with parameter values."""
        if not template:
            return ""
        result = template
        for key, val in params.items():
            result = result.replace(f"{{{{{key}}}}}", str(val))
            result = result.replace(f"{{{{inputs.{key}}}}}", str(val))
        return result

    async def _handle_recovery_rules(self, page: Page, rules: list[RecoveryRule]) -> bool:
        """Checks for and handles transient popups, modals, or banners."""
        for rule in rules:
            try:
                trigger = page.locator(rule.trigger_selector)
                if await trigger.count() > 0 and await trigger.first.is_visible():
                    if rule.trigger_text:
                        text = await trigger.first.inner_text()
                        if rule.trigger_text not in text:
                            continue

                    if self.logger:
                        self.logger.log(
                            event_type="AUTO_RECOVERY_TRIGGERED",
                            message=f"Transient condition detected: {rule.description or rule.trigger_selector}. Executing resolution.",
                            level="INFO"
                        )

                    target_loc = rule.resolution_target or rule.trigger_selector
                    if rule.resolution_action == ActionType.CLICK:
                        await page.click(target_loc)
                        await page.wait_for_timeout(500)
                        return True
            except Exception:
                continue
        return False

    async def _evaluate_checkpoint(self, page: Page, checkpoint: CheckpointRule) -> bool:
        """Evaluates a state assertion checkpoint."""
        try:
            if checkpoint.assertion == CheckpointAssertion.URL_CONTAINS:
                return checkpoint.target in page.url
            elif checkpoint.assertion == CheckpointAssertion.ELEMENT_VISIBLE:
                selectors = [s.strip() for s in checkpoint.target.split(",")]
                for sel in selectors:
                    el = page.locator(sel)
                    if await el.count() > 0 and await el.first.is_visible():
                        return True
                return False
            elif checkpoint.assertion == CheckpointAssertion.TEXT_PRESENT:
                body_text = await page.locator("body").inner_text()
                return checkpoint.target.lower() in body_text.lower()
            elif checkpoint.assertion == CheckpointAssertion.ELEMENT_VALUE_EQUALS:
                el = page.locator(checkpoint.target)
                if await el.count() > 0:
                    val = await el.first.input_value()
                    return val == checkpoint.expected_value
        except Exception:
            return False
        return False

    async def execute(
        self,
        artifact: CapabilityArtifact,
        inputs: Dict[str, Any],
        page: Optional[Page] = None,
        mock_operator_action: Optional[str] = None
    ) -> ExecutionResult:
        """Runs the deterministic replay of the capability artifact."""
        session_id = f"replay_{uuid.uuid4().hex[:8]}"
        start_time = time.time()

        if not self.logger:
            self.logger = ExecutionLogger(session_id=session_id)
        if not self.hitl_manager.logger:
            self.hitl_manager.logger = self.logger

        self.logger.log(
            event_type="REPLAY_START",
            message=f"Starting deterministic replay for capability '{artifact.metadata.name}' ({artifact.metadata.id})",
            capability_id=artifact.metadata.id,
            payload={"inputs": inputs, "version": artifact.metadata.version}
        )

        # 1. Validate inputs schema
        for param in artifact.inputs:
            if param.required and param.name not in inputs:
                if param.default is not None:
                    inputs[param.name] = param.default
                else:
                    err_msg = f"Missing required parameter: '{param.name}'"
                    self.logger.log("INPUT_VALIDATION_ERROR", err_msg, level="ERROR", capability_id=artifact.metadata.id)
                    return ExecutionResult(
                        status=ExecutionStatus.HARD_FAILURE,
                        capability_id=artifact.metadata.id,
                        session_id=session_id,
                        duration_total_ms=(time.time() - start_time) * 1000,
                        error_details={"error": err_msg}
                    )

        # 2. Validate URL security allowlist
        try:
            self.policy.validate_url(artifact.entry_point_url)
        except PolicyViolationError as pve:
            self.logger.log("POLICY_VIOLATION", str(pve), level="ERROR", capability_id=artifact.metadata.id)
            return ExecutionResult(
                status=ExecutionStatus.POLICY_VIOLATION,
                capability_id=artifact.metadata.id,
                session_id=session_id,
                duration_total_ms=(time.time() - start_time) * 1000,
                error_details={"error": str(pve), "rule": pve.rule}
            )

        step_records = []
        should_close_browser = False
        playwright_instance = None
        browser_instance = None

        try:
            if page is None:
                playwright_instance = await async_playwright().start()
                browser_instance = await playwright_instance.chromium.launch(headless=self.headless)
                page = await browser_instance.new_page()
                should_close_browser = True

            # Navigate to Entry Point
            await page.goto(artifact.entry_point_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(500)

            # Process Global Recovery (e.g. dismiss initial popups)
            await self._handle_recovery_rules(page, artifact.global_recovery_rules)

            # 3. Step execution loop
            for step in artifact.steps:
                step_start = time.time()
                self.logger.log(
                    event_type="STEP_ATTEMPT",
                    message=f"Executing Step: {step.name} ({step.step_id})",
                    capability_id=artifact.metadata.id,
                    step_id=step.step_id,
                    payload={"action_type": step.action_type}
                )

                # Validate action policy
                self.policy.validate_action(step.action_type, artifact.metadata.risk_level)

                # Step recovery rules
                if step.recovery_rules:
                    await self._handle_recovery_rules(page, step.recovery_rules)

                interpolated_value = self._interpolate_template(step.value_template, inputs)
                resolved_strategy = None
                target_resolved = None
                status = "SUCCESS"
                error_msg = None

                # Execute action based on type
                if step.action_type == ActionType.NAVIGATE:
                    target_url = interpolated_value or artifact.entry_point_url
                    self.policy.validate_url(target_url)
                    await page.goto(target_url, wait_until="domcontentloaded")
                    target_resolved = target_url

                elif step.action_type == ActionType.WAIT_FOR:
                    wait_ms = int(interpolated_value) if interpolated_value.isdigit() else 1000
                    await page.wait_for_timeout(wait_ms)

                elif step.action_type in [ActionType.CLICK, ActionType.TYPE, ActionType.SELECT]:
                    element, matching_loc, strategy_name = await LocatorResolver.resolve_element(
                        page, step.locators, timeout_ms=step.timeout_ms
                    )

                    if not element and matching_loc and matching_loc.strategy == LocatorStrategy.COORDINATES:
                        coords = matching_loc.coordinates or {"x": 0, "y": 0}
                        await page.mouse.click(coords["x"], coords["y"])
                        resolved_strategy = "COORDINATES"
                        target_resolved = f"({coords['x']}, {coords['y']})"
                    elif element:
                        resolved_strategy = strategy_name
                        target_resolved = matching_loc.value if matching_loc else "resolved_element"

                        if step.action_type == ActionType.CLICK:
                            await element.click()
                        elif step.action_type == ActionType.TYPE:
                            await element.fill(interpolated_value)
                        elif step.action_type == ActionType.SELECT:
                            await element.select_option(interpolated_value)
                    else:
                        # Element resolution failed
                        status = "LOCATOR_FAILED"
                        error_msg = f"Failed to locate element for step '{step.name}' using all configured strategies."

                elif step.action_type == ActionType.PRESS_KEY:
                    await page.keyboard.press(interpolated_value)

                await page.wait_for_timeout(600)

                # Wait for any spinner to disappear
                try:
                    spinner = page.locator("#search-spinner")
                    if await spinner.count() > 0 and await spinner.first.is_visible():
                        await page.wait_for_selector("#search-spinner", state="hidden", timeout=3000)
                except Exception:
                    pass

                # Check for Security Escalation Lockout State (HITL Trigger)
                security_box = page.locator("#security-challenge-box")
                if await security_box.count() > 0 and await security_box.first.is_visible():
                    intervention = await self.hitl_manager.create_intervention(
                        page=page,
                        capability_id=artifact.metadata.id,
                        session_id=session_id,
                        reason="Supervisory security lockout encountered on live account.",
                        step_id=step.step_id,
                        step_name=step.name,
                        suggested_action="Provide supervisory security token PIN to unlock session."
                    )
                    handoff_res = await self.hitl_manager.transfer_control_to_operator(
                        page=page,
                        request=intervention,
                        mock_operator_action=mock_operator_action
                    )
                    if handoff_res.get("resolution") == "SIMULATED_UNLOCK_SUCCESS":
                        status = "RESOLVED_VIA_HITL"

                # Check for Business Outcome Branches (e.g. Member Not Found)
                for outcome in step.business_outcomes:
                    matched = False
                    if outcome.condition_type == CheckpointAssertion.TEXT_PRESENT:
                        if outcome.target and outcome.target.startswith(("#", ".")):
                            el = page.locator(outcome.target)
                            if await el.count() > 0 and await el.first.is_visible():
                                text = await el.first.inner_text()
                                if (outcome.expected_text and outcome.expected_text.lower() in text.lower()) or (not outcome.expected_text and text.strip()):
                                    matched = True
                        else:
                            body_text = await page.locator("body").inner_text()
                            expected = outcome.expected_text or outcome.target
                            if expected and expected.lower() in body_text.lower():
                                matched = True
                    elif outcome.condition_type == CheckpointAssertion.ELEMENT_VISIBLE:
                        el = page.locator(outcome.target)
                        if await el.count() > 0 and await el.first.is_visible():
                            matched = True

                    if matched:
                        self.logger.log(
                            event_type="BUSINESS_OUTCOME_DETECTED",
                            message=f"Business outcome detected: {outcome.outcome_code} - {outcome.description}",
                            level="INFO",
                            capability_id=artifact.metadata.id,
                            step_id=step.step_id,
                            payload={"code": outcome.outcome_code, "desc": outcome.description}
                        )
                        record = StepExecutionRecord(
                            step_id=step.step_id,
                            step_name=step.name,
                            action_type=step.action_type.value,
                            strategy_used=resolved_strategy,
                            target_resolved=target_resolved,
                            duration_ms=(time.time() - step_start) * 1000,
                            status="BUSINESS_OUTCOME",
                            checkpoint_passed=True
                        )
                        step_records.append(record)

                        return ExecutionResult(
                            status=ExecutionStatus.BUSINESS_OUTCOME,
                            capability_id=artifact.metadata.id,
                            session_id=session_id,
                            duration_total_ms=(time.time() - start_time) * 1000,
                            business_outcome_code=outcome.outcome_code,
                            business_outcome_message=outcome.description,
                            outputs=outcome.output_payload or {},
                            step_records=step_records
                        )

                # Check Step Checkpoint
                checkpoint_passed = True
                if step.checkpoint and status == "SUCCESS":
                    checkpoint_passed = await self._evaluate_checkpoint(page, step.checkpoint)
                    if not checkpoint_passed:
                        status = "CHECKPOINT_FAILED"
                        error_msg = f"Checkpoint assertion failed: expected {step.checkpoint.assertion} on '{step.checkpoint.target}'"

                step_duration = (time.time() - step_start) * 1000
                record = StepExecutionRecord(
                    step_id=step.step_id,
                    step_name=step.name,
                    action_type=step.action_type.value,
                    strategy_used=resolved_strategy,
                    target_resolved=target_resolved,
                    duration_ms=step_duration,
                    status=status,
                    error_message=error_msg,
                    checkpoint_passed=checkpoint_passed
                )
                step_records.append(record)

                if status in ["LOCATOR_FAILED", "CHECKPOINT_FAILED"] and not step.optional:
                    # Capture failure snapshot
                    screenshot_path = f"evidence/screenshots/failure_{session_id}_{step.step_id}.png"
                    os.makedirs("evidence/screenshots", exist_ok=True)
                    try:
                        await page.screenshot(path=screenshot_path)
                        record.screenshot_path = screenshot_path
                    except Exception:
                        pass

                    self.logger.log(
                        event_type="HARD_FAILURE",
                        message=f"Execution halted at step '{step.name}': {error_msg}",
                        level="ERROR",
                        capability_id=artifact.metadata.id,
                        step_id=step.step_id,
                        payload={"error": error_msg, "screenshot": screenshot_path}
                    )

                    return ExecutionResult(
                        status=ExecutionStatus.HARD_FAILURE,
                        capability_id=artifact.metadata.id,
                        session_id=session_id,
                        duration_total_ms=(time.time() - start_time) * 1000,
                        error_details={"failed_step": step.step_id, "error": error_msg},
                        step_records=step_records
                    )

            # 4. Extract declared outputs
            extracted_outputs = {}
            for out in artifact.outputs:
                try:
                    scope = page
                    if out.frame_selector:
                        scope = page.frame_locator(out.frame_selector)
                    loc = scope.locator(out.selector).first
                    if await loc.count() > 0:
                        raw_val = await loc.inner_text() if not out.attribute else await loc.get_attribute(out.attribute)
                        if raw_val and out.regex_pattern:
                            match = re.search(out.regex_pattern, raw_val)
                            extracted_outputs[out.name] = match.group(1) if match else raw_val.strip()
                        else:
                            extracted_outputs[out.name] = raw_val.strip() if raw_val else None
                except Exception as ex:
                    extracted_outputs[out.name] = None
                    self.logger.log("EXTRACTION_WARNING", f"Could not extract output '{out.name}': {ex}", level="WARNING")

            self.logger.log(
                event_type="REPLAY_COMPLETE",
                message=f"Replay completed successfully for capability '{artifact.metadata.name}'",
                capability_id=artifact.metadata.id,
                payload={"outputs": extracted_outputs}
            )

            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                capability_id=artifact.metadata.id,
                session_id=session_id,
                duration_total_ms=(time.time() - start_time) * 1000,
                outputs=extracted_outputs,
                step_records=step_records
            )

        finally:
            if should_close_browser and browser_instance:
                await browser_instance.close()
            if should_close_browser and playwright_instance:
                await playwright_instance.stop()
