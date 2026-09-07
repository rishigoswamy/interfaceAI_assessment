# System Design & Implementation Report: Computer-Use Automation System

**Author**: Engineering Team Candidate  
**Target Environment**: Regulated Banking & Credit Union Back-Office Applications  
**Project Repository**: Computer-Use Automation System  

---

## 1. Architecture

### 1.1 Architectural Paradigm: "Discover Once, Replay Many"
Enterprise back-office banking software (e.g. core ledger software, member service consoles, wire transfer systems) changes slowly in terms of layout but presents real runtime exceptions, security locks, and non-semantic legacy surfaces.

Invoking an LLM ("Computer-Use") on every single production execution is expensive, slow (10–30s latency), non-deterministic, and unsafe for transactional banking operations. Our architecture cleanly splits the lifecycle into two decoupled subsystems:

```
[ Natural Language Goal ] 
           │
           ▼
┌─────────────────────────────────────────┐
│     Discovery Engine (LLM-driven)       │ ──> Explores UI, reasons over a11y/DOM,
│   Observe ──> Decide ──> Act Loop       │     synthesizes robust multi-locators.
└─────────────────────────────────────────┘
           │
           ▼ Compiles into
┌─────────────────────────────────────────┐
│       Typed Capability Artifact         │ ──> Versioned, serializable, reviewable
│   (schema.json: inputs, steps, checks)  │     contract decoupled from LLM transcript.
└─────────────────────────────────────────┘
           │
           ▼ Ingested by
┌─────────────────────────────────────────┐
│     Deterministic Replay Engine         │ ──> Pure deterministic execution (0ms LLM),
│   Multi-Strategy Resolvers & Guards     │     strict error taxonomy, sub-second latency.
└─────────────────────────────────────────┘
      │                    ▲
      ▼ (If Blocked)       │ (Resumed)
┌─────────────────────────────────────────┐
│   Human-in-the-Loop (HITL) Handoff      │ ──> Pauses same live session; operator
│      Live Session Control Seam          │     resolves block; hands back control.
└─────────────────────────────────────────┘
```

### 1.2 System Boundaries & Component Roles
1. **Target Banking Application (`bank_app/`)**: A standalone mock core banking portal (**OmniCore Banking v4.2**) modeling realistic multi-tenant legacy traits: nested tables, iframe dialogs, transient compliance modals, and supervisory security lockout challenges.
2. **Core Schema & Contracts (`src/schema/`)**: Pydantic v2 data models governing `CapabilityArtifact`, `ActionStep`, `TargetLocator`, `CheckpointRule`, `BusinessOutcomeBranch`, and `ExecutionResult`.
3. **Discovery Engine (`src/discovery/`)**: Executes a goal-driven observe-decide-act loop on the live Playwright surface. Analyzes the accessibility tree and interactive controls, parameters input placeholders (`{{member_id}}`), and outputs a validated artifact.
4. **Deterministic Replay Engine (`src/replay/`)**: Consumes the artifact and runtime parameter dictionary. Executes actions using prioritized locator strategies with smart waiting, evaluates checkpoints, handles transient recovery popups, and maps runtime UI states to formal result types.
5. **Human-in-the-Loop Escalation Bridge (`src/escalation/`)**: Intercepts unrecoverable failures or security lockouts on the active page, captures a diagnostic package (reason, screenshot, DOM snapshot), pauses automation, exposes a live operator takeover interface, and seamlessly resumes automation without resetting the browser state.
6. **Safety & Policy Guardrails (`src/guardrails/`)**: Zero-trust URL/domain allowlists, action permissions (`SAFE_READ` vs `IRREVERSIBLE`), and automated PII/credential redaction across logs, artifacts, and output dictionaries.
7. **Observability Engine (`src/observability/`)**: Emits structured JSONL audit logs with timestamps, step timings, strategy resolution traces, and diagnostic failure snapshots.

