from __future__ import annotations

from pathlib import Path
from typing import Dict, FrozenSet, Optional
from uuid import uuid4

from claims_platform.models import (
    ClaimDecisionProposal,
    ClaimRecord,
    PayoutApprovalReceipt,
    PolicyCoverageClause,
)

CLAIM_AGENT_TOOLS: FrozenSet[str] = frozenset(
    {"read_claim", "lookup_coverage_clause", "draft_decision_proposal"}
)
HANDLER_COPILOT_TOOLS: FrozenSet[str] = frozenset(
    {"summarize_claim", "inspect_risk_flags", "prepare_signoff_brief"}
)


class ToolScopeViolationError(PermissionError):
    """Raised when an agent attempts to invoke a tool outside its authorized scope."""


class SealedEvaluationIsolationError(PermissionError):
    """Raised when runtime claim processing attempts to access sealed evaluation data."""


class DurableClaimsPlatformEngine:
    """Deterministic backend engine for durable HITL insurance claims processing."""

    def __init__(self, auto_approve_limit: float = 5000.0) -> None:
        if auto_approve_limit < 0:
            raise ValueError("auto_approve_limit must be non-negative")
        self.auto_approve_limit = auto_approve_limit
        self._clauses: Dict[str, PolicyCoverageClause] = {}
        self._claims: Dict[str, ClaimRecord] = {}
        self._proposals: Dict[str, ClaimDecisionProposal] = {}
        self._pending_interrupts: Dict[str, ClaimDecisionProposal] = {}
        self._receipts_by_idempotency_key: Dict[str, PayoutApprovalReceipt] = {}
        self._receipts_by_claim_id: Dict[str, PayoutApprovalReceipt] = {}
        self.payout_execution_count: int = 0

    def register_clause(self, clause: PolicyCoverageClause) -> None:
        self._clauses[clause.incident_type] = clause

    def authorize_tool(self, role: str, tool_name: str) -> bool:
        allowed_by_role = {
            "claim_agent": CLAIM_AGENT_TOOLS,
            "handler_copilot": HANDLER_COPILOT_TOOLS,
        }
        if role not in allowed_by_role:
            raise ToolScopeViolationError(f"Unknown agent role: {role}")
        if tool_name not in allowed_by_role[role]:
            raise ToolScopeViolationError(
                f"Role '{role}' is not authorized to invoke tool '{tool_name}'"
            )
        return True

    def assert_not_sealed_eval_path(self, source_path: str | Path) -> None:
        normalized = Path(source_path).as_posix().lower()
        if "evaluation/" in normalized or normalized.endswith("eval_cases.json"):
            raise SealedEvaluationIsolationError(
                "Runtime engine cannot access sealed evaluation fixtures"
            )

    def evaluate_claim(
        self, claim: ClaimRecord, idempotency_key: Optional[str] = None
    ) -> tuple[ClaimDecisionProposal, Optional[PayoutApprovalReceipt]]:
        self._claims[claim.claim_id] = claim
        clause = self._clauses.get(claim.incident_type)
        if clause is None:
            proposal = ClaimDecisionProposal(
                proposal_id=f"PROP-{uuid4().hex[:8]}",
                claim_id=claim.claim_id,
                clause_id="NONE",
                proposed_payout=0.0,
                recommended_action="DENY",
                rationale=f"No coverage clause found for incident '{claim.incident_type}'",
                requires_human_signoff=False,
                status="REJECTED",
            )
            self._proposals[claim.claim_id] = proposal
            receipt = PayoutApprovalReceipt(
                receipt_id=f"RCPT-{uuid4().hex[:8]}",
                claim_id=claim.claim_id,
                proposal_id=proposal.proposal_id,
                idempotency_key=idempotency_key or f"idem-{claim.claim_id}",
                approved_amount=0.0,
                currency=claim.currency,
                approval_mode="REJECTED",
                approved_by="SYSTEM_BACKEND",
                executed=False,
            )
            self._receipts_by_claim_id[claim.claim_id] = receipt
            self._receipts_by_idempotency_key[receipt.idempotency_key] = receipt
            return proposal, receipt

        if clause.excluded:
            proposal = ClaimDecisionProposal(
                proposal_id=f"PROP-{uuid4().hex[:8]}",
                claim_id=claim.claim_id,
                clause_id=clause.clause_id,
                proposed_payout=0.0,
                recommended_action="DENY",
                rationale=f"Incident '{claim.incident_type}' is excluded by clause {clause.clause_id}",
                requires_human_signoff=False,
                status="REJECTED",
            )
            self._proposals[claim.claim_id] = proposal
            receipt = PayoutApprovalReceipt(
                receipt_id=f"RCPT-{uuid4().hex[:8]}",
                claim_id=claim.claim_id,
                proposal_id=proposal.proposal_id,
                idempotency_key=idempotency_key or f"idem-{claim.claim_id}",
                approved_amount=0.0,
                currency=claim.currency,
                approval_mode="REJECTED",
                approved_by="SYSTEM_BACKEND",
                executed=False,
            )
            self._receipts_by_claim_id[claim.claim_id] = receipt
            self._receipts_by_idempotency_key[receipt.idempotency_key] = receipt
            return proposal, receipt

        net_eligible = max(0.0, claim.requested_amount - clause.deductible)
        proposed_payout = min(net_eligible, clause.max_coverage_amount)
        requires_signoff = proposed_payout > self.auto_approve_limit

        if requires_signoff:
            proposal = ClaimDecisionProposal(
                proposal_id=f"PROP-{uuid4().hex[:8]}",
                claim_id=claim.claim_id,
                clause_id=clause.clause_id,
                proposed_payout=proposed_payout,
                recommended_action="ESCALATE",
                rationale=(
                    f"Proposed payout {proposed_payout:.2f} exceeds backend "
                    f"auto-approve limit {self.auto_approve_limit:.2f}"
                ),
                requires_human_signoff=True,
                status="PENDING_HUMAN_SIGN_OFF",
            )
            self._proposals[claim.claim_id] = proposal
            self._pending_interrupts[claim.claim_id] = proposal
            return proposal, None

        proposal = ClaimDecisionProposal(
            proposal_id=f"PROP-{uuid4().hex[:8]}",
            claim_id=claim.claim_id,
            clause_id=clause.clause_id,
            proposed_payout=proposed_payout,
            recommended_action="APPROVE",
            rationale=(
                f"Proposed payout {proposed_payout:.2f} is within backend "
                f"auto-approve limit {self.auto_approve_limit:.2f}"
            ),
            requires_human_signoff=False,
            status="AUTO_APPROVED",
        )
        self._proposals[claim.claim_id] = proposal
        receipt = self._execute_payout_once(
            claim=claim,
            proposal=proposal,
            idempotency_key=idempotency_key or f"idem-{claim.claim_id}",
            approval_mode="AUTO_APPROVED",
            approved_by="SYSTEM_BACKEND",
        )
        return proposal, receipt

    def resume_with_signoff(
        self,
        claim_id: str,
        approved: bool,
        handler_id: str,
        idempotency_key: str,
    ) -> PayoutApprovalReceipt:
        if idempotency_key in self._receipts_by_idempotency_key:
            return self._receipts_by_idempotency_key[idempotency_key]
        if claim_id in self._receipts_by_claim_id:
            return self._receipts_by_claim_id[claim_id]
        if claim_id not in self._pending_interrupts:
            raise KeyError(f"No pending human sign-off interrupt for claim '{claim_id}'")

        proposal = self._pending_interrupts.pop(claim_id)
        claim = self._claims[claim_id]

        if not approved:
            proposal.status = "REJECTED"
            receipt = PayoutApprovalReceipt(
                receipt_id=f"RCPT-{uuid4().hex[:8]}",
                claim_id=claim_id,
                proposal_id=proposal.proposal_id,
                idempotency_key=idempotency_key,
                approved_amount=0.0,
                currency=claim.currency,
                approval_mode="REJECTED",
                approved_by=handler_id,
                executed=False,
            )
            self._receipts_by_claim_id[claim_id] = receipt
            self._receipts_by_idempotency_key[idempotency_key] = receipt
            return receipt

        proposal.status = "APPROVED"
        return self._execute_payout_once(
            claim=claim,
            proposal=proposal,
            idempotency_key=idempotency_key,
            approval_mode="HUMAN_SIGNED_OFF",
            approved_by=handler_id,
        )

    def _execute_payout_once(
        self,
        claim: ClaimRecord,
        proposal: ClaimDecisionProposal,
        idempotency_key: str,
        approval_mode: str,
        approved_by: str,
    ) -> PayoutApprovalReceipt:
        if idempotency_key in self._receipts_by_idempotency_key:
            return self._receipts_by_idempotency_key[idempotency_key]
        if claim.claim_id in self._receipts_by_claim_id:
            return self._receipts_by_claim_id[claim.claim_id]

        self.payout_execution_count += 1
        receipt = PayoutApprovalReceipt(
            receipt_id=f"RCPT-{uuid4().hex[:8]}",
            claim_id=claim.claim_id,
            proposal_id=proposal.proposal_id,
            idempotency_key=idempotency_key,
            approved_amount=proposal.proposed_payout,
            currency=claim.currency,
            approval_mode=approval_mode,  # type: ignore[arg-type]
            approved_by=approved_by,
            executed=True,
        )
        self._receipts_by_claim_id[claim.claim_id] = receipt
        self._receipts_by_idempotency_key[idempotency_key] = receipt
        return receipt
