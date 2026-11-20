# Architecture Overview

## 1. Purpose
`durable-hitl-claims-platform` is a durable, human-in-the-loop (HITL) travel insurance claims processing platform. It pairs structured agentic decision proposals with deterministic backend financial controls, durable graph checkpoints, and strict evaluation isolation.

## 2. Core Guarantees

### Deterministic Payout Approval Limits
- Payout thresholds (e.g. `MAX_AUTO_PAYOUT_USD = 500.0`) are enforced in backend Python code (`DurableClaimsPlatformEngine`), independent of model prompts or LLM output.
- Any `ClaimDecisionProposal` whose `proposed_payout_usd` exceeds the configured auto-approval limit is routed to the dedicated `human_signoff_interrupt` node and cannot execute a payout until a valid handler sign-off is recorded.

### Durable Checkpointing & Human Sign-Off Interrupt
- Graph execution state is persisted at every transition via a durable checkpointer.
- When a claim triggers `human_signoff_interrupt`, the workflow halts cleanly and awaits an explicit handler decision (`approve` or `reject`) before resuming.

### Idempotent Payout Execution on Resume
- Payout execution is keyed by a deterministic `idempotency_key` (`claim_id:proposal_id`).
- Resuming a graph after a process restart or network retry returns the existing `PayoutApprovalReceipt` instead of issuing a duplicate disbursement.

### Strict Agent-Eval Isolation
- Ground-truth evaluation answer keys under `data/evals` are strictly blocked from agent file-read or tool access at the engine boundary.
- Any attempt by an agent to read `data/evals` raises a `PermissionError` / isolation violation.

### Separate Tool Scopes (Claim Agent vs. Handler Copilot)
- **Claim Agent**: Restricted to read-only claim/policy inspection and submitting `ClaimDecisionProposal` drafts. Cannot approve payouts or sign off on interrupts.
- **Handler Copilot**: Restricted to reviewing pending interrupts, inspecting audit trails, and recording human handler sign-off decisions.

## 3. Module Layout
- `claims_platform/models.py`: Pydantic data models (`ClaimRecord`, `PolicyCoverageClause`, `ClaimDecisionProposal`, `PayoutApprovalReceipt`).
- `claims_platform/engine.py`: `DurableClaimsPlatformEngine`, tool scope enforcement, eval-key isolation, interrupt/resume lifecycle, and idempotent payout ledger.
- `claims_platform/cli.py`: Runnable CLI demonstration of auto-approved and HITL-interrupted claims.
- `evaluation/eval_cases.json`: Benchmark scenarios for payout limits, idempotency, isolation, and tool scopes.
- `tests/test_engine.py`: Automated `pytest` verification suite.