### 1.3 Key Architectural Trade-offs
* **Synchronous in-process execution vs Distributed Queue**: Implemented as a clean in-process execution engine with async I/O. In production, this core engine embeds directly into Celery/Temporal workers behind an API gateway without architectural changes.
* **Semantic Accessibility Tree vs Pure Computer-Vision Coordinates**: Pure coordinate-based vision is brittle across monitor resolutions and tenant themes; pure DOM CSS selectors fail on non-semantic legacy HTML. We chose a **hybrid prioritized cascade**: Accessibility Tree (Role/Name) $\rightarrow$ Text Heuristics $\rightarrow$ CSS/XPath $\rightarrow$ Coordinate fallback.

---

## 2. Artifact Schema

### 2.1 Schema Design & Contract Decoupling
The capability artifact is an independent, versioned JSON document representing an invocable function. It completely abstracts away the raw LLM conversation history, token streams, and intermediate discovery thoughts.

```json
{
  "metadata": {
    "id": "cap_member_lookup_v1",
    "name": "Member Profile and Balance Lookup",
    "version": "1.0.0",
    "app_name": "OmniCore Banking",
    "tenant_id": "default",
    "risk_level": "SAFE_READ",
    "created_at": "2026-09-01T15:23:53Z"
  },
  "entry_point_url": "http://127.0.0.1:8000",
  "inputs": [
    {
      "name": "member_id",
      "type": "string",
      "description": "Unique identifier of the credit union member",
      "required": true,
      "validation_regex": "^MBR-[0-9A-Za-z_-]+$"
    }
  ],
  "outputs": [
    {
      "name": "savings_balance",
      "type": "string",
      "description": "Current balance of the Primary High-Yield Savings Account",
      "selector": "#account-ledger-table tbody tr:last-child .account-balance-cell"
    }
  ],
  "steps": [ ... ],
  "global_recovery_rules": [ ... ]
}
```

### 2.2 Why the Schema is Shaped This Way
1. **Typed Parameters with Validation**: Calling AI agents supply inputs matching declared parameter types and regex constraints (`validation_regex`), preventing injection attacks and malformed UI actions.
2. **Multi-Tier Locator Definitions**: Each step contains an ordered array of `TargetLocator` objects rather than a single selector, allowing the replay engine to fall back gracefully if minor markup changes occur.
3. **Explicit State Checkpoints**: Every state-altering step contains a `CheckpointRule` asserting that the application transitioned into the expected state (e.g. `ELEMENT_VISIBLE: #member-profile-card`). Automation never blindly assumes a click succeeded.
4. **First-Class Business Outcome Branches**: Steps declare known domain outcomes (e.g. `MEMBER_NOT_FOUND`) with expected UI triggers, allowing the engine to return structured business responses to callers without throwing technical exceptions.

---

## 3. Determinism & Error Handling

### 3.1 Locator Resilience Strategy
To achieve determinism on legacy banking surfaces without test IDs, the locator resolver evaluates strategies in strict order of robustness:

```
[ Target Locator Evaluation ]
  ├── 1. Semantic Accessibility (Role + Accessible Name): get_by_role('tab', name='Member Inquiry')
  ├── 2. Text Anchor Heuristics: get_by_text('Search Records', exact=True)
  ├── 3. Structured CSS / XPath: locator('#member-id-input'), locator('//table[@id="ledger"]')
  └── 4. Spatial Coordinate Fallback: mouse.click(x=300, y=210)
```

### 3.2 Three-Tier Outcome Taxonomy
Conflating expected business states with automation crashes is a fatal flaw in enterprise automation. Our replay engine strictly categorizes results into four distinct outcomes:

