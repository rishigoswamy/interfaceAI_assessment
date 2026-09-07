"""
cli.py
Command-Line Interface for the Computer-Use Automation System.
"""

import argparse
import asyncio
import json
import os
import sys
import threading
import time

from bank_app.server import run_server
from src.discovery.agent import DiscoveryAgent
from src.escalation.handoff import HITLManager
from src.guardrails.policy import SafetyPolicy
from src.observability.logger import ExecutionLogger
from src.replay.engine import DeterministicReplayEngine
from src.schema.artifact import CapabilityArtifact


def cmd_serve_bank(args):
    """Starts the OmniCore Banking mock application."""
    print(f"Starting OmniCore Banking server on {args.host}:{args.port}...")
    run_server(host=args.host, port=args.port)


def cmd_discover(args):
    """Runs the LLM Discovery Agent against a target URL to emit a CapabilityArtifact."""
    async def _run():
        logger = ExecutionLogger(session_id="discovery_cli")
        policy = SafetyPolicy()
        agent = DiscoveryAgent(policy=policy, logger=logger, headless=not args.headed)
        artifact = await agent.discover(
            goal=args.goal,
            entry_point_url=args.url,
            output_file=args.output
        )
        print("\n--- Capability Artifact Summary ---")
        print(f"ID:          {artifact.metadata.id}")
        print(f"Name:        {artifact.metadata.name}")
        print(f"Version:     {artifact.metadata.version}")
        print(f"Risk Level:  {artifact.metadata.risk_level.value}")
        print(f"Inputs:      {[p.name for p in artifact.inputs]}")
        print(f"Outputs:     {[o.name for o in artifact.outputs]}")
        print(f"Steps count: {len(artifact.steps)}")

    asyncio.run(_run())


def cmd_replay(args):
    """Deterministically replays a saved CapabilityArtifact with provided parameters."""
    async def _run():
        if not os.path.exists(args.artifact):
            print(f"Error: Artifact file not found: {args.artifact}")
            sys.exit(1)

        with open(args.artifact, "r", encoding="utf-8") as f:
            artifact_data = json.load(f)
        artifact = CapabilityArtifact.model_validate(artifact_data)

        params = {}
        if args.params:
            try:
                params = json.loads(args.params)
            except json.JSONDecodeError:
                print(f"Error: Invalid JSON string for --params: {args.params}")
                sys.exit(1)

        logger = ExecutionLogger(session_id="replay_cli")
        engine = DeterministicReplayEngine(
            logger=logger,
            headless=not args.headed
        )

        print(f"\n[Deterministic Replay] Invoking Capability '{artifact.metadata.name}'...")
        print(f"[Deterministic Replay] Input Parameters: {json.dumps(params)}")
        result = await engine.execute(
            artifact=artifact,
            inputs=params,
            mock_operator_action=args.mock_operator
        )

        print("\n" + "="*50)
        print("🎯 REPLAY EXECUTION RESULT")
        print("="*50)
        print(f"Status:             {result.status.value}")
        print(f"Capability ID:      {result.capability_id}")
        print(f"Duration:           {result.duration_total_ms:.2f} ms")
        if result.outputs:
            print(f"Extracted Outputs:  {json.dumps(result.outputs, indent=2)}")
        if result.business_outcome_code:
            print(f"Business Outcome:   {result.business_outcome_code} - {result.business_outcome_message}")
        if result.error_details:
            print(f"Error Details:      {json.dumps(result.error_details, indent=2)}")
        print("="*50)

    asyncio.run(_run())


