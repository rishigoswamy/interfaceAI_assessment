# Computer-Use Automation System

**A production-grade backend integration layer enabling AI agents to operate legacy back-office banking software without APIs.**

Built for **interface.ai** — Engineering Take-Home Project.

---

## 1. Overview & Core Paradigm

In US banks and credit unions, core banking systems, loan servicing portals, and administrative consoles lack modern APIs. Automation must interact with live UIs the way human operators do.

This system solves this problem with a **Discover-Once, Replay-Many** paradigm:
1. **Discovery (LLM / Computer Use)**: An LLM explores the live application surface for a natural language goal, reasons through UI structures, and executes the sequence.
2. **Capability Artifact**: The discovery run compiles the interaction trace into a strongly-typed, parameterized, versioned, and reviewable **Capability Artifact** (decoupled from raw model transcripts).
3. **Deterministic Replay (Production Execution)**: AI agents invoke the capability directly with runtime input parameters (e.g. `member_id: "MBR-1092"`) — running with **no LLM in the loop**, millisecond execution times, resilient multi-strategy locators, and explicit classification of business outcomes vs technical failures.
4. **Human-in-the-Loop (HITL) Live Session Handoff**: If automation encounters a security lockout or stuck state, it pauses on the **same live browser session**, transfers control to a human operator, and resumes seamlessly after resolution.
5. **Safety & PII Guardrails**: Enforces domain allowlists, action risk policies, and automatic sanitization of SSNs, account numbers, and credentials.

---

## 2. Architecture Summary

```
                       +---------------------------------------------+
                       |  Caller / AI Agent (e.g. Customer Assistant)|
                       +---------------------------------------------+
                                       |
                   +-------------------+-------------------+
                   | (First Time: Discovery)               | (Production: Replay)
                   v                                       v
      +-------------------------+             +--------------------------+
      |     Discovery Agent     |             | Deterministic Replay     |
      |   (Observe-Decide-Act)  |             |          Engine          |
      +-------------------------+             +--------------------------+
                   |                                       |
                   | Generates                             | Ingests & Executes
                   v                                       |
      +-------------------------+                          |
      |   Capability Artifact   |--------------------------+
      |  (Typed Schema Contract)|
      +-------------------------+
                   |                                       |
                   +-------------------+-------------------+
                                       | Drives Surface
                                       v
                   +---------------------------------------+
                   | OmniCore Banking Portal (v4.2)        |
                   | - Multi-tenant Branding & Config      |
                   | - Nested Legacy Tables & Frames       |
                   | - Transient Compliance Interstitials  |
                   | - Security Lockout Escalation States  |
                   +---------------------------------------+
                                       |
                  [Security Lockout / Stuck Detected]
                                       v
                   +---------------------------------------+
                   | Human-in-the-Loop (HITL) Bridge       |
                   | - Pauses Live Session (No Restart)    |
                   | - Operator Overrides Security Lock    |
                   | - Seamless Resume & Audit Log         |
                   +---------------------------------------+
```

---

## 3. Installation & Setup

### Prerequisites
* Python 3.10+
* Playwright & Chromium browser binary

### Setup Commands
```bash
# 1. Clone repository
git clone https://github.com/<your-username>/computer-use-automation.git
cd computer-use-automation

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install Playwright browser binaries
python -m playwright install chromium
```

---

## 4. Quickstart Demo Commands

### Step 1: Start the Mock Target Banking Application
Launch the standalone OmniCore Banking portal:
```bash
python cli.py serve-bank --port 8000
```
*Access the portal in your browser at `http://127.0.0.1:8000` to inspect the UI, tenants, and ledger records.*

---

### Step 2: Run Goal-Driven Discovery
Run the discovery agent to explore the live application and synthesize a reusable capability artifact:
```bash
python cli.py discover --goal "Look up member MBR-1092 and read their current savings balance" --url "http://127.0.0.1:8000" --output evidence/member_lookup.json
```

---

### Step 3: Replay Deterministically (Production Execution)

#### A. Happy Path Replay
Execute the capability without an LLM to retrieve savings balance:
```bash
python cli.py replay --artifact evidence/member_lookup.json --params "{\"member_id\": \"MBR-1092\"}"
```
**Output**:
```json
{
  "member_id": "MBR-1092",
  "member_status": "ACTIVE",
  "savings_balance": "$14,250.00"
}
```

#### B. Expected Business Outcome (Member Not Found)
Replay with an unregistered member ID (`MBR-9999`). The system returns a clean `BUSINESS_OUTCOME` response instead of a runtime crash:
```bash
python cli.py replay --artifact evidence/member_lookup.json --params "{\"member_id\": \"MBR-9999\"}"
```
**Output**:
```
Status:           BUSINESS_OUTCOME
Business Outcome: MEMBER_NOT_FOUND - The requested member record was not found in the active core banking ledger.
```

#### C. Human-in-the-Loop (HITL) Escalation on Security Lockout
Replay on a security-locked member (`MBR-LOCKED`). The system pauses on the live session, routes an intervention request to the operator console, simulates/accepts the supervisory PIN override, and resumes:
```bash
python cli.py replay --artifact evidence/member_lookup.json --params "{\"member_id\": \"MBR-LOCKED\"}" --mock-operator auto_unlock_pin
```

---

### Step 4: Run Complete End-to-End Verification & Populate `/evidence/`
Executes discovery, happy-path replay, business outcome handling, and HITL live escalation in one automated pass:
```bash
python cli.py run-all-evidence
```

---

### Step 5: Run Automated Test Suite
Run the full pytest suite testing schemas, safety policies, PII redactor, deterministic replay, and HITL handoff:
```bash
python -m pytest tests/ -v
```

---

## 5. Repository Structure

```
.
├── bank_app/                  # Mock legacy core banking portal (OmniCore v4.2)
│   ├── server.py              # FastAPI server
│   ├── data.py                # In-memory member & ledger database
│   ├── templates/             # Jinja2 HTML templates
│   └── static/style.css       # Portal styling
├── src/
│   ├── schema/                # Pydantic capability contracts, steps, results, events
│   ├── discovery/             # Observe-Decide-Act agent & capability compiler
│   ├── replay/                # Deterministic replay engine & multi-strategy locator
│   ├── escalation/            # HITL live session handoff manager
│   ├── guardrails/            # Domain allowlists, risk policy, PII redactor
│   └── observability/         # Structured JSON execution & audit logger
├── evidence/                  # Generated capability artifacts, session logs & snapshots
│   ├── member_lookup.json     # Production capability artifact
│   ├── logs/                  # JSONL audit traces
│   └── screenshots/           # Diagnostic screenshots
├── tests/                     # Comprehensive test suite (10/10 automated tests)
├── cli.py                     # Unified CLI entrypoint
├── REPORT.md                  # Detailed 7-section design & evaluation report
└── README.md                  # Setup & execution guide
```