| Outcome Tier | Description | Engine Response | Result Status |
|---|---|---|---|
| **Success** | Goal reached, checkpoints passed, outputs extracted. | Returns extracted payload (e.g. `{"savings_balance": "$14,250.00"}`). | `SUCCESS` |
| **Business Outcome** | Valid application state indicating domain condition (e.g. "Member not found", "Insufficient funds"). | Returns structured outcome code (`MEMBER_NOT_FOUND`) without throwing an exception. | `BUSINESS_OUTCOME` |
| **Recoverable Condition** | Transient blocker (e.g. daily compliance notice, loading spinner, session prompt). | Executes `RecoveryRule`, dismisses interstitial, and retries the pending step. | `RECOVERED` |
| **Hard Failure** | Action failure, timeout, or broken workflow. | Captures diagnostic screenshot and DOM snapshot, logs structured error, halts safely. | `HARD_FAILURE` |

### 3.3 Handling UI Drift
- **Multi-Locator Fallback**: If a tenant renames an ID from `#btn-search-member` to `#search-button`, the accessibility role (`role="button", name="Search Records"`) or text anchor resolves the element seamlessly.
- **Dynamic Checkpoint Polling**: Checkpoint evaluations use configurable timeouts (`timeout_ms: 5000`) with polling, accommodating server latency without hardcoded sleeps.

---

## 4. Heterogeneity & Multi-Tenant

### 4.1 Surface Abstraction Architecture
To support modern web apps, legacy web apps (deeply nested tables, framesets), and native desktop applications, the system defines a clean **Surface Driver Adapter Interface**:

```
                       ┌────────────────────────────┐
                       │  Deterministic Replay Core │
                       └────────────────────────────┘
                                     │
                     ┌───────────────┴───────────────┐
                     ▼                               ▼
       ┌───────────────────────────┐   ┌───────────────────────────┐
       │   Web Driver Adapter      │   │  Desktop Driver Adapter   │
       │   (Playwright / CDP)      │   │  (Windows UIA / Win32)    │
       └───────────────────────────┘   └───────────────────────────┘
```

1. **Perception Layer**:
   - Web: Accessibility Tree snapshot (`page.accessibility.snapshot()`) + DOM tree + Screenshot.
   - Desktop: Windows UI Automation (UIA) tree (`AutomationElement`, `ControlPattern`) + OS accessibility hierarchy.
2. **Action Layer**:
   - Web: Playwright click, fill, select, frame switching.
   - Desktop: UIA `InvokePattern`, `ValuePattern`, simulated OS input events.

Because the `CapabilityArtifact` schema is parameterized on action types (`CLICK`, `TYPE`, `SELECT`) and semantic locators (`ROLE_NAME`, `TEXT_ANCHOR`), the core execution engine remains surface-agnostic.

### 4.2 Multi-Tenant Scale & Drift Management
Hundreds of financial institutions use the same underlying vendor software (e.g. FIS, Fiserv, Jack Henry) with custom branding, tenant IDs, and localized layouts.

```
       ┌─────────────────────────────────────────────────────────────┐
       │             Base Vendor Capability Artifact                 │
       │  (e.g., OmniCore v4.2: Member Inquiry & Account Open Flow)  │
       └─────────────────────────────────────────────────────────────┘
                                      │
              ┌───────────────────────┴───────────────────────┐
              ▼                                               ▼
┌───────────────────────────┐                   ┌───────────────────────────┐
│   Tenant A: Apex CU       │                   │ Tenant B: Horizon FCU     │
│   - Base flow identical   │                   │ - Base flow identical     │
│   - Base locators apply   │                   │ - Custom locator override │
│   - Base checkpoints pass │                   │   (#horizon-search-input) │
└───────────────────────────┘                   └───────────────────────────┘
```

1. **Layered Artifact Inheritance (Base + Overlay)**:
   - Institutions share a `base_capability.json` defining the vendor product workflow.
   - A tenant-specific overlay (`tenant_overrides.json`) specifies tenant URLs, custom branding locators, or supplementary recovery rules without re-recording the entire flow.
2. **Automated Drift Detection**:
   - If replay succeeds via fallback strategy #2 or #3 rather than primary strategy #1, an observability alert (`LOCATOR_DRIFT_WARNING`) is emitted, flagging the artifact for non-breaking maintenance.