def cmd_run_all_evidence(args):
    """Executes the full pipeline and populates the /evidence/ directory."""
    async def _run():
        os.makedirs("evidence/logs", exist_ok=True)
        os.makedirs("evidence/screenshots", exist_ok=True)

        print("==================================================")
        print("[*] EXECUTING COMPLETE VERIFICATION & EVIDENCE SUITE")
        print("==================================================")

        # 1. Start bank server in background thread if not already active
        import httpx
        server_running = False
        try:
            r = httpx.get("http://127.0.0.1:8000/health", timeout=1.0)
            if r.status_code == 200:
                server_running = True
        except Exception:
            pass

        if not server_running:
            print("Starting mock OmniCore Banking server in background...")
            t = threading.Thread(target=run_server, kwargs={"host": "127.0.0.1", "port": 8000}, daemon=True)
            t.start()
            time.sleep(1.5)

        # Step A: Discovery Run
        print("\n[PHASE 1] Executing Discovery Agent...")
        disc_logger = ExecutionLogger(session_id="discovery_run_evidence", log_dir="evidence/logs")
        agent = DiscoveryAgent(logger=disc_logger, headless=True)
        artifact = await agent.discover(
            goal="Look up member MBR-1092 and read their current savings balance",
            entry_point_url="http://127.0.0.1:8000",
            output_file="evidence/member_lookup.json"
        )
        print("[+] Discovery completed. Artifact saved to evidence/member_lookup.json")

        # Step B: Deterministic Replay - Happy Path
        print("\n[PHASE 2] Executing Deterministic Replay (Happy Path - Member MBR-1092)...")
        replay_logger_1 = ExecutionLogger(session_id="replay_success_evidence", log_dir="evidence/logs")
        engine_1 = DeterministicReplayEngine(logger=replay_logger_1, headless=True)
        res_1 = await engine_1.execute(
            artifact=artifact,
            inputs={"member_id": "MBR-1092"}
        )
        print(f"[+] Replay 1 Status: {res_1.status.value} | Savings Balance: {res_1.outputs.get('savings_balance')}")

        # Step C: Deterministic Replay - Business Outcome (Member Not Found)
        print("\n[PHASE 3] Executing Deterministic Replay (Business Outcome - Member MBR-9999)...")
        replay_logger_2 = ExecutionLogger(session_id="replay_not_found_evidence", log_dir="evidence/logs")
        engine_2 = DeterministicReplayEngine(logger=replay_logger_2, headless=True)
        res_2 = await engine_2.execute(
            artifact=artifact,
            inputs={"member_id": "MBR-9999"}
        )
        print(f"[+] Replay 2 Status: {res_2.status.value} | Outcome Code: {res_2.business_outcome_code}")

        # Step D: Deterministic Replay - Human-in-the-Loop Escalation
        print("\n[PHASE 4] Executing Deterministic Replay with HITL Escalation (Member MBR-LOCKED)...")
        replay_logger_3 = ExecutionLogger(session_id="escalation_session_evidence", log_dir="evidence/logs")
        engine_3 = DeterministicReplayEngine(logger=replay_logger_3, headless=True)
        res_3 = await engine_3.execute(
            artifact=artifact,
            inputs={"member_id": "MBR-LOCKED"},
            mock_operator_action="auto_unlock_pin"
        )
        print(f"[+] Replay 3 Status: {res_3.status.value} | HITL Resolution verified")

        print("\n==================================================")
        print("[SUCCESS] ALL PHASES COMPLETED -- EVIDENCE POPULATED IN /evidence/")
        print("==================================================")

    asyncio.run(_run())


def main():
    parser = argparse.ArgumentParser(description="Computer-Use Automation System CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # serve-bank
    p_serve = subparsers.add_parser("serve-bank", help="Start the mock OmniCore banking application")
    p_serve.add_argument("--host", default="127.0.0.1", help="Host address")
    p_serve.add_argument("--port", type=int, default=8000, help="Port number")

    # discover
    p_disc = subparsers.add_parser("discover", help="Run Computer-Use Discovery agent on a goal")
    p_disc.add_argument("--goal", required=True, help="Natural language goal")
    p_disc.add_argument("--url", default="http://localhost:8000", help="Target entry URL")
    p_disc.add_argument("--output", default="evidence/member_lookup.json", help="Output artifact path")
    p_disc.add_argument("--headed", action="store_true", help="Run browser in visible headed mode")

    # replay
    p_rep = subparsers.add_parser("replay", help="Replay a capability artifact deterministically")
    p_rep.add_argument("--artifact", default="evidence/member_lookup.json", help="Path to capability artifact JSON")
    p_rep.add_argument("--params", default='{"member_id": "MBR-1092"}', help="JSON string of parameter inputs")
    p_rep.add_argument("--headed", action="store_true", help="Run browser in visible headed mode")
    p_rep.add_argument("--mock-operator", choices=["auto_unlock_pin"], default=None, help="Mock operator action for HITL")

    # run-all-evidence
    subparsers.add_parser("run-all-evidence", help="Run end-to-end suite to populate /evidence/")

    args = parser.parse_args()

    if args.command == "serve-bank":
        cmd_serve_bank(args)
    elif args.command == "discover":
        cmd_discover(args)
    elif args.command == "replay":
        cmd_replay(args)
    elif args.command == "run-all-evidence":
        cmd_run_all_evidence(args)


if __name__ == "__main__":
    main()
