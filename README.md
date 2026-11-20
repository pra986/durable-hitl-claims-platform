# durable-hitl-claims-platform

Project 30 (F1: AI FDE - UnderCover): Durable LangGraph and FastAPI travel insurance claims platform enforcing hard payout approval limits in backend code, human sign-off interrupts, and sealed evals.

## Architecture

```
Claimant / Adjuster -> FastAPI Claims API -> LangGraph Durable Checkpointer
                                                    |
                                                    v
                      +----------------------------------------------------------+
                      | 6-Stage Durable Claims Graph (Interrupt & Resume Ready)  |
                      | Intake -> Policy Check -> Evidence -> Payout Cap -> HITL |
                      +----------------------------------------------------------+
                                                    |
                                                    v
                       Deterministic Payout Guardrails + Sealed Eval Suite
```

- **FastAPI Backend**: Exposes claim submission, durable thread status polling, and human-in-the-loop (HITL) resume endpoints.
- **LangGraph Durable Workflow**: Persists state across checkpoints so claims exceeding backend payout thresholds pause cleanly on human sign-off interrupts.
- **Backend Payout Guardrails**: Enforces hard monetary approval caps in deterministic Python code—never delegated to LLM prompts alone.
- **Sealed Eval Suite**: Evaluates policy coverage accuracy, guardrail enforcement, and HITL escalation behavior against held-out scenarios.

## 6-Stage Workflow

1. **Claim Intake & Schema Validation**: Validates claimant identity, policy ID, incident date, and requested payout amount.
2. **Policy Coverage Verification**: Checks active policy window, covered perils, and deductible rules.
3. **Evidence & Receipt Audit**: Extracts and verifies supporting travel disruption or medical documentation.
4. **Deterministic Payout Calculation**: Computes eligible reimbursement and applies backend hard payout approval limits.
5. **Human-in-the-Loop (HITL) Interrupt**: Automatically pauses execution via LangGraph `interrupt` whenever requested or calculated payout exceeds the auto-approval cap or triggers a fraud/ambiguity flag.
6. **Final Settlement & Audit Trail**: Resumes upon signed adjuster approval/rejection, records immutable decision logs, and emits settlement status.

## Data Contract

- **`ClaimRequest`**: `claim_id`, `policy_id`, `claimant_id`, `incident_type`, `incident_date`, `requested_amount_usd`, `evidence_refs`.
- **`PolicyVerificationResult`**: `is_active`, `covered_peril`, `deductible_usd`, `max_coverage_usd`, `exclusions_triggered`.
- **`PayoutDecision`**: `eligible_amount_usd`, `hard_cap_usd`, `requires_hitl_signoff`, `status` (`AUTO_APPROVED | AWAITING_HITL | APPROVED | REJECTED`).
- **`HumanSignOffPayload`**: `reviewer_id`, `approved`, `override_amount_usd`, `rationale`, `signed_at`.

## Production Controls

- **Hard Payout Limits in Backend Code**: Auto-approval ceiling (e.g., `MAX_AUTO_APPROVAL_USD`) is enforced in deterministic backend validators, preventing prompt-injection or model drift from authorizing over-limit payouts.
- **Durable HITL Interrupts**: State is checkpointed before human sign-off so long-running adjuster reviews survive worker restarts.
- **Idempotent Resume & Auditability**: Duplicate sign-off callbacks are deduplicated and every state transition is recorded with reviewer attribution.
- **Sealed Evals**: Regression and adversarial test cases verify zero unauthorized auto-approvals.

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
pytest -v
```

## Attribution

Inspired by and adapted with pinned attribution from [`ed-donner/undercover`](https://github.com/ed-donner/undercover).
 sign-off interrupts, and sealed evals.