---

## 5. Escalation & Handoff

### 5.1 Detecting Stuck States & Escalation Triggers
Human escalation is triggered when:
1. An unrecoverable step failure or timeout occurs.
2. An irreversible or risky action requires supervisory dual-authorization.
3. A security challenge or fraud lock screen is detected on the live surface (e.g. `#security-challenge-box`).

### 5.2 Live Session Control Transfer Mechanics
A critical requirement is operating on the **same live browser session** rather than opening a fresh one:

```
[ Automation Running ] ──> [ Lockout Detected ] ──> [ Pause Automation ]
                                                            │
                                                            ▼
                                                [ Package Context & Screenshot ]
                                                            │
                                                            ▼
[ Automation Resumed ] <── [ Control Returned ] <── [ Human Takes Over Live Session ]
```

1. **Session Freezing**: Automation pauses execution on the active Playwright `Page` and `BrowserContext` (preserving active cookies, session tokens, and filled forms).
2. **Context Packaging**: Generates an `InterventionRequest` containing session ID, current step, reason, suggested human action, and diagnostic screenshot.
3. **Live Handoff**: Exposes the live browser session to the human operator (interactive console prompt or local web bridge) to enter supervisor credentials or complete manual verification.
4. **Resumption & Verification**: Once the operator signals completion, the engine validates that the page is unlocked and resumes the remaining automated steps.

---

## 6. Safety

### 6.1 Policy & Allowlist Guardrails
* **Domain Allowlist**: Strict validation ensures the browser never navigates outside approved banking hostnames/IPs (e.g. `localhost`, `127.0.0.1`, internal bank domains). Any attempt to access unauthorized domains raises `PolicyViolationError` immediately.
* **Action Type Governance**: Restricts executable action types to approved operations.
* **Risk Categorization**:
  - `SAFE_READ`: Idempotent balance lookups and searches (always permitted).
  - `REVERSIBLE_WRITE`: Draft notes or form population (permitted with logging).
  - `IRREVERSIBLE`: Fund transfers, account closure, security lock overrides (blocked or gated behind operator confirmation).

### 6.2 Regulated Financial Data & PII Redaction
To maintain compliance with GLBA, PCI-DSS, and banking privacy regulations:
* All execution logs, audit events, and generated artifacts pass through `DataRedactor`.
* SSNs are transformed to `[REDACTED_SSN]`, payment card PANs to `[REDACTED_PAN]`, and bearer tokens/passwords to `[REDACTED_SECRET]`.
* Screenshots captured for failure evidence are scoped to avoid storing unmasked customer data.

---

## 7. Cuts

### 7.1 Deliberately Cut from Scope
1. **Real-time WebRTC Co-browsing UI**: Instead of building a complex WebRTC/VNC streaming frontend for human takeover, we implemented a robust live session handoff seam with CLI/interactive pause-and-resume on the real active browser. The control transfer model, session preservation, and evidence capture are fully functional.
2. **Distributed Message Queue Infrastructure**: Prematurely adding Celery, Redis, and RabbitMQ was avoided in favor of a clean, testable in-process execution engine with async I/O.
3. **Live Desktop Windows UIA Driver**: Implemented against the live web surface while designing the exact Surface Driver Adapter interface so desktop UIA/Win32 drivers plug in cleanly.

### 7.2 What We Would Build Next
1. **Automatic Self-Healing Locators**: On replay success via fallback locator #2, automatically update the artifact's primary locator with a drift confidence score.
2. **Cross-Tenant Parameterized URL Canonicalization**: Auto-generalize URLs containing IDs (`/members/12345` $\rightarrow$ `/members/:member_id`).
3. **Agent-Facing OpenAPI / Tool Catalog**: Expose saved capability artifacts automatically as JSON tool definitions for Anthropic Claude / OpenAI function-calling models.
